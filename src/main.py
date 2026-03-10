"""FastAPI application — HTTP gateway only.

Handles incoming webhooks / API calls and dispatches work to the
orchestrator (and later Temporal).
"""

from __future__ import annotations

import logging
import os
import uuid
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.agents.base import AgentContext
from src.agents.orchestrator import Orchestrator
from src.api.events import manager

logger = logging.getLogger(__name__)

# ── Lifespan ─────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """App startup / shutdown hooks."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s │ %(name)-30s │ %(levelname)-5s │ %(message)s",
    )
    from src.observability.langfuse_setup import setup_langfuse
    setup_langfuse()
    logger.info("Bug Detective API starting")
    yield
    logger.info("Bug Detective API shutting down")


app = FastAPI(
    title="AI Bug Detective",
    description="Multi-agent error analysis and fix suggestion system",
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS — allow the Next.js dev server ──────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response schemas ───────────────────────────────────────────
class AnalyzeRequest(BaseModel):
    """Incoming error analysis request."""

    error_output: str = Field(
        description="Raw error output — stack trace, log lines, error message."
    )
    project_path: str = Field(default="", description="Absolute path to the project root to index.")
    project_name: str = Field(default="", description="Name of the project (optional context).")
    extra_context: str = Field(default="", description="Any extra context to help the agents.")
    session_id_override: str = Field(default="", description="Optional: client-provided session UUID for WebSocket targeting.")
    auto_apply_fix: bool = Field(default=False, description="If true, automatically applies the suggested fix and runs Docker tests.")
    test_command: str = Field(
        default="",
        description="Optional Docker sandbox test command, e.g. 'uv run pytest tests/e2e/test_pipeline.py'.",
    )


class AnalyzeResponse(BaseModel):
    """Full pipeline result."""

    session_id: str
    title: str
    severity: str
    summary: str
    error_details: str
    root_cause: str
    proposed_fix: str
    risk_assessment: str
    references: list[str]
    next_steps: list[str]


# ── Routes ───────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze_error(request: AnalyzeRequest):
    """Run the full bug-fix pipeline on the provided error output."""
    session_id = request.session_id_override or str(uuid.uuid4())
    logger.info("POST /analyze — session=%s", session_id)

    context = AgentContext(
        session_id=session_id,
        state={
            "project_name": request.project_name,
        },
    )

    # Build the input — combine error output with any extra context
    user_input = request.error_output
    if request.project_name:
        user_input = f"Project: {request.project_name}\n\n{user_input}"
    if request.extra_context:
        user_input = f"{user_input}\n\nExtra context: {request.extra_context}"

    try:
        orchestrator = Orchestrator(project_path=request.project_path or os.getcwd())
        result = await orchestrator.run(
            user_input,
            context,
            auto_apply_fix=request.auto_apply_fix,
            test_command=request.test_command,
        )
    except Exception as exc:
        logger.exception("Pipeline failed for session=%s", session_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    report = result.report
    return AnalyzeResponse(
        session_id=session_id,
        title=report.title,
        severity=report.severity,
        summary=report.summary,
        error_details=report.error_details,
        root_cause=report.root_cause,
        proposed_fix=report.proposed_fix,
        risk_assessment=report.risk_assessment,
        references=report.references,
        next_steps=report.next_steps,
    )


@app.websocket("/ws/events/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for real-time agent event streaming."""
    await manager.connect(websocket, session_id)
    try:
        while True:
            # Keep connection alive; clients generally just listen,
            # but we need to receive to handle disconnects elegantly.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, session_id)
