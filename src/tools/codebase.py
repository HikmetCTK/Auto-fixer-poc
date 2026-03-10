"""Codebase tools — agent-callable tools for interacting with indexed code.

These tools let agents:
  * **search** the codebase by keyword
  * **read** files or specific line ranges
  * **list** files in the project
"""

from __future__ import annotations

import json
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.agents.base import AgentContext

from src.indexer.indexer import CodebaseIndex
from src.tools.base import Tool, ToolParameter


# ── Shared index instance ────────────────────────────────────────────────
# The orchestrator initialises this once; all tools share the same index.
_global_index: CodebaseIndex | None = None


def set_global_index(index: CodebaseIndex) -> None:
    global _global_index
    _global_index = index


def get_global_index() -> CodebaseIndex | None:
    return _global_index


# ── Tool: Keyword Search ────────────────────────────────────────────────
class CodebaseSearchTool(Tool):
    """Search the indexed codebase for a keyword or pattern."""

    name = "codebase_search"
    description = (
        "Search the project codebase for a keyword or pattern. "
        "Returns matching code chunks with file paths, line numbers, "
        "and matched lines. Use this to find where errors originate, "
        "locate function definitions, or find usage of specific variables."
    )
    parameters = [
        ToolParameter(
            name="query",
            type="string",
            description="The keyword or pattern to search for (e.g. 'database_url', 'def connect', 'KeyError').",
            required=True,
        ),
        ToolParameter(
            name="max_results",
            type="integer",
            description="Maximum number of results to return (default: 10).",
            required=False,
        ),
    ]

    async def execute(self, **kwargs: Any) -> str:
        index = get_global_index()
        if index is None:
            return json.dumps({"error": "Codebase not indexed. Call index_directory first."})

        query = kwargs.get("query", "")
        max_results = int(kwargs.get("max_results", 10))

        if not query:
            return json.dumps({"error": "Empty search query."})

        hits = index.keyword_search(query, max_results=max_results)

        if not hits:
            return json.dumps({"results": [], "message": f"No matches found for '{query}'."})

        results = []
        for hit in hits:
            results.append({
                "file": hit.chunk.file_path,
                "name": hit.chunk.qualified_name,
                "type": hit.chunk.chunk_type,
                "lines": f"{hit.chunk.start_line}-{hit.chunk.end_line}",
                "score": hit.score,
                "matched_lines": hit.matched_lines[:5],
                "content": hit.chunk.content[:500],  # truncate for context window
            })

        return json.dumps({"results": results, "total": len(results)}, ensure_ascii=False)


# ── Tool: Read File ─────────────────────────────────────────────────────
class CodebaseReadTool(Tool):
    """Read a file or specific line range from the indexed codebase."""

    name = "codebase_read"
    description = (
        "Read the contents of a file from the project codebase. "
        "You can read the entire file or a specific line range. "
        "Use this after searching to inspect the full context around a match. "
        "If a file is listed under 'Already-Read Files' in your context, do NOT call this — use that content."
    )
    parameters = [
        ToolParameter(
            name="file_path",
            type="string",
            description="Relative path to the file (e.g. 'src/config.py', 'main.py').",
            required=True,
        ),
        ToolParameter(
            name="start_line",
            type="integer",
            description="Start line number (1-indexed). Omit to read entire file.",
            required=False,
        ),
        ToolParameter(
            name="end_line",
            type="integer",
            description="End line number (1-indexed, inclusive). Omit to read entire file.",
            required=False,
        ),
    ]

    def __init__(self, context: "AgentContext | None" = None) -> None:
        super().__init__()
        self._context = context

    async def execute(self, **kwargs: Any) -> str:
        index = get_global_index()
        if index is None:
            return json.dumps({"error": "Codebase not indexed."})

        file_path = kwargs.get("file_path", "")
        start = kwargs.get("start_line")
        end = kwargs.get("end_line")

        if not file_path:
            return json.dumps({"error": "file_path is required."})

        # ── Normalize cache key ────────────────────────────────────────────
        # Whole-file reads (no range) use just the file path as key so that
        # all agents hit the same cache entry regardless of None vs explicit args.
        if start is None and end is None:
            cache_key = file_path
        else:
            cache_key = f"{file_path}:{start}:{end}"

        # ── Cache hit: return previously-read content ──────────────────────
        if self._context and cache_key in self._context.file_cache:
            cached = self._context.file_cache[cache_key]
            return json.dumps({
                "file": file_path,
                "content": cached,
                "truncated": False,
                "total_chars": len(cached),
                "cached": True,
            }, ensure_ascii=False)

        if start is not None and end is not None:
            content = index.read_lines(file_path, int(start), int(end))
        else:
            content = index.read_file(file_path)

        if content is None:
            base_name = file_path.replace("\\", "/").split("/")[-1]
            available = index.list_files(f"*{base_name}*")
            hint = f"Use one of these exact paths: {available[:5]}" if available else "No similar files found."
            return json.dumps({
                "error": f"File not found: {file_path}",
                "hint": hint,
                "similar_files": available[:5],
            })

        # Increased from 3000 → 8000 chars so the LLM rarely needs a second
        # partial read (avoids the truncated-file re-read loop).
        MAX_CONTENT = 8000
        truncated_content = content[:MAX_CONTENT]

        # ── Store in shared cache for subsequent agents ────────────────────
        if self._context:
            self._context.file_cache[cache_key] = truncated_content

        return json.dumps({
            "file": file_path,
            "content": truncated_content,
            "truncated": len(content) > 3000,
            "total_chars": len(content),
        }, ensure_ascii=False)


# ── Tool: List Files ────────────────────────────────────────────────────
class CodebaseListTool(Tool):
    """List files in the indexed codebase."""

    name = "codebase_list"
    description = (
        "List files in the project codebase. Optionally filter by glob pattern. "
        "Use this to understand the project structure before reading specific files."
    )
    parameters = [
        ToolParameter(
            name="pattern",
            type="string",
            description="Glob pattern to filter files (e.g. '*.py', 'src/*.py', '*test*'). Default: '*' (all files).",
            required=False,
        ),
    ]

    async def execute(self, **kwargs: Any) -> str:
        index = get_global_index()
        if index is None:
            return json.dumps({"error": "Codebase not indexed."})

        pattern = kwargs.get("pattern", "*")
        files = index.list_files(pattern)

        return json.dumps({
            "files": files,
            "total": len(files),
            "pattern": pattern,
        })


# ── Tool: Codebase Stats ────────────────────────────────────────────────
class CodebaseStatsTool(Tool):
    """Get statistics about the indexed codebase."""

    name = "codebase_stats"
    description = (
        "Get overview statistics of the indexed codebase: "
        "file count, chunk count, language breakdown, and chunk types."
    )
    parameters = []

    async def execute(self, **kwargs: Any) -> str:
        index = get_global_index()
        if index is None:
            return json.dumps({"error": "Codebase not indexed."})
        return json.dumps(index.stats())
