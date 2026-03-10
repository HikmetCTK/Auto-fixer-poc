"""BaseAgent — the core agent abstraction.

Every agent in the system inherits from ``BaseAgent``.  It provides:

* An **agentic tool-call loop**: call the LLM → if it requests tools,
  execute them and feed results back → repeat until the LLM returns a
  final structured answer.
* **Structured output** via a Pydantic ``output_schema``.
* **Retry / max-iterations** safety to prevent infinite loops.
"""

from __future__ import annotations

import json
import logging
import re
from abc import ABC
from typing import Any, TypeVar, Generic

from pydantic import BaseModel, ConfigDict

from src.llm.router import llm_completion
from src.tools.base import ToolRegistry
from src.config.settings import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

from src.api.events import manager

# ── Agent Context ────────────────────────────────────────────────────────
class AgentContext(BaseModel):
    """Shared context passed through an agent invocation.

    Carries session-level state that any agent or tool may read/write.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    session_id: str = ""
    state: dict[str, Any] = {}
    metadata: dict[str, Any] = {}
    file_cache: dict[str, str] = {}  # shared read cache — file_path → content

    async def emit(self, event_type: str, data: dict[str, Any]) -> None:
        """Helper to emit real-time WebSocket events for the frontend UI."""
        if not self.session_id:
            return
        
        payload = {
            "type": event_type,
            "session_id": self.session_id,
            "data": data
        }
        await manager.broadcast(self.session_id, payload)


# ── Base Agent ───────────────────────────────────────────────────────────
class BaseAgent(ABC, Generic[T]):
    """Abstract agent with a tool-call loop producing a typed output.

    Subclasses must set:
      * ``name``          – unique identifier
      * ``description``   – what the agent does (used by orchestrator)
      * ``system_prompt`` – the instruction sent as the ``system`` message
      * ``output_schema`` – a Pydantic model class for the final response
    """

    name: str
    description: str
    system_prompt: str
    output_schema: type[T]

    # Defaults — override per agent if needed
    model: str | None = None            # None → use settings.default_model
    max_iterations: int = 10            # hard cap on tool-call loops
    temperature: float = 0.2
    require_tool_calls: bool = False    # if True, agent MUST call at least one tool before Final Answer

    def __init__(self) -> None:
        self.tool_registry = ToolRegistry()
        self._register_tools()

    # ── Subclass hook ────────────────────────────────────────────────────
    def _register_tools(self) -> None:
        """Override to register tools into ``self.tool_registry``."""

    def _register_tools_with_context(self, context: AgentContext) -> None:
        """Override to re-register tools that need the live context (e.g. shared cache).
        Called once per ``run()`` invocation, AFTER context is resolved.
        """

    def validate_result(self, result: T, tools_called: set[str]) -> None:
        """Override to validate the final result. Raise ValueError if invalid."""

    # ── Public entry point ───────────────────────────────────────────────
    async def run(self, user_input: str, context: AgentContext | None = None) -> T:
        """Execute the agent: LLM call → tool loop → structured output."""
        context = context or AgentContext()

        # Allow agents to wire context-aware tools (e.g. shared file cache)
        self._register_tools_with_context(context)

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._build_system_prompt(context)},
            {"role": "user", "content": user_input},
        ]

        tools = self.tool_registry.schemas or None
        has_tools = len(self.tool_registry) > 0
        is_native = settings.use_native_tool_calling and has_tools
        tools_called_count = 0  # tracks actual tool invocations this session
        tools_called: set[str] = set() # tracks WHICH tools were invoked
        last_agent_content = ""  # tracks last LLM response (not Observation messages)

        # Emit once to signal agent start
        await context.emit("agent_started", {"agent": self.name})

        for iteration in range(1, self.max_iterations + 1):
            logger.info("[%s] iteration %d", self.name, iteration)
            call_messages = list(messages)
            if iteration == self.max_iterations:
                call_messages.append({
                    "role": "user",
                    "content": (
                        "CRITICAL: You have reached the maximum number of tool calls permitted. "
                        "You MUST NOT use any more tools. You MUST now provide a Final Answer "
                        "with the strictly matching JSON schema."
                    )
                })
            elif iteration > 1:
                reminder_text = (
                    "Reminder: If you need more info, use native tools. " if is_native else
                    "Reminder: If you need more info, use Action and Action Input. "
                )
                call_messages.append({
                    "role": "user",
                    "content": (
                        f"{reminder_text}"
                        "If finished, use Final Answer: followed by ONLY the requested JSON schema. "
                        "Do NOT truncate the JSON — ensure all brackets/braces are closed. "
                        "IMPORTANT: Do NOT re-read files that are already listed under 'Already-Read Files' in your context."
                    )
                })

            response = await llm_completion(
                model=self.model,
                messages=call_messages,
                tools=tools if is_native else None,
                temperature=self.temperature,
                stream=not is_native,
                stop=None if is_native else ["Observation:", "\nObservation:", "Observation?", "\nObservation?"],
                metadata={
                    "session_id": context.session_id,
                    "agent_name": self.name,
                    **context.metadata
                }
            )

            print(f"\n\n{'='*40}\n[{self.name.upper()} - Loop {iteration}]")
            
            tool_calls = None
            if is_native:
                msg = response.choices[0].message
                content = msg.content or ""
                if content:
                    print(content)
                tool_calls = getattr(msg, "tool_calls", None)
            else:
                content_chunks = []
                async for chunk in response:
                    delta = chunk.choices[0].delta.content or ""
                    content_chunks.append(delta)
                    print(delta, end="", flush=True)
                content = "".join(content_chunks)

            last_agent_content = content  # always track the latest LLM response
            print(f"\n{'='*40}")

            if is_native and tool_calls:
                messages.append(msg.model_dump(exclude_none=True) if hasattr(msg, "model_dump") else msg)
                for tc in tool_calls:
                    act_name = getattr(tc.function, "name", "")
                    act_input = getattr(tc.function, "arguments", "{}")
                    logger.info("[%s] Native Tool Call: %s", self.name, act_name)
                    print(f"👉 Tool Triggered (Native): {act_name}\n")
                    await context.emit("tool_trigger", {"agent": self.name, "tool": act_name, "input": act_input})
                    
                    result = await self.tool_registry.call(act_name, act_input)
                    tools_called_count += 1
                    tools_called.add(act_name)

                    # Side-channel: mark file edit so orchestrator always detects it
                    # (mirrors the same logic in the ReAct path below)
                    if act_name.lower() in ("file_editor", "file_edit") and "error" not in str(result).lower():
                        context.state["file_edited"] = True

                    print(f"✅ Tool Result ({act_name}): {str(result)[:500]}...\n")
                    await context.emit("tool_result", {"agent": self.name, "tool": act_name, "result": str(result)})
                    
                    messages.append({
                        "role": "tool",
                        "tool_call_id": getattr(tc, "id", ""),
                        "name": act_name,
                        "content": str(result)
                    })
                continue

            # Guard: if model returned empty or clearly irrelevant content, force a retry
            stripped = content.strip()
            if not stripped or (len(stripped) < 20 and "Final Answer" not in stripped and "Action" not in stripped):
                logger.warning("[%s] Empty/irrelevant response at iteration %d, retrying...", self.name, iteration)
                messages.append({"role": "assistant", "content": content or "(empty)"})
                messages.append({"role": "user", "content": "Your last response was empty or irrelevant. Please continue: use Action/Action Input OR provide Final Answer with the JSON."})
                continue
            
            # ── ReAct Text Parser ───────────────────────────────────────
            # Priority: Detect Action first. If Action exists, execute it and ignore downstream Hallucinations.
            
            action_match = re.search(r"Action\s*:\s*(.*?)(?=\n|$)", content, re.IGNORECASE)
            input_match = re.search(r"Action Input\s*:\s*(.*)", content, re.DOTALL | re.IGNORECASE)

            # ── Detect alternative format: {"tool": "x", "tool_input": {...}} ─
            if not (action_match and input_match):
                alt_json = self._extract_first_json(content)
                if alt_json:
                    try:
                        parsed = json.loads(alt_json)
                        if isinstance(parsed, dict):
                            act_name, act_input = None, None
                            
                            # check for tool/tool_input or action/action_input bindings case-insensitively
                            lower_keys = {k.lower(): v for k, v in parsed.items()}
                            
                            if "tool" in lower_keys and "tool_input" in lower_keys:
                                act_name = str(lower_keys["tool"])
                                act_input = json.dumps(lower_keys["tool_input"])
                            elif "action" in lower_keys and "action_input" in lower_keys:
                                act_name = str(lower_keys["action"])
                                act_input = json.dumps(lower_keys["action_input"])
                                
                            if act_name and act_input:
                                action_match = type('M', (), {'group': lambda self, n: act_name})()
                                input_match = type('M', (), {'group': lambda self, n: act_input})()
                    except json.JSONDecodeError:
                        pass
            
            if action_match and input_match:
                action = action_match.group(1).strip()
                raw_input = input_match.group(1).strip()
                
                # Extract FIRST valid JSON object (not from { to last })
                action_input = self._extract_first_json(raw_input) or raw_input
                
                logger.info("[%s] ReAct Tool Call: %s", self.name, action)
                print(f"👉 Tool Triggered: {action}\n")
                await context.emit("tool_trigger", {"agent": self.name, "tool": action, "input": action_input})
                
                result = await self.tool_registry.call(action, action_input)
                tools_called_count += 1
                tools_called.add(action)

                # Side-channel: mark in context so orchestrator can detect it
                # even if the LLM forgets to set did_edit=True in Final Answer.
                if action.lower() in ("file_editor", "file_edit") and "error" not in str(result).lower():
                    context.state["file_edited"] = True

                print(f"✅ Tool Result ({action}): {str(result)[:500]}...\n")
                await context.emit("tool_result", {"agent": self.name, "tool": action, "result": str(result)})
                
                # Truncate content to avoid saving runaway hallucinations (e.g. fake Observations/Final Answers)
                runaway_index = content.find(raw_input)
                if runaway_index != -1:
                    clean_content = content[:runaway_index + len(raw_input)]
                else:
                    clean_content = content

                messages.append({"role": "assistant", "content": clean_content})
                messages.append({
                    "role": "user",
                    "content": f"Observation: {result}"
                })
                continue
                
            # ── Check for Final Answer ────────────────────────────────────
            if "Final Answer:" in content:
                final_json_str = content.split("Final Answer:", 1)[1].strip()
                try:
                    final_res = self._parse_output(final_json_str)
                    if hasattr(self, "validate_result"):
                        self.validate_result(final_res, tools_called)
                    return final_res
                except ValueError as e:
                    messages.append({"role": "assistant", "content": content})
                    messages.append({"role": "user", "content": f"Validation Error on your Final Answer: {str(e)}"})
                    continue

            # If no Action and no Final Answer, maybe it just dumped JSON directly?
            # ANTI-HALLUCINATION GUARD: only for agents that MUST call tools (require_tool_calls=True)
            if self.require_tool_calls and has_tools and tools_called_count == 0:
                logger.warning(
                    "[%s] Agent tried to shortcut — has %d tools but called NONE. Forcing tool use.",
                    self.name, len(self.tool_registry)
                )
                messages.append({"role": "assistant", "content": content})
                messages.append({
                    "role": "user",
                    "content": (
                        "CRITICAL ERROR: You provided a final answer WITHOUT calling any tools. "
                        "You MUST use the available tools to actually perform the work — do NOT fabricate results. "
                        "Start over: use Action/Action Input to call the required tools before giving a Final Answer."
                    )
                })
                continue

            try:
                # Provide a hard guard if the model tries to pass tools as a raw JSON without ReAct format
                if '"Action"' in content and "Final Answer" not in content:
                    raise ValueError("Model dumped JSON instead of using Text ReAct format.")
                
                final_res = self._parse_output(content)
                if hasattr(self, "validate_result"):
                    self.validate_result(final_res, tools_called)
                print(f"\n🎉 [{self.name}] Output structured successfully.\n")
                await context.emit("agent_status", {"agent": self.name, "status": "success", "message": "Task complete."})
                return final_res
            except ValueError as e:
                # LLM talked but didn't follow format or failed validation
                messages.append({"role": "assistant", "content": content})
                if "Validation Error" in str(e) or "hallucinate" in str(e).lower() or "fabricate" in str(e).lower():
                    messages.append({"role": "user", "content": str(e)})
                else:
                    messages.append({"role": "user", "content": "Error: You didn't use a tool (Action/Action Input format) and you didn't provide a Final Answer. Return ONLY exactly one block of Thought/Action/Action Input OR Final Answer."})
                continue

        # Exhausted iterations — parse last LLM response (NOT the last Observation)
        logger.warning("[%s] max iterations (%d) reached", self.name, self.max_iterations)
        final_res = self._parse_output(last_agent_content)
        # Final validation on exit 
        if hasattr(self, "validate_result"):
            self.validate_result(final_res, tools_called)
        return final_res

    # ── Helpers ──────────────────────────────────────────────────────────
    def _extract_first_json(self, text: str) -> str | None:
        """Find the first valid JSON object in a string containing extra text."""
        start = text.find("{")
        if start == -1:
            return None
        
        # Count braces to find the end of the JSON object
        brace_count = 0
        in_string = False
        escape_next = False
        
        for i in range(start, len(text)):
            ch = text[i]
            
            if escape_next:
                escape_next = False
                continue
                
            if ch == "\\" and in_string:
                escape_next = True
                continue
                
            if ch == '"':
                in_string = not in_string
                continue
                
            if not in_string:
                if ch == "{":
                    brace_count += 1
                elif ch == "}":
                    brace_count -= 1
                    
                    if brace_count == 0:
                        # Found the end of the JSON object
                        json_str = text[start:i+1]
                        try:
                            # Verify it's valid JSON
                            json.loads(json_str)
                            return json_str
                        except json.JSONDecodeError:
                            return None
        return None

    def _build_system_prompt(self, context: AgentContext) -> str:
        """Build the system prompt, injecting context state if needed."""
        base = self.system_prompt

        # Inject structured-output instruction
        schema_json = json.dumps(
            self.output_schema.model_json_schema(), indent=2, ensure_ascii=False
        )
        
        react_instructions = ""
        if len(self.tool_registry) > 0:
            if settings.use_native_tool_calling:
                react_instructions = """
