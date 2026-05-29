from __future__ import annotations

import json
import re
from typing import Any, Callable, Mapping, Sequence

from pydantic import BaseModel, Field

from app.core.safe_logging import mask_sensitive_text, safe_log_data
from app.services.agent_types import ChatMessage
from app.tools.base import ToolResult
from app.tools.registry import TOOL_NOT_FOUND, ToolRegistry


DEFAULT_MAX_TOOL_CALLS = 5
MAX_OBSERVATION_TEXT_LENGTH = 4000


class ReActToolCall(BaseModel):
    """One tool call selected and executed by the ReAct loop."""

    tool_name: str
    tool_args: dict[str, Any] = Field(default_factory=dict)
    status: str
    result: Any | None = None
    error: str | None = None
    duration_ms: float | None = None
    error_code: str | None = None
    retryable: bool | None = None


class ReActReasoningStep(BaseModel):
    """A JSON-safe Thought, Action, Observation, or Final Answer step."""

    type: str
    content: Any | None = None
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None
    observation: Any | None = None
    status: str | None = None
    error: str | None = None


class ReActResult(BaseModel):
    """Final ReAct output expected by callers."""

    final_answer: str
    reasoning_steps: list[ReActReasoningStep] = Field(default_factory=list)
    tool_calls: list[ReActToolCall] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


class ParsedReActResponse(BaseModel):
    """Parsed model response for one ReAct turn."""

    thought: str | None = None
    final_answer: str | None = None
    action_name: str | None = None
    action_args: dict[str, Any] = Field(default_factory=dict)


