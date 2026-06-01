from __future__ import annotations

from time import perf_counter
from typing import Any, Protocol

from backend.app.agents.base import AgentResult, BaseAgent
from backend.app.services.agent_types import ChatMessage
from backend.app.tools.base import ToolResult


class ToolManagerProtocol(Protocol):
    def call(self, name: str, max_retries: int = 1, **kwargs: Any) -> ToolResult:
        """Run a named tool and return normalized metadata."""


class SearchAgent(BaseAgent):
    """Sub agent responsible for external information search."""

    name = "SearchAgent"
    default_search_results = 3
    default_read_top_k = 3
    max_read_top_k = 3

    def __init__(self, tool_manager: ToolManagerProtocol, read_top_k: int | None = None) -> None:
        self.tool_manager = tool_manager
        self.read_top_k = self._normalize_top_k(read_top_k)

    def run(self, question: str, messages: list[ChatMessage], model: str | None = None) -> AgentResult:
        started_at = perf_counter()
        task = question.strip() or "Search for external references relevant to the user question."
        try:
            search_result = self.tool_manager.call(
                "web_search",
                query=task,
                max_results=self.default_search_results,
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

        data = self._build_search_data(task, search_result)
        if search_result.success:
            data["read_pages"] = self._read_top_pages(data["search_results"])
            data["sources"] = self._build_sources(data["search_results"], data["read_pages"])

        content = self._format_search_content(search_result, data)
        return AgentResult(
            agent_name=self.name,
            task=task,
            success=search_result.success,
            content=content,
            data=data,
            error=search_result.error_message or search_result.error,
            duration_ms=self._elapsed_ms(started_at),
            metadata={
                "tool_name": search_result.name,
                "tool_status": "success" if search_result.success else "failed",
                "tool_duration_ms": search_result.duration_ms,
                "retryable": search_result.retryable,
                "read_top_k": self.read_top_k,
                "read_success_count": self._read_success_count(data["read_pages"]),
            },
        )

    def _build_search_data(self, query: str, search_result: ToolResult) -> dict[str, Any]:
        search_data = search_result.result if isinstance(search_result.result, dict) else {}
        results = search_data.get("results") if isinstance(search_data, dict) else None
        search_results = [item for item in results if isinstance(item, dict)] if isinstance(results, list) else []
        return {
            "query": str(search_data.get("query") or query),
            "search_results": search_results,
            "read_pages": [],
            "sources": [],
            "search_tool": self._tool_result_payload(search_result),
        }

    def _read_top_pages(self, search_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        read_pages: list[dict[str, Any]] = []
        for item in search_results[: self.read_top_k]:
            url = str(item.get("url") or "").strip()
            if not url:
                continue

            try:
                read_result = self.tool_manager.call("read_webpage", url=url)
            except Exception as exc:
                read_pages.append(
                    {
                        "requested_url": url,
                        "url": url,
                        "success": False,
                        "error": str(exc),
                        "tool_result": {
                            "name": "read_webpage",
                            "success": False,
                            "error": str(exc),
                        },
                    }
                )
                continue

            page_data = read_result.result if isinstance(read_result.result, dict) else {}
            read_pages.append(
                {
                    "requested_url": url,
                    "url": str(page_data.get("url") or url),
                    "success": read_result.success,
                    "title": str(item.get("title") or "").strip(),
                    "content": str(page_data.get("content") or "").strip(),
                    "content_type": page_data.get("content_type"),
                    "content_length": page_data.get("content_length"),
                    "cached": page_data.get("cached"),
                    "error": read_result.error_message or read_result.error,
                    "tool_result": self._tool_result_payload(read_result),
                }
            )
        return read_pages

    def _build_sources(
        self,
        search_results: list[dict[str, Any]],
        read_pages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        pages_by_url: dict[str, dict[str, Any]] = {}
        for page in read_pages:
            for key in ("requested_url", "url"):
                page_url = str(page.get(key) or "").strip()
                if page_url:
                    pages_by_url[page_url] = page
        sources: list[dict[str, Any]] = []
        for index, item in enumerate(search_results, start=1):
            url = str(item.get("url") or "").strip()
            page = pages_by_url.get(url, {})
            snippet = str(item.get("content") or item.get("snippet") or "").strip()
            evidence = str(page.get("content") or snippet).strip()
            sources.append(
                {
                    "index": index,
                    "title": str(item.get("title") or "Untitled").strip(),
                    "url": url,
                    "snippet": snippet,
                    "evidence": evidence[:1200],
                    "read_success": bool(page.get("success")),
                    "score": item.get("score"),
                }
            )
        return sources

    def _format_search_content(self, search_result: ToolResult, data: dict[str, Any]) -> str:
        if not search_result.success:
            return search_result.error_message or search_result.error or "Search did not complete successfully."

        results = data.get("sources")
        if not isinstance(results, list) or not results:
            return "Search completed, but no results were returned."

        lines: list[str] = []
        for index, item in enumerate(results[: self.default_search_results], start=1):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "Untitled").strip()
            url = str(item.get("url") or "").strip()
            snippet = str(item.get("snippet") or item.get("evidence") or "").strip()
            evidence = str(item.get("evidence") or snippet).strip()
            summary = evidence or snippet
            parts = [f"{index}. 资料来源: {title}"]
            if url:
                parts.append(f"URL: {url}")
            if summary:
                parts.append(f"摘要: {summary[:700]}")
            if snippet and snippet != summary:
                parts.append(f"搜索摘要: {snippet[:300]}")
            lines.append(" | ".join(parts))

        return "\n".join(lines) if lines else "Search completed, but results could not be formatted."

    def _tool_result_payload(self, tool_result: ToolResult) -> dict[str, Any]:
        return {
            "name": tool_result.name,
            "success": tool_result.success,
            "result": tool_result.result,
            "error": tool_result.error,
            "error_code": tool_result.error_code,
            "error_message": tool_result.error_message,
            "duration_ms": tool_result.duration_ms,
            "retryable": tool_result.retryable,
        }

    def _read_success_count(self, read_pages: list[dict[str, Any]]) -> int:
        return sum(1 for page in read_pages if page.get("success"))

    def _normalize_top_k(self, value: int | None) -> int:
        if value is None:
            return self.default_read_top_k
        try:
            return min(max(int(value), 0), self.max_read_top_k)
        except (TypeError, ValueError):
            return self.default_read_top_k
