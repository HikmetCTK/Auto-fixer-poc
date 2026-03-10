"""Error Analyzer Agent — parses stack traces and identifies root causes.

This is the first agent in the bug-fix workflow.  It receives raw error
output (stack trace, log lines, error message) and produces a structured
``ErrorAnalysis``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.agents.base import BaseAgent


# ── Structured Output ───────────────────────────────────────────────────
class ErrorAnalysis(BaseModel):
    """Structured analysis of a software error."""

    error_type: str = Field(
        description="The exception/error class, e.g. 'KeyError', 'NullPointerException', 'ConnectionRefusedError'."
    )
    root_cause: str = Field(
        description="Concise explanation of WHY the error happened."
    )
    affected_files: list[str] = Field(
        default_factory=list,
        description="List of source files involved in the error (parsed from stack trace).",
    )
    test_files: list[str] = Field(
        default_factory=list,
        description="List of test files associated with the affected files (found via search or naming conventions).",
    )
    severity: str = Field(
        description="One of: critical, high, medium, low."
    )
    stack_summary: str = Field(
        description="A human-readable summary of the stack trace, highlighting the most relevant frames."
    )
    language: str = Field(
        default="unknown",
        description="The programming language of the code that produced the error.",
    )
    suggested_search_queries: list[str] = Field(
        default_factory=list,
        description="2-3 web search queries that would help find solutions for this error.",
    )


# ── Agent ────────────────────────────────────────────────────────────────
class ErrorAnalyzerAgent(BaseAgent[ErrorAnalysis]):
    """Analyzes error output and produces a structured ErrorAnalysis."""

    name = "error_analyzer"
    description = "Analyzes stack traces and error messages to identify root causes and severity."
    output_schema = ErrorAnalysis

    system_prompt = """\
You are an expert software debugger.  You will receive raw error output
(stack traces, log lines, error messages) from a software project.

You have access to the project's **indexed codebase** via these tools:
- **codebase_search**: Search for keywords/patterns across all source files.
- **codebase_read**: Read the contents of a specific file (or line range).
- **codebase_list**: List files in the project to understand the structure.

**Process:**
1. Parse the stack trace to identify the error type and raw affected files.
2. Use **codebase_search** to locate the exact path of the error origin in the actual code.
3. Use **codebase_search** or **codebase_list** to find the corresponding test file for the affected file (e.g. searching for `test_data_parser.py` if `data_parser.py` is affected).
4. Use **codebase_read** to inspect the relevant code around the error.
5. Determine the root cause from the actual source code.
5. Assess severity (critical / high / medium / low).
6. Summarize the findings with code references.
7. Suggest 2-3 web search queries that would help find solutions.

Be precise and concise.  Base your analysis on the ACTUAL source code.
"""

    def _register_tools(self) -> None:
        from src.tools.codebase import CodebaseSearchTool, CodebaseReadTool, CodebaseListTool
        self.tool_registry.register(CodebaseSearchTool())
        self.tool_registry.register(CodebaseReadTool())
        self.tool_registry.register(CodebaseListTool())

    def _register_tools_with_context(self, context) -> None:
        from src.tools.codebase import CodebaseReadTool
        # Replace the context-unaware instance with one that has the shared file cache
        self.tool_registry.register(CodebaseReadTool(context=context))

