"""Notification Tool — sends bug reports to Slack or simulated email."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from src.tools.base import Tool, ToolParameter

logger = logging.getLogger(__name__)


class NotificationTool(Tool):
    """Sends notifications to Slack webhooks or logs them as simulated emails."""

    name = "notify"
    description = (
        "Send a notification with the final bug report to stakeholders. "
        "Supports Slack webhooks. If no webhook is configured, it logs the message to the console."
    )
    parameters = [
        ToolParameter(
            name="channel",
            type="string",
            description="The channel/target to notify: 'slack' or 'email' (default: 'slack').",
            required=False,
            enum=["slack", "email"],
        ),
        ToolParameter(
            name="title",
            type="string",
            description="Short title for the notification.",
            required=True,
        ),
        ToolParameter(
            name="summary",
            type="string",
            description="A concise summary of the bug and fix.",
            required=True,
        ),
        ToolParameter(
            name="webhook_url",
            type="string",
            description="Optional Slack webhook URL. If omitted, uses default from config.",
            required=False,
        ),
    ]

    async def execute(self, **kwargs: Any) -> str:
        channel = kwargs.get("channel", "slack")
        title = kwargs.get("title", "Bug Detective Report")
        summary = kwargs.get("summary", "")
        webhook_url = kwargs.get("webhook_url")

        if not summary:
            return json.dumps({"error": "Summary is required."})

        if channel == "slack":
            if not webhook_url:
                # In a real app, you'd get this from settings
                logger.info("[SIMULATED SLACK] %s: %s", title, summary)
                return json.dumps({"status": "success", "message": "Simulated Slack notification sent."})

            try:
                payload = {
                    "text": f"* {title} *\n\n{summary}",
                }
                async with httpx.AsyncClient() as client:
                    resp = await client.post(webhook_url, json=payload)
                    resp.raise_for_status()

                return json.dumps({"status": "success", "message": "Slack notification sent."})
            except Exception as exc:
                logger.error("Slack notification failed: %s", exc)
                return json.dumps({"error": str(exc)})

        else:  # email
            logger.info("[SIMULATED EMAIL] %s\n\n%s", title, summary)
            return json.dumps({"status": "success", "message": "Simulated Email notification sent."})
