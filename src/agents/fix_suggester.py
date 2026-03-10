"""Fix Suggester Agent — proposes code fixes for identified errors.

Receives the error analysis and research results, then generates
concrete fix suggestions with risk assessments.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.agents.base import BaseAgent


# ── Structured Output ───────────────────────────────────────────────────
class AlternativeFix(BaseModel):
    """An alternative fix approach."""

    description: str = Field(description="What this alternative fix does.")
    code_snippet: str = Field(default="", description="Code change (if applicable).")
    trade_offs: str = Field(default="", description="Trade-offs of this approach.")


class FixSuggestion(BaseModel):
    """Structured fix suggestion for a bug."""

    model_config = {"frozen": False}  # allow field mutation in validate_result

    suggested_fix: str = Field(
        description="The primary recommended fix — describe what to change and where."
    )
    code_snippet: str = Field(
        default="",
        description="The actual code change (diff-style or full replacement).",
    )
    explanation: str = Field(
        description="Why this fix works — connect it back to the root cause."
    )
    risk_level: str = Field(
        description="Risk of this fix: low, medium, high. Consider side effects."
    )
    affected_files: list[str] = Field(
        default_factory=list,
        description="Files that need to be modified.",
    )
    alternative_fixes: list[AlternativeFix] = Field(
        default_factory=list,
        description="Alternative approaches if the primary fix is not suitable.",
    )
    requires_testing: bool = Field(
        default=True,
        description="Whether this fix should be validated with tests.",
    )
    test_suggestion: str = Field(
        default="",
        description="Suggested test to validate the fix.",
    )
    did_edit: bool = Field(
        default=False,
        description="Whether you actually used the file_editor tool to fix the code on disk.",
    )
    branch_name: str = Field(
        default="",
        description="Suggested branch name if you edited the code.",
    )
    commit_message: str = Field(
        default="",
        description="Suggested commit message if you edited the code.",
    )


# ── Agent ────────────────────────────────────────────────────────────────
class FixSuggesterAgent(BaseAgent[FixSuggestion]):
    """Generates fix suggestions based on error analysis and research."""

    name = "fix_suggester"
    description = "Proposes code fixes with risk assessment and alternatives."
    output_schema = FixSuggestion
    max_iterations = 15

    def validate_result(self, result: FixSuggestion, tools_called: set[str]) -> None:
        """Auto-correct did_edit if file_editor was actually called but LLM forgot to set the flag."""
        if "file_editor" in tools_called and not result.did_edit:
            # Pydantic v2: model must have frozen=False (set above) for this to work
            result.did_edit = True
            import logging
            logging.getLogger(__name__).info(
                "[fix_suggester] file_editor was called — auto-setting did_edit=True"
            )

    system_prompt = """\
You are a senior software engineer proposing and applying a bug fix.

You will receive:
- An error analysis (type, root cause, affected files, severity)
- Research results (similar issues, known solutions)
- Possibly: already-read file contents under "Already-Read Files"

## YOUR WORKFLOW (follow strictly, in order)

**STEP 1 — Check context first.**
Look at the "Already-Read Files" section in your context.
If the affected file is already there — DO NOT call `codebase_read` again. Use that content directly.

**STEP 2 — Read only if needed.**
If the file is NOT in "Already-Read Files", call `codebase_read` ONCE with the exact path.

**STEP 3 — Apply the fix immediately.**
Use `file_editor` to apply the fix directly to disk.
- `file_path`: the relative path (e.g. `src/utils/data_processor.py`)
- `target_text`: the EXACT lines to replace (copy from the file content — do NOT paraphrase)
- `replacement_text`: the corrected code

**STEP 4 — Provide Final Answer.**
Set `did_edit: true`, fill in `branch_name` and `commit_message`.

## RULES
- Do NOT call `codebase_read` more than once per file.
- Do NOT call `codebase_search` — you already have the analysis.
- Do NOT fabricate tool results.
- Make minimal, targeted changes — do not rewrite large blocks unnecessarily.

**PROJECT CONTEXT**
- This project uses `uv` for dependency management.
- Dependencies are in `pyproject.toml`, NOT `requirements.txt`.
- To install a package: `uv add <package>`.
"""

    def _register_tools(self) -> None:
        from src.tools.codebase import CodebaseReadTool
        from src.tools.file_editor import FileEditorTool
        self.tool_registry.register(CodebaseReadTool())
        self.tool_registry.register(FileEditorTool())

    def _register_tools_with_context(self, context) -> None:
        from src.tools.codebase import CodebaseReadTool
        from src.tools.file_editor import FileEditorTool
        self.tool_registry.register(CodebaseReadTool(context=context))
        self.tool_registry.register(FileEditorTool())  # keep editor registered after context re-wire
