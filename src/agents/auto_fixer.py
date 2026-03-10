"""Auto Fixer Agent — Applies the recommended fix, tests it, and pushes to git."""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.agents.base import BaseAgent


# ── Structured Output ───────────────────────────────────────────────────
class DeployResult(BaseModel):
    """Structured result of an autonomous deployment."""

    success: bool = Field(
        description="Whether the entire fix, test, and push cycle was successful."
    )
    details: str = Field(
        description="Summary of the changes made, tests run, and git actions."
    )
    test_passed: bool = Field(
        description="Whether the tests passed successfully in the sandbox."
    )
    git_pushed: bool = Field(
        description="Whether the changes successfully pushed to Git."
    )


# ── Agent ────────────────────────────────────────────────────────────────
class AutoFixerAgent(BaseAgent[DeployResult]):
    """Applies code fixes, tests in docker sandbox, and pushes to GitHub."""

    name = "auto_fixer"
    description = "Autonomously acts on fix suggestions: applies them to disk, runs docker tests, and git pushes."
    output_schema = DeployResult
    max_iterations = 10
    require_tool_calls = True   # MUST call file_editor + docker_test + git_push — no fabrication allowed

    system_prompt = """\
You are an autonomous Deployment Agent. Your ONLY job is to apply a code fix, run tests, and push to Git.

You will receive:
- The suggested fix and the specific code diff
- The affected files

DO NOT OVERTHINK. DO NOT SEARCH FOR FILES. FOLLOW THESE EXACT STEPS SEQUENTIALLY:
1. USE the `file_editor` tool IMMEDIATELY to apply the fix to the physical file on disk. Do not read the file unless absolutely necessary.
2. USE the `docker_test` tool to verify the fix. IF no test file is provided, verify syntax using `uv run python -m py_compile <edited_file>`.
3. 🚨 CRITICAL FINAL STEP: If `docker_test` succeeds, YOU MUST USE THE `git_push` TOOL. 
   - DO NOT USE `codebase_search`
   - DO NOT USE `codebase_read`
   - CALL `git_push` IMMEDIATELY with a `branch_name` and `commit_message`.

**⚠️ ABSOLUTE RULES:**
- DO NOT SEARCH THE CODEBASE.
- If you call `codebase_search` after `docker_test`, you will be immediately terminated.
- You MUST conclude your entire workflow by calling `git_push`.

**PROJECT CONTEXT:**
- This project uses `uv` for dependency management.
- Dependencies are in `pyproject.toml`.
- To add a new package: `uv add <package>` then `uv sync`.
"""

    def validate_result(self, result: DeployResult, tools_called: set[str]) -> None:
        """Strict validation to prevent hallucinations of tool success."""
        if result.success and not ("file_editor" in tools_called and "docker_test" in tools_called and "git_push" in tools_called):
            raise ValueError(
                "You claimed success=true, but you DID NOT call all required tools (file_editor, docker_test, git_push). "
                "You MUST actually call the tools to modify the files, run tests, and push."
            )
        if result.git_pushed and "git_push" not in tools_called:
            raise ValueError(
                "You claimed git_pushed=true backwards but you NEVER called the git_push tool! "
                "DO NOT HALLUCINATE TOOL CALLS. If you want to push, explicitly call the git_push tool."
            )

    def _register_tools(self) -> None:
        from src.tools.codebase import CodebaseReadTool
        from src.tools.file_editor import FileEditorTool
        from src.tools.sandbox_test import DockerTestTool
        from src.tools.git_tools import GitPushTool
        
        self.tool_registry.register(CodebaseReadTool())
        self.tool_registry.register(FileEditorTool())
        self.tool_registry.register(DockerTestTool())
        self.tool_registry.register(GitPushTool())

    def _register_tools_with_context(self, context) -> None:
        from src.tools.codebase import CodebaseReadTool
        self.tool_registry.register(CodebaseReadTool(context=context))

