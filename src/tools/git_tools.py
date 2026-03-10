"""Git Tool — coordinates committing and pushing to a Git repository."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from typing import Any

from src.tools.base import Tool, ToolParameter

logger = logging.getLogger(__name__)


class GitPushTool(Tool):
    """Commits and pushes changes to Git."""

    name = "git_push"
    description = (
        "Commit and push applied fixes to the remote Git repository."
        "Use this ONLY after running 'docker_test' explicitly assuring that the fix works."
    )
    parameters = [
        ToolParameter(
            name="branch_name",
            type="string",
            description="The name of the new branch to create for this fix. Should be concise (e.g., 'fix/missing-dependency').",
            required=True,
        ),
        ToolParameter(
            name="commit_message",
            type="string",
            description="The message for the 'git commit' explicitly highlighting what was fixed.",
            required=True,
        ),
        ToolParameter(
            name="files_to_commit",
            type="string",
            description="Comma-separated paths to files that were edited. e.g. 'src/agents/orchestrator.py'",
            required=False,
        ),
    ]

    async def execute(self, **kwargs: Any) -> str:
        commit_message = kwargs.get("commit_message", "fix: Autonomously applied by agent")
        files_to_commit = kwargs.get("files_to_commit", "")
        branch_name = kwargs.get("branch_name", "fix/autonomous-patch")
        files_list = [f.strip() for f in files_to_commit.split(",")] if files_to_commit else ["."]

        # Resolve git executable — PATH-independent (uses PROGRAMFILES env vars + GIT_PATH override)
        from src.tools.sandbox_test import _find_git
        git_path = _find_git()
        if not git_path:
            return json.dumps({"error": "git executable not found. Set GIT_PATH in .env or install Git.", "passed": False})

        try:
            # 1. Create and checkout a new branch
            logger.info("Creating branch: %s", branch_name)
            subprocess.run([git_path, "checkout", "-B", branch_name], check=True, capture_output=True, text=True, encoding="utf-8")

            # 2. Add files to git index
            logger.info("Adding files to Git: %s", files_list)
            for f in files_list:
                subprocess.run([git_path, "add", f], check=True, capture_output=True, text=True, encoding="utf-8")

            # 3. Commit changes
            logger.info("Committing changes: '%s'", commit_message)
            commit_result = subprocess.run(
                [git_path, "commit", "-m", commit_message],
                capture_output=True, text=True, encoding="utf-8",
            )

            if "nothing to commit" in commit_result.stdout:
                subprocess.run([git_path, "checkout", "-"], check=False, capture_output=True)
                return json.dumps({"status": "warning", "message": "Nothing to commit. Ensure the files were modified.", "passed": False})

            # 4. Push branch to remote
            logger.info("Pushing branch %s to origin", branch_name)
            push_result = subprocess.run(
                [git_path, "push", "--set-upstream", "origin", branch_name],
                capture_output=True, text=True, encoding="utf-8",
            )

            pr_message = f"Branch '{branch_name}' pushed. Open a PR on GitHub to merge into main."
            response = {
                "stdout": push_result.stdout,
                "stderr": push_result.stderr,
                "pr_instructions": pr_message,
                "exit_code": push_result.returncode,
                "passed": push_result.returncode == 0,
            }
            subprocess.run([git_path, "checkout", "-"], check=False, capture_output=True)
            return json.dumps(response, ensure_ascii=False)

        except subprocess.CalledProcessError as exc:
            logger.exception("Git command failed")
            return json.dumps({
                "error": "Git command failed.",
                "stdout": exc.stdout,
                "stderr": exc.stderr,
                "passed": False,
            })
        except Exception as exc:
            logger.exception("Unexpected error in Git tool")
            return json.dumps({"error": str(exc), "passed": False})
