from typing import Any

from backend.app.tools.base import ToolResult
from backend.app.tools.registry import ToolRegistry
from backend.app.workflow.engine import WorkflowEdge, WorkflowGraph, WorkflowNode


def create_research_workflow(
    tool_registry: ToolRegistry,
    *,
    max_results: int = 3,
    read_top_k: int = 2,
) -> WorkflowGraph:
    """Create a fixed Search -> Read -> Summarize research workflow."""

    def search(context: dict[str, Any]) -> ToolResult:
        query = str(context["input"].get("query") or "").strip()
        if not query:
            return ToolResult(
                name="web_search",
                success=False,
                error="Research workflow requires a query.",
                error_code="INVALID_ARGUMENTS",
                error_message="Research workflow requires a query.",
            )
        return tool_registry.run_tool(
            "web_search",
            {
                "query": query,
                "max_results": max_results,
                "search_depth": context["input"].get("search_depth", "basic"),
            },
        )

    def read(context: dict[str, Any]) -> dict[str, Any]:
        search_output = context["results"].get("search") or {}
        search_results = search_output.get("results", []) if isinstance(search_output, dict) else []
        pages: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []

        for item in _select_search_results(search_results, read_top_k):
            url = str(item.get("url") or "").strip()
            result = tool_registry.run_tool("web_reader", {"url": url})
            if result.success and isinstance(result.result, dict):
                pages.append(
                    {
                        "title": item.get("title", ""),
                        "url": result.result.get("url") or url,
                        "search_snippet": item.get("content") or item.get("snippet") or "",
                        "content": _truncate_text(str(result.result.get("content") or ""), 2000),
                    }
                )
            else:
                errors.append(
                    {
                        "url": url,
                        "code": result.error_code or "READ_FAILED",
                        "message": result.error_message or result.error or "Read failed.",
                    }
                )

        return {
            "pages": pages,
            "errors": errors,
            "success_pages": len(pages),
            "failed_pages": len(errors),
        }

    def summarize(context: dict[str, Any]) -> dict[str, Any]:
        search_output = context["results"].get("search") or {}
        read_output = context["results"].get("read") or {}
        search_results = search_output.get("results", []) if isinstance(search_output, dict) else []
        read_pages = read_output.get("pages", []) if isinstance(read_output, dict) else []

        return {
            "workflow": "research_workflow",
            "query": context["input"].get("query"),
            "search_success": bool(search_output),
            "search_error": None,
            "search_results": _compact_search_results(search_results),
            "read_pages": read_pages,
            "web_pages_read": bool(read_pages),
            "success_pages": read_output.get("success_pages", 0) if isinstance(read_output, dict) else 0,
            "failed_pages": read_output.get("failed_pages", 0) if isinstance(read_output, dict) else 0,
            "read_errors": read_output.get("errors", []) if isinstance(read_output, dict) else [],
        }

    return WorkflowGraph(
        name="research_workflow",
        nodes=[
            WorkflowNode("search", "Search", search),
            WorkflowNode("read", "Read", read),
            WorkflowNode("summarize", "Summarize", summarize),
        ],
        edges=[
            WorkflowEdge("search", "read"),
            WorkflowEdge("read", "summarize"),
        ],
    )


def _select_search_results(results: Any, limit: int) -> list[dict[str, Any]]:
    if not isinstance(results, list):
        return []
    selected: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for item in results:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        selected.append(item)
        if len(selected) >= max(limit, 0):
            break
    return selected


def _compact_search_results(results: Any) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for item in _select_search_results(results, 5):
        compact.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": _truncate_text(str(item.get("content") or item.get("snippet") or ""), 500),
                "score": item.get("score"),
            }
        )
    return compact


def _truncate_text(text: str, max_chars: int) -> str:
    clean_text = " ".join(text.split())
    if len(clean_text) <= max_chars:
        return clean_text
    return clean_text[: max_chars - 3].rstrip() + "..."
