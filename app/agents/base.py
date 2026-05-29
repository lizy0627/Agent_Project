from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any, Protocol

from app.services.agent_types import ChatMessage


class LLMClientProtocol(Protocol):
    model: str

    def complete_chat(self, messages: list[ChatMessage], model: str | None = None) -> str:
        """Return a chat completion."""


@dataclass(frozen=True)
class AgentResult:
    """Structured output returned by every sub agent."""

    agent_name: str
    task: str
    success: bool
    content: str
    data: Any = None
    error: str | None = None
    duration_ms: float | None = None
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "agent_name": self.agent_name,
            "task": self.task,
            "success": self.success,
            "content": self.content,
        }
        if self.data is not None:
            payload["data"] = self.data
        if self.error is not None:
            payload["error"] = self.error
        if self.duration_ms is not None:
            payload["duration_ms"] = self.duration_ms
        if self.metadata is not None:
            payload["metadata"] = self.metadata
        return payload


class BaseAgent:
    """Common utilities shared by manager and sub agents."""

    name = "BaseAgent"

    def _elapsed_ms(self, started_at: float) -> float:
        return round((perf_counter() - started_at) * 1000, 2)

    def _latest_user_message(self, messages: list[ChatMessage]) -> str:
        for message in reversed(messages):
            if message.get("role") == "user":
                return message.get("content", "")
        return ""
