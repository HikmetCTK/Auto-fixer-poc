"""Code Executor Tool — runs Python code in a sandboxed Docker container."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import uuid
from typing import Any

from src.tools.base import Tool, ToolParameter

logger = logging.getLogger(__name__)


class CodeExecutorTool(Tool):
    """Executes Python code in an isolated Docker container."""

    name = "code_executor"
    description = (
        "Execute Python code in a secure sandboxed environment to validate fixes or test logic. "
        "The environment has all project dependencies installed. "
        "Use this to verify a fix before recommending it. "
        "The tool returns the stdout and stderr of the execution."
    )
    parameters = [
        ToolParameter(
            name="code",
            type="string",
            description="The Python code to execute.",
            required=True,
        ),
        ToolParameter(
            name="file_name",
            type="string",
            description="Optional name for the temporary file (e.g. 'test_fix.py').",
            required=False,
        ),
    ]

    async def execute(self, **kwargs: Any) -> str:
        code = kwargs.get("code", "")
        file_name = kwargs.get("file_name", f"temp_{uuid.uuid4().hex[:8]}.py")

        if not code:
            return json.dumps({"error": "No code provided to execute."})

        # Locate docker executable in PATH
        docker_path = shutil.which("docker")
        
        # Fallback for Windows if not found in PATH
        if not docker_path and os.path.exists(r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"):
            docker_path = r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"

        if not docker_path:
            return json.dumps({"error": "[Errno 2] Docker executable not found in PATH or default Windows path. Is Docker Desktop running?"})

        # Create a temporary directory to host the code
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = os.path.join(tmp_dir, file_name)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(code)

            # Docker command with security constraints
            # Note: We assume the image 'bugdetective-sandbox' is built.
            # In Phase 1 we defined Dockerfile.sandbox for this.
            docker_cmd = [
                docker_path, "run", "--rm",
                "--network", "none",
                "--memory", "256m",
                "--cpus", "0.5",
                "--pids-limit", "50",
                "--cap-drop", "ALL",
                "--user", "nobody",
                "-v", f"{tmp_dir}:/workspace:ro",
                "bugdetective-sandbox",
                f"/workspace/{file_name}"
            ]

            try:
                logger.info("Executing code in sandbox → %s", file_name)
                # Run subprocess with timeout
                result = subprocess.run(
                    docker_cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=60,  # 60s timeout
                )

                response = {
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "exit_code": result.returncode,
                    "timeout": False,
                }
                return json.dumps(response, ensure_ascii=False)

            except subprocess.TimeoutExpired as exc:
                logger.warning("Code execution timed out")
                return json.dumps({
                    "error": "Execution timed out (60s limit)",
                    "stdout": exc.stdout or "",
                    "stderr": exc.stderr or "",
                    "timeout": True,
                })
            except Exception as exc:
                logger.exception("Code execution failed")
                return json.dumps({"error": str(exc)})
