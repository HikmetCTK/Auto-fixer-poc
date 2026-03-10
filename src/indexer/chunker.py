"""AST-based code chunker.

Parses source files into semantic chunks (functions, classes, methods)
using Python's ``ast`` module.  Non-Python files fall back to a
line-based splitting strategy.

Each chunk captures:
  - file path, line range, chunk type, name
  - full source code of that chunk
  - docstring (if present)
  - parent class (for methods)
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


# ── Chunk data class ─────────────────────────────────────────────────────
@dataclass
class CodeChunk:
    """A single semantic unit of code."""

    file_path: str
    chunk_type: str          # "function", "class", "method", "module_header", "block"
    name: str                # e.g. "MyClass", "MyClass.my_method", "helper_func"
    start_line: int
    end_line: int
    content: str             # actual source code
    docstring: str = ""
    language: str = "python"
    parent: str = ""         # parent class name (for methods)
    decorators: list[str] = field(default_factory=list)

    @property
    def qualified_name(self) -> str:
        """Full dotted name, e.g. ``MyClass.my_method``."""
        if self.parent:
            return f"{self.parent}.{self.name}"
        return self.name

    @property
    def line_count(self) -> int:
        return self.end_line - self.start_line + 1

    def summary(self) -> str:
        """One-line summary for search results."""
        doc_preview = self.docstring.split("\n")[0][:80] if self.docstring else ""
        return (
            f"[{self.chunk_type}] {self.qualified_name} "
            f"({self.file_path}:{self.start_line}-{self.end_line})"
            + (f" — {doc_preview}" if doc_preview else "")
        )


# ── Language detection ───────────────────────────────────────────────────
EXTENSION_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
}


def detect_language(path: Path) -> str:
    return EXTENSION_LANGUAGE.get(path.suffix.lower(), "unknown")


# ── Python AST chunker ──────────────────────────────────────────────────
def _get_decorators(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> list[str]:
    """Extract decorator names from an AST node."""
    decorators: list[str] = []
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name):
            decorators.append(dec.id)
        elif isinstance(dec, ast.Attribute):
            decorators.append(ast.dump(dec))
        elif isinstance(dec, ast.Call):
            if isinstance(dec.func, ast.Name):
                decorators.append(dec.func.id)
            elif isinstance(dec.func, ast.Attribute):
                decorators.append(ast.dump(dec.func))
    return decorators


def _get_docstring(node: ast.AST) -> str:
    """Extract docstring from a function or class node."""
    try:
        return ast.get_docstring(node) or ""
    except Exception:
        return ""


def _node_end_line(node: ast.AST) -> int:
    """Get the end line of an AST node."""
    return getattr(node, "end_lineno", getattr(node, "lineno", 0))


def chunk_python(source: str, file_path: str) -> list[CodeChunk]:
    """Parse Python source into semantic chunks via AST."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        logger.warning("SyntaxError in %s: %s — falling back to block chunking", file_path, exc)
        return chunk_by_lines(source, file_path, language="python")

    lines = source.splitlines()
    chunks: list[CodeChunk] = []

    # ── Module-level header (imports, constants, etc.) ───────────────
    first_def_line = None
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            first_def_line = node.lineno
            break

    if first_def_line and first_def_line > 1:
        header_lines = lines[: first_def_line - 1]
        header_content = "\n".join(header_lines).strip()
        if header_content:
            chunks.append(CodeChunk(
                file_path=file_path,
                chunk_type="module_header",
                name="<imports>",
                start_line=1,
                end_line=first_def_line - 1,
                content=header_content,
                language="python",
            ))

    # ── Top-level functions and classes ──────────────────────────────
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = _node_end_line(node)
            content = "\n".join(lines[node.lineno - 1 : end])
            chunks.append(CodeChunk(
                file_path=file_path,
                chunk_type="function",
                name=node.name,
                start_line=node.lineno,
                end_line=end,
                content=content,
                docstring=_get_docstring(node),
                language="python",
                decorators=_get_decorators(node),
            ))

        elif isinstance(node, ast.ClassDef):
            end = _node_end_line(node)
            content = "\n".join(lines[node.lineno - 1 : end])
            chunks.append(CodeChunk(
                file_path=file_path,
                chunk_type="class",
                name=node.name,
                start_line=node.lineno,
                end_line=end,
                content=content,
                docstring=_get_docstring(node),
                language="python",
                decorators=_get_decorators(node),
            ))

            # ── Methods inside the class ────────────────────────────
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    m_end = _node_end_line(child)
                    m_content = "\n".join(lines[child.lineno - 1 : m_end])
                    chunks.append(CodeChunk(
                        file_path=file_path,
                        chunk_type="method",
                        name=child.name,
                        start_line=child.lineno,
                        end_line=m_end,
                        content=m_content,
                        docstring=_get_docstring(child),
                        language="python",
                        parent=node.name,
                        decorators=_get_decorators(child),
                    ))

    # If no chunks were extracted (e.g. script with no functions/classes),
    # treat the whole file as a single block.
    if not chunks:
        chunks = chunk_by_lines(source, file_path, language="python")

    return chunks


# ── Generic line-based chunker (fallback) ────────────────────────────────
def chunk_by_lines(
    source: str,
    file_path: str,
    *,
    language: str = "unknown",
    max_lines: int = 80,
) -> list[CodeChunk]:
    """Split source into fixed-size line blocks for non-Python files."""
    lines = source.splitlines()
    chunks: list[CodeChunk] = []

    for i in range(0, len(lines), max_lines):
        block = lines[i : i + max_lines]
        content = "\n".join(block)
        chunks.append(CodeChunk(
            file_path=file_path,
            chunk_type="block",
            name=f"<block:{i + 1}-{i + len(block)}>",
            start_line=i + 1,
            end_line=i + len(block),
            content=content,
            language=language,
        ))

    return chunks


# ── Public API ───────────────────────────────────────────────────────────
def chunk_file(path: Path) -> list[CodeChunk]:
    """Chunk a single file — uses AST for Python, line-based otherwise."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        logger.warning("Cannot read %s: %s", path, exc)
        return []

    if not source.strip():
        return []

    language = detect_language(path)
    file_path = str(path)

    if language == "python":
        return chunk_python(source, file_path)
    else:
        return chunk_by_lines(source, file_path, language=language)
