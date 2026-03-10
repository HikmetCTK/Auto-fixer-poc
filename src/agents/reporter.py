"""Reporter Agent — formats the final bug report and sends notifications.

Combines the outputs of all previous agents into a polished, actionable
report suitable for Slack, email, or a dashboard.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.agents.base import BaseAgent


# ── Structured Output ───────────────────────────────────────────────────
class ReportOutput(BaseModel):
    """Final bug report ready for stakeholders."""

    title: str = Field(
        description="Short, descriptive title for the bug report (max ~80 chars)."
    )
    severity: str = Field(
        description="Overall severity: critical, high, medium, low."
    )
    summary: str = Field(
        description="Executive summary — 2-3 sentences explaining the bug and proposed fix."
    )
    error_details: str = Field(
        description="Technical details of the error (type, stack summary)."
    )
    root_cause: str = Field(
        description="Why the error occurred."
    )
    proposed_fix: str = Field(
        description="The recommended fix with code snippets if applicable."
    )
    risk_assessment: str = Field(
        description="Risk level of the fix and potential side effects."
    )
    references: list[str] = Field(
        default_factory=list,
        description="Useful links (Stack Overflow, docs, GitHub issues).",
    )
    next_steps: list[str] = Field(
        default_factory=list,
        description="Actionable next steps for the engineering team.",
    )


# ── Agent ────────────────────────────────────────────────────────────────
class ReporterAgent(BaseAgent[ReportOutput]):
    """Creates a polished bug report from all agent outputs."""

    name = "reporter"
    description = "Formats bug analysis, research, and fix suggestions into a final report."
    output_schema = ReportOutput

    system_prompt = """\
You are a technical writer creating a bug report for an engineering team.

You will receive the combined outputs of three agents:
- Error Analyzer: error type, root cause, severity, stack summary
- Research Agent: similar issues found, known solutions
- Fix Suggester: proposed fix, risk level, alternatives

Your job:
1. Write a clear, concise **title** (max ~80 characters).
2. Write an **executive summary** (2-3 sentences).
3. Include all **technical details** in a structured way.
4. List concrete **next steps** for the team.

The report should be immediately actionable — an engineer reading it
should know exactly what happened and what to do about it.
"""

    def _register_tools(self) -> None:
        from src.tools.notifier import NotificationTool
        self.tool_registry.register(NotificationTool())
