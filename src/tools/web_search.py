"""Web Search Tool — implementation using Tavily API."""

from __future__ import annotations

import json
import logging
from typing import Any

from tavily import TavilyClient

from src.config.settings import settings
from src.tools.base import Tool, ToolParameter

logger = logging.getLogger(__name__)


class WebSearchTool(Tool):
    """Search the web for information using Tavily."""

    name = "web_search"
    description = (
        "Search the web for information, similar issues, solutions, and documentation. "
        "Use this for researching software errors, finding Stack Overflow posts, "
        "or looking up specific library documentation."
    )
    parameters = [
        ToolParameter(
            name="query",
            type="string",
            description="The search query. Keep it focused (e.g., 'Python UnicodeDecodeError utf-8 fix').",
            required=True,
        ),
    ]

    def __init__(self) -> None:
        self.client = None
        if settings.tavily_api_key:
            self.client = TavilyClient(api_key=settings.tavily_api_key)

    async def execute(self, **kwargs: Any) -> str:
        if not self.client:
            return json.dumps({"error": "Tavily API key is not configured."})

        query = kwargs.get("query", "")
        depth = kwargs.get("search_depth", "basic")

        if not query:
            return json.dumps({"error": "Query is required."})

        try:
            logger.info("Tavily search → %s (depth: %s)", query, depth)
            response = self.client.search(
                query=query,
                search_depth="basic",   # always basic — advanced is overkill for our use-case
                max_results=3,          # 3 results is enough; keeps Observation short
            )

            results = []
            for result in response.get("results", []):
                snippet = result.get("content", "").strip()
                # Keep only the first 250 chars — the model needs a hint, not a full article
                snippet = snippet[:250].rsplit(" ", 1)[0] if len(snippet) > 250 else snippet
                results.append({
                    "title": result.get("title", "")[:80],  # short title
                    "url": result.get("url", ""),
                    "snippet": snippet,
                })

            return json.dumps({"results": results}, ensure_ascii=False)

        except Exception as exc:
            logger.exception("Tavily search failed")
            return json.dumps({"error": str(exc)})
