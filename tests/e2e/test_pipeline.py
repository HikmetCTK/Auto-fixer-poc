"""End-to-end tests for the Multi-Agent pipeline.

Note: Requires real LLM keys and indexed codebase.
"""

from __future__ import annotations

import pytest
import os
from src.agents.orchestrator import Orchestrator
from src.agents.base import AgentContext
from src.observability.langfuse_setup import setup_langfuse

@pytest.mark.skipif(not os.getenv("CEREBRAS_API_KEY"), reason="CEREBRAS_API_KEY not set")
@pytest.mark.asyncio
async def test_e2e_pipeline_simulation():
    """Runs the full pipeline against a simulated error in the codebase itself."""
    # Ensure Langfuse traces are sent during tests
    setup_langfuse()
    
    orchestrator = Orchestrator(project_path=".")
    
    # A real-ish error from this project
    error_output = """
    Traceback (most recent call last):
      File "src/main.py", line 51, in analyze_error
        from src.indexer.indexer import CodebaseIndex
      File "src/indexer/indexer.py", line 12, in <module>
        try:\n    import faiss\nexcept Exception:\n    class _FaissStub:\n        __version__ = "0.0.0-stub"\n    faiss = _FaissStub()
    ModuleNotFoundError: No module named 'faiss'
    """
    
    context = AgentContext(session_id="test-e2e")
    result = await orchestrator.run(error_output, context, auto_apply_fix=True)
    
    assert result.error_analysis.error_type == "ModuleNotFoundError"
    assert result.report.title != ""
    assert result.fix.suggested_fix != ""
    print(f"\nE2E Report Title: {result.report.title}")
    print(f"Fix Proposed: {result.fix.risk_level} risk")
    if result.deploy:
        print(f"\nAuto-Deploy Success: {result.deploy.success}")
        print(f"Deploy Details: {result.deploy.details[:100]}...")
