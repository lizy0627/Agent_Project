from __future__ import annotations

from time import perf_counter
from typing import Any, Protocol

from app.agents.base import AgentResult, BaseAgent
from app.services.agent_types import ChatMessage
from app.tools.base import ToolResult


class ToolManagerProtocol(Protocol):
    def call(self, name: str, max_retries: int = 1, **kwargs: Any) -> ToolResult:
        """Run a named tool and return normalized metadata."""


class SearchAgent(BaseAgent):
    """Sub agent responsible for external information search."""

    name = "SearchAgent"

    def __init__(self, tool_manager: ToolManagerProtocol) -> None:
        self.tool_manager = tool_manager

    def run(self, question: str, messages: list[ChatMessage], model: str | None = None) -> AgentResult:
        started_at = perf_counter()
        task = question.strip() or "Search for external references relevant to the user question."
        try:
            tool_result = self.tool_manager.call(
                "web_search",
                query=task,
                max_results=3,
                search_depth="basic",
            )
        except Exception as exc:
            return AgentResult(
                agent_name=self.name,
                task=task,
                success=False,
                content="SearchAgent failed before receiving a tool result.",
                error=str(exc),
                duration_ms=self._elapsed_ms(started_at),
            )

        content = self._format_search_content(tool_result)
        return AgentResult(
            agent_name=self.name,
            task=task,
            success=tool_result.success,
            content=content,
            data=tool_result.result,
            error=tool_result.error_message or tool_result.error,
            duration_ms=self._elapsed_ms(started_at),
            metadata={
                "tool_name": tool_result.name,
                "tool_status": "success" if tool_result.success else "failed",
                "tool_duration_ms": tool_result.duration_ms,
                "retryable": tool_result.retryable,
            },
        )

    def _format_search_content(self, tool_result: ToolResult) -> str:
        if not tool_result.success:
            return tool_result.error_message or tool_result.error or "Search did not complete successfully."

        data = tool_result.result if isinstance(tool_result.result, dict) else {}
        results = data.get("results") if isinstance(data, dict) else None
        if not isinstance(results, list) or not results:
            return "Search completed, but no results were returned."

        lines: list[str] = []
        for index, item in enumerate(results[:3], start=1):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "Untitled").strip()
            url = str(item.get("url") or "").strip()
            snippet = str(item.get("content") or item.get("snippet") or "").strip()
            parts = [f"{index}. {title}"]
            if url:
                parts.append(f"URL: {url}")
            if snippet:
                parts.append(f"Snippet: {snippet[:500]}")
            lines.append(" | ".join(parts))

        return "\n".join(lines) if lines else "Search completed, but results could not be formatted."