## Tools Available
You have access to native tools. Use them to gather information. Do NOT try to use the legacy Action/Action Input text format.
When you have gathered everything you need, move on to the Final Output Format.
"""
            else:
                react_instructions = f"""
## Tools Available
You have access to the following tools:
{self.tool_registry.text_schemas}

To use a tool, you MUST use the following exact format:
Thought: Describe your reasoning for using the tool.
Action: The name of the tool to use.
Action Input: A valid JSON object containing the arguments for the tool.

CRITICAL: You MUST ONLY use ONE tool at a time! After providing the Action Input, you MUST immediately STOP outputting and wait. Do NOT simulate or fabricate the "Observation". Multiple Actions in a single output will be IGNORED.
The system will then run the tool and reply with "Observation: ...".
You can use tools as many times as needed to gather information, but strictly ONE by ONE.
"""

        base += f"""
{react_instructions}
## Final Output Format
When you have collected all the information you need, or if you don't need to use any tools, you MUST return your final response using the following format:

Thought: Describe your final conclusion.
Final Answer: <Your final JSON object strictly matching the schema>

The JSON object MUST correspond exactly to this JSON schema (DO NOT output the schema definitions like \"properties\" or \"type\", output the actual data matching the schema):
```json
{schema_json}
```
CRITICAL RULES for JSON:
1. Escape all quotes inside strings properly.
2. Ensure you close all brackets and braces. Do not truncate the JSON.
3. Do not wrap your JSON in extraneous formatting or markdown outside of the Final Answer block.
4. ONLY OUTPUT THE DATA OBJECT. DO NOT output keys like "properties", "required", or "type".
"""

        # Inject session state if present
        if context.state:
            state_str = json.dumps(context.state, indent=2, ensure_ascii=False)
            base += f"\n\n## Session State\n```json\n{state_str}\n```"

        # Inject already-read files so this agent doesn't re-fetch them
        # Only show entries whose key is a plain file path (skip composite "file:start:end" keys)
        clean_cache = {
            path: content
            for path, content in context.file_cache.items()
            if ":" not in path  # composite keys like "src/foo.py:100:200" are excluded
        }
        if clean_cache:
            cache_lines = "\n\n".join(
                f"### {path}\n```\n{content[:4000]}\n```"
                for path, content in clean_cache.items()
            )
            base += f"\n\n## Already-Read Files (DO NOT read these again, use the content below)\n{cache_lines}"

        return base

    def _parse_output(self, raw: str) -> T:
        """Parse LLM text into the Pydantic output schema."""
        cleaned = raw.strip()

        # Strip markdown code fences if present
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines).strip()

        # Try direct parse first
        try:
            return self.output_schema.model_validate_json(cleaned)
        except Exception:
            pass

        # Find outermost JSON object
        start = cleaned.find("{")
        if start != -1:
            end = cleaned.rfind("}") + 1
            if end > start:
                json_str = cleaned[start:end]
                try:
                    return self.output_schema.model_validate_json(json_str)
                except Exception:
                    pass

            # ── Truncated JSON Recovery ───────────────────────────────
            # Model hit token limit and JSON was cut off mid-string.
            # Try to auto-close open braces/brackets to make it valid.
            partial = cleaned[start:]
            repaired = self._repair_truncated_json(partial)
            if repaired:
                try:
                    return self.output_schema.model_validate_json(repaired)
                except Exception as e:
                    logger.warning("[%s] Repaired JSON still invalid: %s", self.name, str(e))
                    print(f"\n⚠️  [{self.name}] Repaired JSON validation failed: {e}\n")

        logger.error("[%s] Failed to parse output. Raw: %.200s", self.name, raw)
        raise ValueError(
            f"Agent '{self.name}' returned unparseable output. Raw: {raw[:300]}"
        )

    @staticmethod
    def _repair_truncated_json(partial: str) -> str | None:
        """Attempt to close a truncated JSON string by balancing brackets.

        Strategy:
        1. Truncate at the last complete key-value pair boundary.
        2. Close any open string literals.
        3. Close open arrays / objects in reverse order.
        """
        try:
            # First try: just balance brackets/braces as-is
            stack: list[str] = []
            in_string = False
            escape_next = False
            last_safe_pos = 0  # position after last cleanly closed structure

            for i, ch in enumerate(partial):
                if escape_next:
                    escape_next = False
                    continue
                if ch == "\\" and in_string:
                    escape_next = True
                    continue
                if ch == '"' and not escape_next:
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if ch in ("{", "["):
                    stack.append(ch)
                elif ch == "}":
                    if stack and stack[-1] == "{":
                        stack.pop()
                        if not stack:  # top level closed
                            last_safe_pos = i + 1
                elif ch == "]":
                    if stack and stack[-1] == "[":
                        stack.pop()

            # Build closing suffix
            suffix = ""
            if in_string:
                suffix += '"'  # close open string
            # Close open arrays/objects in reverse
            for opener in reversed(stack):
                suffix += "}" if opener == "{" else "]"

            repaired = partial + suffix
            # Validate it is at least parseable JSON before returning
            json.loads(repaired)
            return repaired
        except Exception:
            return None
