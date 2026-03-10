"""Codebase Indexer — scans, chunks, and indexes an entire project.

Walks a project directory, parses every supported source file via ``chunker``,
and builds an in-memory index that supports:

  * **keyword search** — fast grep-like text matching across all chunks
  * **chunk lookup**   — retrieve a specific chunk by file + name
  * **file listing**   — browse the indexed file tree

Phase 3 migration: chunks will also be embedded via ``text-embedding-004``
and stored in pgvector for semantic (RAG) search.
"""

from __future__ import annotations

import fnmatch
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from src.indexer.chunker import CodeChunk, chunk_file

logger = logging.getLogger(__name__)

def get_faiss():
    """Lazily import and return faiss, raising ImportError if not available."""
    try:
        import faiss
        return faiss
    except ImportError:
        raise ImportError('faiss-cpu is required for semantic search. Install with: uv add faiss-cpu')

# ── Default ignore patterns ──────────────────────────────────────────────
DEFAULT_IGNORE: list[str] = [
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "*.egg-info",
    "dist",
    "build",
    "out",
    ".next",
    ".cache",
    ".parcel-cache",
    "coverage",
    "*.pyc",
    "*.pyo",
    "*.so",
    "*.dll",
    "*.exe",
    "*.bin",
    "*.whl",
    "*.lock",
]

# Supported source file extensions
SUPPORTED_EXTENSIONS: set[str] = {
    ".py", ".js", ".ts", ".jsx", ".tsx",
    ".java", ".go", ".rs", ".rb", ".php",
    ".cs", ".cpp", ".c", ".h", ".hpp",
    ".yaml", ".yml", ".toml", ".json",
    ".md", ".txt", ".cfg", ".ini",
    ".sql", ".sh", ".bash", ".dockerfile",
}


# ── Search result ────────────────────────────────────────────────────────
@dataclass
class SearchHit:
    """A single search result from the index."""

    chunk: CodeChunk
    score: float = 0.0          # relevance score (keyword count for now)
    matched_lines: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "file": self.chunk.file_path,
            "name": self.chunk.qualified_name,
            "type": self.chunk.chunk_type,
            "lines": f"{self.chunk.start_line}-{self.chunk.end_line}",
            "score": self.score,
            "matched_lines": self.matched_lines[:5],
            "summary": self.chunk.summary(),
        }


