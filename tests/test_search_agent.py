from typing import Any

from app.agents.search_agent import SearchAgent
from app.tools.base import ToolResult
from backend.app.agents.search_agent import SearchAgent as BackendSearchAgent


class FakeSearchToolManager:
    def __init__(self, read_failures: set[str] | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.read_failures = read_failures or set()

    def call(self, name: str, max_retries: int = 1, **kwargs: Any) -> ToolResult:
        self.calls.append((name, kwargs))
        if name == "web_search":
            return ToolResult(
                name="web_search",
                success=True,
                result={
                    "query": kwargs["query"],
                    "results": [
                        {
                            "title": "First result",
                            "url": "https://example.test/one",
                            "content": "First search snippet",
                            "score": 0.9,
                        },
                        {
                            "title": "Second result",
                            "url": "https://example.test/two",
                            "content": "Second search snippet",
                            "score": 0.8,
                        },
                        {
                            "title": "Third result",
                            "url": "https://example.test/three",
                            "content": "Third search snippet",
                            "score": 0.7,
                        },
                    ],
                },
                duration_ms=2.0,
            )
        if name == "read_webpage":
            url = kwargs["url"]
            if url in self.read_failures:
                return ToolResult(
                    name="read_webpage",
                    success=False,
                    error="reader failed",
                    error_message="reader failed",
                    error_code="NETWORK_ERROR",
                    duration_ms=1.0,
                    retryable=True,
                )
            return ToolResult(
                name="read_webpage",
                success=True,
                result={
                    "url": url,
                    "content": f"Readable body for {url}",
                    "content_type": "text/html",
                    "content_length": 120,
                    "cached": False,
                },
                duration_ms=1.0,
            )
        raise AssertionError(f"Unexpected tool call: {name}")


def test_search_agent_reads_top_k_pages_and_returns_evidence():
    tool_manager = FakeSearchToolManager()
    agent = SearchAgent(tool_manager, read_top_k=2)

    result = agent.run("Find release notes", [])

    assert result.success is True
    assert [name for name, _kwargs in tool_manager.calls] == ["web_search", "read_webpage", "read_webpage"]
    assert result.data["query"] == "Find release notes"
    assert len(result.data["search_results"]) == 3
    assert len(result.data["read_pages"]) == 2
    assert result.data["read_pages"][0]["success"] is True
    assert result.data["sources"][0]["evidence"] == "Readable body for https://example.test/one"
    assert result.data["sources"][0]["read_success"] is True
    assert "资料来源" in result.content
    assert "摘要" in result.content
    assert "First result" in result.content
    assert "https://example.test/one" in result.content
    assert "First search snippet" in result.content


def test_search_agent_keeps_search_success_when_read_webpage_fails():
    tool_manager = FakeSearchToolManager(read_failures={"https://example.test/one"})
    agent = SearchAgent(tool_manager, read_top_k=2)

    result = agent.run("Find release notes", [])

    assert result.success is True
    assert result.error is None
    assert result.data["read_pages"][0]["success"] is False
    assert result.data["read_pages"][0]["error"] == "reader failed"
    assert result.data["read_pages"][0]["tool_result"]["error_code"] == "NETWORK_ERROR"
    assert result.data["sources"][0]["evidence"] == "First search snippet"
    assert result.data["sources"][1]["evidence"] == "Readable body for https://example.test/two"


def test_search_agent_preserves_web_search_error_payload():
    class FailingSearchToolManager:
        def call(self, name: str, max_retries: int = 1, **kwargs: Any) -> ToolResult:
            return ToolResult(
                name="web_search",
                success=False,
                error="search failed",
                error_message="search failed",
                error_code="API_KEY_MISSING",
                retryable=False,
            )

    result = SearchAgent(FailingSearchToolManager()).run("Find release notes", [])

    assert result.success is False
    assert result.error == "search failed"
    assert result.data["search_tool"]["error_code"] == "API_KEY_MISSING"
    assert result.data["search_results"] == []
    assert result.data["read_pages"] == []
    assert result.data["sources"] == []


def test_backend_search_agent_reads_pages_with_same_result_shape():
    tool_manager = FakeSearchToolManager()
    agent = BackendSearchAgent(tool_manager, read_top_k=2)

    result = agent.run("Find release notes", [])

    assert result.success is True
    assert [name for name, _kwargs in tool_manager.calls] == ["web_search", "read_webpage", "read_webpage"]
    assert set(result.data) >= {"query", "search_results", "read_pages", "sources"}
    assert result.data["sources"][0]["evidence"] == "Readable body for https://example.test/one"
