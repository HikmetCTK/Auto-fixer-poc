"""File Editor Tool â€” allows the agent to apply fixes to the codebase."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from src.tools.base import Tool, ToolParameter

logger = logging.getLogger(__name__)


class FileEditorTool(Tool):
    """Modifies a file in the codebase."""

    name = "file_editor"
    description = (
        "Replace text in a specified file. "
        "Use this tool to apply a bug fix to the codebase. "
        "Be extremely precise with 'target_text' as it must match exactly the text you want to replace."
    )
    parameters = [
        ToolParameter(
            name="file_path",
            type="string",
            description="The relative path to the file to edit (e.g. 'src/agents/orchestrator.py').",
            required=True,
        ),
        ToolParameter(
            name="target_text",
            type="string",
            description="The exact text to be replaced in the file.",
            required=True,
        ),
        ToolParameter(
            name="replacement_text",
            type="string",
            description="The exact replacement text.",
            required=True,
        ),
    ]

    async def execute(self, **kwargs: Any) -> str:
        file_path = kwargs.get("file_path", "")
        target_text = kwargs.get("target_text", "")
        replacement_text = kwargs.get("replacement_text", "")

        # ── Resolve path: try relative to indexed codebase root first ────────
        # Agents supply relative paths (e.g. 'src/utils/foo.py'). We must
        # resolve them against the project root, not the process CWD.
        resolved_path = file_path
        if not os.path.isfile(file_path):
            try:
                from src.tools.codebase import get_global_index
                index = get_global_index()
                if index and index.root:
                    candidate = os.path.join(index.root, file_path.replace("/", os.sep))
                    if os.path.isfile(candidate):
                        resolved_path = candidate
            except Exception:
                pass

        if not os.path.isfile(resolved_path):
            return json.dumps({
                "error": f"File not found: {file_path} (resolved: {resolved_path}). "
                         "Provide the path exactly as returned by codebase_list or codebase_search.",
                "passed": False,
            })
        file_path = resolved_path

        # Read raw bytes first to avoid implicit UTF-8 decoding.
        with open(file_path, "rb") as f:
            raw_bytes = f.read()
        
        try:
            content = raw_bytes.decode("utf-8", errors="replace")
        except Exception:
            content = raw_bytes.decode("latin-1", errors="replace")

        # Normalize newlines to avoid \r\n vs \n mismatch failures
        content = content.replace("\r\n", "\n")
        target_text = target_text.replace("\r\n", "\n")

        # Fallback 1: Exact match after stripping
        strip_target = target_text.strip()
        if target_text not in content and strip_target and strip_target in content:
            target_text = strip_target
            
        # Fallback 2: Fuzzy match if exact whitespace differences exist
        if target_text not in content:
            import re
            
            # Escape regex characters but make whitespace flexible
            escaped = re.escape(target_text)
            flexible_white = re.sub(r'\\s\+', r'\\s+', re.sub(r'\s+', r'\\s+', escaped))
            
            match = re.search(flexible_white, content)
            if match:
                target_text = match.group(0) # Use the EXACT string found in the file
            else:
                return json.dumps({
                    "error": "The 'target_text' was not found in the file exactly as provided. Please verify spacing and try again.", 
                    "passed": False
                })

        # Replace exactly one instance to prevent unintended replacements if duplicated snippet
        new_content = content.replace(target_text, replacement_text, 1)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        logger.info("Successfully replaced content in %s", file_path)
        return json.dumps({"success": f"File {file_path} successfully modified.", "passed": True})