# ── Codebase Index ───────────────────────────────────────────────────────
class CodebaseIndex:
    """In-memory index of a codebase, chunked via AST and cached via Pickle."""

    def __init__(self) -> None:
        self.chunks: list[CodeChunk] = []
        self.files: dict[str, list[CodeChunk]] = {}   # file_path → chunks
        self.root: str = ""
        self._indexed = False

    # ── Indexing ─────────────────────────────────────────────────────────
    def index_directory(
        self,
        root: str | Path,
        ignore_patterns: list[str] | None = None,
    ) -> int:
        """Walk ``root``, chunk every source file with caching, return total chunk count."""
        import pickle
        import os
        
        root = Path(root).resolve()
        self.root = str(root)
        self.chunks.clear()
        self.files.clear()

        ignore = ignore_patterns or DEFAULT_IGNORE
        cache_file = root / ".codebase_index_cache.pkl"
        
        # Load existing cache if available
        cache_data = {}
        if cache_file.exists():
            try:
                with open(cache_file, "rb") as f:
                    cache_data = pickle.load(f)
                logger.info("Loaded index cache from %s", cache_file)
            except Exception as e:
                logger.warning("Failed to load index cache: %s", e)

        new_cache_data = {}
        file_count = 0
        changed_or_new_files = 0

        # ── Walk and index ───────────────────────────────────────────────
        def walk_dir(current_path: Path):
            nonlocal file_count, changed_or_new_files
            
            # Skip if this directory itself should be ignored
            if self._should_ignore(current_path, root, ignore):
                return

            try:
                # Use sorted iterdir for deterministic indexing order
                for path in sorted(current_path.iterdir()):
                    if path.is_dir():
                        walk_dir(path)
                    elif path.is_file():
                        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                            continue
                        if self._should_ignore(path, root, ignore):
                            continue

                        rel_str = str(path.relative_to(root))
                        mtime = os.path.getmtime(path)
                        
                        # Check cache hit based on modification time
                        if rel_str in cache_data and cache_data[rel_str]["mtime"] == mtime:
                            file_chunks = cache_data[rel_str]["chunks"]
                        else:
                            # No cache hit, parse the file
                            file_chunks = chunk_file(path)
                            changed_or_new_files += 1

                        if file_chunks:
                            for c in file_chunks:
                                c.file_path = rel_str
                            
                            # Update records
                            self.chunks.extend(file_chunks)
                            self.files[rel_str] = file_chunks
                            new_cache_data[rel_str] = {"mtime": mtime, "chunks": file_chunks}
                            file_count += 1
            except (PermissionError, OSError) as e:
                logger.warning("Failed to scan directory %s: %s", current_path, e)

        walk_dir(root)

        self._indexed = True
        logger.info(
            "Indexed %d files (parsed %d, cached %d) → %d chunks from %s",
            file_count, changed_or_new_files, file_count - changed_or_new_files, len(self.chunks), root,
        )
        
        # Save updated cache safely
        try:
            with open(cache_file, "wb") as f:
                pickle.dump(new_cache_data, f)
        except Exception as e:
            logger.warning("Failed to save index cache: %s", e)

        return len(self.chunks)

    # ── Keyword search ───────────────────────────────────────────────────
    def keyword_search(
        self,
        query: str,
        *,
        max_results: int = 10,
        case_sensitive: bool = False,
    ) -> list[SearchHit]:
        """Search all chunks for a keyword/pattern.

        Returns hits sorted by relevance (match count).
        """
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            pattern = re.compile(re.escape(query), flags)
        except re.error:
            pattern = re.compile(re.escape(query), flags)

        hits: list[SearchHit] = []

        for chunk in self.chunks:
            matches = pattern.findall(chunk.content)
            if matches:
                matched_lines = [
                    line.strip()
                    for line in chunk.content.splitlines()
                    if pattern.search(line)
                ]
                hits.append(SearchHit(
                    chunk=chunk,
                    score=len(matches),
                    matched_lines=matched_lines,
                ))

        # Sort by score descending
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:max_results]

    # ── Read file ────────────────────────────────────────────────────────
    def read_file(self, file_path: str) -> str | None:
        """Read the full content of an indexed file."""
        # Normalize separators so 'src/tools/x.py' matches 'src\\tools\\x.py' on Windows
        normalized = file_path.replace("/", "\\").replace("\\\\", "\\")
        if normalized not in self.files:
            normalized = file_path.replace("\\", "/")  # try Unix style too
        key = normalized if normalized in self.files else file_path

        if key in self.files:
            full_path = Path(self.root) / key
            if full_path.exists():
                return full_path.read_text(encoding="utf-8", errors="replace")
            sorted_chunks = sorted(self.files[key], key=lambda c: c.start_line)
            return "\n".join(c.content for c in sorted_chunks)
        return None

    # ── Read specific lines ──────────────────────────────────────────────
    def read_lines(self, file_path: str, start: int, end: int) -> str | None:
        """Read specific line range from a file (1-indexed, inclusive)."""
        # Normalize separators for cross-platform compatibility
        full_path = Path(self.root) / file_path
        if not full_path.exists():
            # Try the other separator style
            alt = file_path.replace("/", "\\") if "/" in file_path else file_path.replace("\\", "/")
            full_path = Path(self.root) / alt
        if not full_path.exists():
            return None
        lines = full_path.read_text(encoding="utf-8", errors="replace").splitlines()
        selected = lines[max(0, start - 1) : end]
        return "\n".join(selected)

    # ── Chunk lookup ─────────────────────────────────────────────────────
    def get_chunk(self, file_path: str, name: str) -> CodeChunk | None:
        """Find a specific chunk by file path and qualified name."""
        for chunk in self.files.get(file_path, []):
            if chunk.qualified_name == name or chunk.name == name:
                return chunk
        return None

    # ── List files ───────────────────────────────────────────────────────
    def list_files(self, pattern: str = "*") -> list[str]:
        """List indexed files, optionally filtered by glob pattern."""
        return [
            f for f in sorted(self.files.keys())
            if fnmatch.fnmatch(f, pattern)
        ]

    # ── Stats ────────────────────────────────────────────────────────────
    def stats(self) -> dict:
        """Return index statistics."""
        lang_count: dict[str, int] = {}
        type_count: dict[str, int] = {}
        for c in self.chunks:
            lang_count[c.language] = lang_count.get(c.language, 0) + 1
            type_count[c.chunk_type] = type_count.get(c.chunk_type, 0) + 1

        return {
            "root": self.root,
            "total_files": len(self.files),
            "total_chunks": len(self.chunks),
            "by_language": lang_count,
            "by_type": type_count,
        }

    # ── Helpers ──────────────────────────────────────────────────────────
    @staticmethod
    def _should_ignore(path: Path, root: Path, patterns: list[str]) -> bool:
        """Check if a path matches any ignore pattern."""
        rel_parts = path.relative_to(root).parts
        for part in rel_parts:
            for pat in patterns:
                if fnmatch.fnmatch(part, pat):
                    return True
        return False
