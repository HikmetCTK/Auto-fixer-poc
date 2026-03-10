"""Tool base class and registry.

Every tool the agents can use inherits from ``Tool`` and implements
``execute()``.  The ``ToolRegistry`` collects tools and converts them to
the OpenAI-compatible function-calling schema that LiteLLM expects.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ── Parameter schema helper ─────────────────────────────────────────────
class ToolParameter(BaseModel):
    """Describes a single parameter for a tool."""

    name: str
    type: str = "string"
    description: str = ""
    required: bool = True
    enum: list[str] | None = None


# ── Base Tool ────────────────────────────────────────────────────────────
class Tool(ABC):
    """Abstract base for all tools.

    Subclasses must set ``name``, ``description``, ``parameters`` and
    implement ``execute(**kwargs)``.
    """

    name: str
    description: str
    parameters: list[ToolParameter] = []

    @abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        """Run the tool and return a *string* result.

        Tools always return strings so they can be injected back into the
        LLM conversation as a ``tool`` message.
        """

    # ── OpenAI function-calling schema ──────────────────────────────────
    def to_openai_schema(self) -> dict[str, Any]:
        """Convert to the ``tools`` format LiteLLM / OpenAI expects."""
        properties: dict[str, Any] = {}
        required: list[str] = []

        for p in self.parameters:
            prop: dict[str, Any] = {"type": p.type, "description": p.description}
            if p.enum:
                prop["enum"] = p.enum
            properties[p.name] = prop
            if p.required:
                required.append(p.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

    # ── ReAct Text Schema ───────────────────────────────────────────────────
    def to_text_schema(self) -> str:
        """Convert to a text description for ReAct prompts."""
        desc_lines = [f"Tool Name: {self.name}", f"Description: {self.description}"]
        if self.parameters:
            desc_lines.append("Arguments (JSON object keys):")
            for p in self.parameters:
                req = "required" if p.required else "optional"
                enum_str = f" (enum: {p.enum})" if p.enum else ""
                desc_lines.append(f"  - {p.name} ({p.type}, {req}): {p.description}{enum_str}")
        else:
            desc_lines.append("Arguments: None")
        return "\n".join(desc_lines)


# ── Tool Registry ───────────────────────────────────────────────────────
class ToolRegistry:
    """Holds a set of tools and dispatches calls by function name."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    @property
    def schemas(self) -> list[dict[str, Any]]:
        """OpenAI-compatible tool schemas for all registered tools."""
        return [t.to_openai_schema() for t in self._tools.values()]

    @property
    def text_schemas(self) -> str:
        """Text descriptions of all registered tools."""
        if not self._tools:
            return "No tools available."
        return "\n\n".join(t.to_text_schema() for t in self._tools.values())

    async def call(self, name: str, arguments: str | dict) -> str:
        """Execute a tool by name with the given arguments JSON."""
        tool = self._tools.get(name)
        if tool is None:
            return json.dumps({"error": f"Unknown tool: {name}"})

        kwargs = {}
        if isinstance(arguments, str):
            try:
                # Try standard parsing
                kwargs = json.loads(arguments)
            except json.JSONDecodeError:
                try:
                    # Sometimes the LLM wraps the JSON in a string, e.g. "{\"args\": 1}"
                    # Use literal_eval to strip the outer quotes if present
                    import ast
                    evaluated = ast.literal_eval(arguments)
                    if isinstance(evaluated, str):
                        kwargs = json.loads(evaluated)
                    elif isinstance(evaluated, dict):
                        kwargs = evaluated
                except Exception:
                    kwargs = {"raw": arguments}
        elif isinstance(arguments, dict):
            kwargs = arguments

        try:
            logger.info("Tool call → %s(%s)", name, kwargs)
            result = await tool.execute(**kwargs)
            logger.info("Tool result ← %s: %s chars", name, len(result))
            return result
        except Exception as exc:
            logger.exception("Tool %s failed", name)
            return json.dumps({"error": str(exc)})

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