class ReActAgent:
    """Run a Thought / Action / Observation / Final Answer loop over ToolRegistry."""

    def __init__(
        self,
        llm_client: Any,
        tool_registry: ToolRegistry,
        *,
        max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS,
        system_prompt: str | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.tool_registry = tool_registry
        self.max_tool_calls = min(max(int(max_tool_calls), 1), DEFAULT_MAX_TOOL_CALLS)
        self.system_prompt = system_prompt

    def run(self, messages: str | Sequence[ChatMessage], model: str | None = None) -> ReActResult:
        """Execute the ReAct loop and return final_answer, reasoning_steps, and tool_calls."""

        base_messages = self._normalize_messages(messages)
        reasoning_steps: list[ReActReasoningStep] = []
        tool_calls: list[ReActToolCall] = []
        scratchpad = ""

        for _ in range(self.max_tool_calls):
            model_reply = self._complete(self._build_prompt_messages(base_messages, scratchpad), model=model)
            parsed = parse_react_response(model_reply)
            self._append_thought(reasoning_steps, parsed.thought)

            if parsed.final_answer is not None:
                final_answer = self._redact_text(parsed.final_answer)
                reasoning_steps.append(ReActReasoningStep(type="final_answer", content=final_answer))
                return ReActResult(
                    final_answer=final_answer,
                    reasoning_steps=reasoning_steps,
                    tool_calls=tool_calls,
                )

            if not parsed.action_name:
                final_answer = self._redact_text(model_reply)
                reasoning_steps.append(ReActReasoningStep(type="final_answer", content=final_answer))
                return ReActResult(
                    final_answer=final_answer,
                    reasoning_steps=reasoning_steps,
                    tool_calls=tool_calls,
                )

            reasoning_steps.append(
                ReActReasoningStep(
                    type="action",
                    tool_name=parsed.action_name,
                    tool_args=self._redact_data(parsed.action_args),
                )
            )
            tool_result = self._run_registry_tool(parsed.action_name, parsed.action_args)
            tool_call = self._tool_call_from_result(parsed.action_name, parsed.action_args, tool_result)
            observation = self._observation_from_result(tool_result)
            tool_calls.append(tool_call)
            reasoning_steps.append(
                ReActReasoningStep(
                    type="observation",
                    tool_name=parsed.action_name,
                    observation=observation,
                    status=tool_call.status,
                    error=tool_call.error,
                )
            )
            scratchpad = self._append_observation_to_scratchpad(scratchpad, model_reply, observation)

        final_answer = self._final_answer_after_tool_limit(base_messages, scratchpad, model=model)
        reasoning_steps.append(
            ReActReasoningStep(
                type="final_answer",
                content=final_answer,
                status="tool_limit_reached",
            )
        )
        return ReActResult(final_answer=final_answer, reasoning_steps=reasoning_steps, tool_calls=tool_calls)

    def chat(self, messages: str | Sequence[ChatMessage], model: str | None = None) -> ReActResult:
        """Compatibility alias for callers that expect an agent-like chat method."""

        return self.run(messages, model=model)

    def _build_prompt_messages(self, messages: list[ChatMessage], scratchpad: str) -> list[ChatMessage]:
        prompt_messages: list[ChatMessage] = [
            {
                "role": "system",
                "content": self.system_prompt or self._react_system_prompt(),
            },
            *messages,
        ]
        if scratchpad:
            prompt_messages.append(
                {
                    "role": "assistant",
                    "content": scratchpad,
                }
            )
        return prompt_messages

    def _react_system_prompt(self) -> str:
        tools = self._available_tools()
        tool_names = ", ".join(tool["name"] for tool in tools) or "(no tools registered)"
        return (
            "You are a ReAct agent. Use this exact format:\n"
            "Thought: brief reasoning about the next step\n"
            'Action: {"tool": "<tool name>", "args": {}}\n'
            "Observation: the runtime will append the tool result\n"
            "Final Answer: the final response to the user\n\n"
            "Rules:\n"
            f"- Action must choose one registered tool only: {tool_names}.\n"
            f"- You may call at most {self.max_tool_calls} tools, then you must provide Final Answer.\n"
            "- Never reveal, repeat, or infer API keys, tokens, passwords, secrets, or Authorization headers.\n"
            "- Use Final Answer when no tool is needed.\n\n"
            f"Available tools:\n{json.dumps(tools, ensure_ascii=False)}"
        )

    def _available_tools(self) -> list[dict[str, Any]]:
        return self._redact_data(self.tool_registry.list_tools())

    def _run_registry_tool(self, tool_name: str, tool_args: dict[str, Any]) -> ToolResult:
        if self.tool_registry.get_tool(tool_name) is None:
            return ToolResult(
                name=tool_name,
                success=False,
                error=f"Tool is not registered: {tool_name}",
                error_code=TOOL_NOT_FOUND,
                error_message=f"Tool is not registered: {tool_name}",
                retryable=False,
            )
        return self.tool_registry.run_tool(tool_name, tool_args)

    def _tool_call_from_result(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        result: ToolResult,
    ) -> ReActToolCall:
        return ReActToolCall(
            tool_name=tool_name,
            tool_args=self._redact_data(tool_args),
            status="success" if result.success else "failed",
            result=self._redact_data(result.result),
            error=self._redact_text(result.error or result.error_message) if result.error or result.error_message else None,
            duration_ms=result.duration_ms,
            error_code=result.error_code,
            retryable=result.retryable,
        )

    def _observation_from_result(self, result: ToolResult) -> dict[str, Any]:
        return {
            "tool_name": result.name,
            "success": result.success,
            "result": self._redact_data(result.result),
            "error": self._redact_text(result.error or result.error_message) if result.error or result.error_message else None,
            "duration_ms": result.duration_ms,
            "error_code": result.error_code,
            "retryable": result.retryable,
        }

    def _append_observation_to_scratchpad(
        self,
        scratchpad: str,
        model_reply: str,
        observation: dict[str, Any],
    ) -> str:
        observation_text = self._observation_text(observation)
        return f"{scratchpad}{model_reply.strip()}\nObservation: {observation_text}\n"

    def _observation_text(self, observation: dict[str, Any]) -> str:
        text = json.dumps(self._redact_data(observation), ensure_ascii=False)
        if len(text) > MAX_OBSERVATION_TEXT_LENGTH:
            return f"{text[:MAX_OBSERVATION_TEXT_LENGTH]}..."
        return text

    def _final_answer_after_tool_limit(
        self,
        messages: list[ChatMessage],
        scratchpad: str,
        model: str | None = None,
    ) -> str:
        limit_message = (
            f"The ReAct tool-call limit of {self.max_tool_calls} has been reached. "
            "Do not call another tool. Provide only `Final Answer: ...` using the observations above."
        )
        prompt_messages = [
            *self._build_prompt_messages(messages, scratchpad),
            {"role": "user", "content": limit_message},
        ]
        model_reply = self._complete(prompt_messages, model=model)
        parsed = parse_react_response(model_reply)
        return self._redact_text(parsed.final_answer if parsed.final_answer is not None else model_reply)

    def _complete(self, messages: list[ChatMessage], model: str | None = None) -> str:
        if hasattr(self.llm_client, "complete_chat"):
            return str(self.llm_client.complete_chat(messages, model=model) or "")
        if isinstance(self.llm_client, Callable):
            return str(self.llm_client(messages) or "")
        raise TypeError("llm_client must provide complete_chat(messages, model=None) or be callable.")

    def _normalize_messages(self, messages: str | Sequence[ChatMessage]) -> list[ChatMessage]:
        if isinstance(messages, str):
            return [{"role": "user", "content": self._redact_text(messages)}]
        normalized: list[ChatMessage] = []
        for message in messages:
            role = str(message.get("role") or "user")
            content = self._redact_text(str(message.get("content") or ""))
            normalized.append({"role": role, "content": content})
        return normalized

    def _append_thought(self, reasoning_steps: list[ReActReasoningStep], thought: str | None) -> None:
        if thought is not None:
            reasoning_steps.append(ReActReasoningStep(type="thought", content=self._redact_text(thought)))

    def _redact_text(self, value: str) -> str:
        return mask_sensitive_text(str(value or ""))

    def _redact_data(self, value: Any) -> Any:
        return safe_log_data(value, max_length=MAX_OBSERVATION_TEXT_LENGTH)


def parse_react_response(text: str) -> ParsedReActResponse:
    """Parse Thought / Action / Final Answer from one model response."""

    clean_text = str(text or "").strip()
    final_answer = _extract_section(clean_text, "Final Answer", consume_rest=True)
    thought = _extract_section(clean_text, "Thought")
    if final_answer is not None:
        return ParsedReActResponse(
            thought=mask_sensitive_text(thought.strip()) if thought else None,
            final_answer=mask_sensitive_text(final_answer.strip()),
        )

    action_block = _extract_section(clean_text, "Action")
    action_input = _extract_section(clean_text, "Action Input")
    action_name, action_args = parse_action(action_block, action_input)
    return ParsedReActResponse(
        thought=mask_sensitive_text(thought.strip()) if thought else None,
        action_name=action_name,
        action_args=action_args,
    )


def parse_action(action_block: str | None, action_input: str | None = None) -> tuple[str | None, dict[str, Any]]:
    """Parse a flexible ReAct Action block into a registered-tool name and arguments."""

    if not action_block:
        return None, {}

    action_text = _strip_code_fence(action_block.strip())
    input_text = _strip_code_fence(action_input.strip()) if action_input else None
    if input_text is None and "Action Input:" in action_text:
        action_text, input_text = re.split(r"(?im)^\s*Action Input\s*:\s*", action_text, maxsplit=1)
        action_text = action_text.strip()
        input_text = input_text.strip()

    json_payload = _loads_json_object(action_text)
    if json_payload is not None:
        tool_name = _string_value(json_payload, "tool", "tool_name", "name", "action")
        args = _mapping_value(json_payload, "args", "arguments", "tool_args", "action_input", "input")
        return tool_name, args

    action_line = next((line.strip() for line in action_text.splitlines() if line.strip()), "")
    match = re.match(r"^(?P<name>[A-Za-z_][\w.-]*)(?:\s*\((?P<paren>.*)\)|\s+(?P<tail>\{.*\}))?$", action_line)
    if not match:
        return None, {}

    tool_name = match.group("name")
    raw_args = input_text or match.group("paren") or match.group("tail") or ""
    return tool_name, _parse_args(raw_args)


def _extract_section(text: str, section: str, *, consume_rest: bool = False) -> str | None:
    stop = r"\Z" if consume_rest else r"(?=^\s*(?:Thought|Action|Action Input|Observation|Final Answer)\s*:|\Z)"
    pattern = rf"(?ims)^\s*{re.escape(section)}\s*:\s*(?P<value>.*?){stop}"
    matches = list(re.finditer(pattern, text))
    if not matches:
        return None
    return matches[-1].group("value").strip()


def _parse_args(raw_args: str) -> dict[str, Any]:
    clean_args = _strip_code_fence(str(raw_args or "").strip())
    if not clean_args:
        return {}
    payload = _loads_json_object(clean_args)
    if payload is not None:
        return payload
    return {"input": mask_sensitive_text(clean_args)}


def _loads_json_object(value: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _mapping_value(payload: Mapping[str, Any], *keys: str) -> dict[str, Any]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    return {}


def _string_value(payload: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _strip_code_fence(value: str) -> str:
    stripped = value.strip()
    fence = re.match(r"^```(?:json)?\s*(?P<body>.*?)\s*```$", stripped, flags=re.IGNORECASE | re.DOTALL)
    return fence.group("body").strip() if fence else stripped


ReactAgent = ReActAgent
ReactorAgent = ReActAgent

__all__ = [
    "DEFAULT_MAX_TOOL_CALLS",
    "ParsedReActResponse",
    "ReActAgent",
    "ReActReasoningStep",
    "ReActResult",
    "ReActToolCall",
    "ReactAgent",
    "ReactorAgent",
    "parse_action",
    "parse_react_response",
]
