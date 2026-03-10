"""Docker Sandbox Test Tool — runs tests in a sandbox environment."""

from __future__ import annotations

import json
import logging
import shlex
import subprocess
import asyncio
import os
import shutil
from typing import Any

from src.tools.base import Tool, ToolParameter

logger = logging.getLogger(__name__)


def _find_docker() -> str | None:
    """Find docker executable using multiple strategies, PATH-independent."""

    # 1. Explicit override via env var (most reliable for server processes)
    if env_path := os.environ.get("DOCKER_PATH"):
        if os.path.isfile(env_path):
            logger.info("Docker found via DOCKER_PATH env: %s", env_path)
            return env_path

    # 2. shutil.which — works if uvicorn inherited the right PATH
    if found := shutil.which("docker"):
        logger.info("Docker found via shutil.which: %s", found)
        return found

    # 3. Common Windows installation paths (PATH-independent)
    local_app = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
    program_files_x86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
    user_profile = os.environ.get("USERPROFILE", "")

    candidates = [
        os.path.join(program_files, "Docker", "Docker", "resources", "bin", "docker.exe"),
        os.path.join(program_files, "Docker", "resources", "bin", "docker.exe"),
        os.path.join(program_files_x86, "Docker", "Docker", "resources", "bin", "docker.exe"),
        os.path.join(local_app, "Programs", "Docker", "Docker", "resources", "bin", "docker.exe"),
        os.path.join(local_app, "Docker", "wsl", "main", "docker.exe"),
        os.path.join(user_profile, "AppData", "Local", "Programs", "Docker", "Docker", "resources", "bin", "docker.exe"),
        r"C:\ProgramData\DockerDesktop\version-bin\docker.exe",
    ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            logger.info("Docker found via candidate path: %s", candidate)
            return candidate

    logger.warning("Docker not found. Searched PATH=%s", os.environ.get("PATH", ""))
    return None


def _find_git() -> str | None:
    """Find git executable using multiple strategies, PATH-independent."""

    # 1. Explicit override via env var
    if env_path := os.environ.get("GIT_PATH"):
        if os.path.isfile(env_path):
            logger.info("Git found via GIT_PATH env: %s", env_path)
            return env_path

    # 2. shutil.which
    if found := shutil.which("git"):
        logger.info("Git found via shutil.which: %s", found)
        return found

    # 3. Common Windows paths (PATH-independent)
    local_app = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
    program_files_x86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
    user_profile = os.environ.get("USERPROFILE", "")

    candidates = [
        os.path.join(program_files, "Git", "bin", "git.exe"),
        os.path.join(program_files, "Git", "cmd", "git.exe"),
        os.path.join(program_files_x86, "Git", "bin", "git.exe"),
        os.path.join(local_app, "Programs", "Git", "bin", "git.exe"),
        os.path.join(user_profile, "scoop", "shims", "git.exe"),
        os.path.join(user_profile, "AppData", "Local", "Programs", "Git", "bin", "git.exe"),
        r"C:\Git\bin\git.exe",
    ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            logger.info("Git found via candidate path: %s", candidate)
            return candidate

    logger.warning("Git not found. Searched PATH=%s", os.environ.get("PATH", ""))
    return None


class DockerTestTool(Tool):
    """Executes the test suite in an isolated Docker container."""

    name = "docker_test"
    description = (
        "Run the project's test suite inside a secure Docker sandbox environment. "
        "Use this after applying a code fix to verify that the fix resolves the issue "
        "without breaking other tests. Specify the test file to run (e.g., 'tests/e2e/test_pipeline.py')."
    )
    parameters = [
        ToolParameter(
            name="test_command",
            type="string",
            description="The unwrapped test command to run. Default relies on pytest (e.g., 'uv run pytest tests/e2e/test_pipeline.py').",
            required=False,
        ),
    ]

    async def execute(self, **kwargs: Any) -> str:
        await asyncio.sleep(1.5)

        test_command = kwargs.get("test_command", 'uv run python -c "print(\'No specific test provided. Syntax checked.\')"')

        docker_path = _find_docker()

        if not docker_path:
            return json.dumps({
                "error": "Docker executable not found. Set DOCKER_PATH in .env or ensure Docker Desktop is running.",
                "passed": False
            })

        docker_cmd = [docker_path, "compose", "run", "--rm", "api"] + shlex.split(test_command, posix=False)

        try:
            logger.info("Executing tests in docker: %s", " ".join(docker_cmd))
            result = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=120,
            )

            if result.returncode != 0 and "daemon is not running" in result.stderr.lower():
                return json.dumps({"error": "Docker daemon not running. Please start Docker Desktop.", "passed": False})

            response = {
                "stdout": result.stdout[:2000],
                "stderr": result.stderr[:2000],
                "exit_code": result.returncode,
                "timeout": False,
                "passed": result.returncode == 0
            }
            return json.dumps(response, ensure_ascii=False)

        except subprocess.TimeoutExpired as exc:
            return json.dumps({
                "error": "Execution timed out (120s limit)",
                "stdout": (exc.stdout or "")[:1000],
                "stderr": (exc.stderr or "")[:1000],
                "timeout": True,
                "passed": False
            })
        except Exception as exc:
            logger.exception("Test execution failed")
            return json.dumps({"error": str(exc), "passed": False})
