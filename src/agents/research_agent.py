"""Research Agent — searches the web for solutions to errors.

Uses the Web Search tool to find relevant Stack Overflow posts, GitHub
issues, blog articles, and documentation pages, then synthesises the
findings into a structured ``ResearchResult``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.agents.base import BaseAgent


# ── Structured Output ───────────────────────────────────────────────────
class SimilarIssue(BaseModel):
    """A single similar issue found during research."""

    title: str = Field(description="Title or summary of the issue. Max 100 chars.", max_length=100)
    url: str = Field(description="URL of the source.", max_length=200)
    relevance: str = Field(description="How relevant this is: high, medium, low.")
    summary: str = Field(description="Brief 1-2 sentence summary. Max 200 chars.", max_length=200)


class ResearchResult(BaseModel):
    """Structured output of web research on an error."""

    similar_issues: list[SimilarIssue] = Field(
        default_factory=list,
        description="Max 3 similar issues found on the web.",
        max_length=3,
    )
    solutions_found: list[str] = Field(
        default_factory=list,
        description="Max 3 concrete solution approaches found. Each max 200 chars.",
        max_length=3,
    )
    references: list[str] = Field(
        default_factory=list,
        description="Max 3 URLs of the most useful references.",
        max_length=3,
    )
    confidence: str = Field(
        description="How confident are we that a good solution was found: high, medium, low."
    )
    summary: str = Field(
        description="Overall summary of research findings. Max 300 chars.",
        max_length=300,
    )


# ── Agent ────────────────────────────────────────────────────────────────
class ResearchAgent(BaseAgent[ResearchResult]):
    """Researches errors on the web and returns structured findings."""

    name = "research_agent"
    description = "Searches the web for solutions to software errors and synthesises findings."
    output_schema = ResearchResult
    max_iterations = 8

    system_prompt = """\
You are a senior software engineer doing research on a bug.

You will receive an error analysis (error type, root cause, stack summary)
and your job is to use the **web_search** tool to find:

1. Similar issues reported by others (Stack Overflow, GitHub Issues, forums).
2. Concrete solutions or workarounds.
3. Relevant documentation pages.

**Process:**
- Use the suggested search queries (you will receive them).
- If results are poor, reformulate and search again (max 3 searches).
- Synthesise all findings into a structured ResearchResult.

Be thorough but efficient.  Prefer official documentation and highly-voted
answers.
"""

    def _register_tools(self) -> None:
        from src.tools.web_search import WebSearchTool
        self.tool_registry.register(WebSearchTool())
