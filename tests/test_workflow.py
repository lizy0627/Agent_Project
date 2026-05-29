from typing import Any

from app.tools.base import BaseTool
from app.tools.registry import ToolRegistry
from app.workflow import WorkflowEdge, WorkflowGraph, WorkflowNode, create_research_workflow


class FakeSearchTool(BaseTool):
    name = "web_search"
    description = "Fake search."
    args_schema = {}

    def run(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "results": [
                {
                    "title": "Result 1",
                    "url": "https://example.test/one",
                    "content": f"Snippet for {kwargs['query']}",
                    "score": 0.9,
                }
            ]
        }


class FakeReaderTool(BaseTool):
    name = "web_reader"
    description = "Fake reader."
    args_schema = {}

    def run(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "url": kwargs["url"],
            "content": "Full page content for research.",
        }


def test_research_workflow_runs_search_read_summarize():
    registry = ToolRegistry()
    registry.register(FakeSearchTool())
    registry.register(FakeReaderTool())

    execution = create_research_workflow(registry).run({"query": "workflow engine"})
    tool_result = execution.to_tool_result()

    assert execution.success is True
    assert [result.node_id for result in execution.node_results] == ["search", "read", "summarize"]
    assert tool_result.name == "research_workflow"
    assert tool_result.success is True
    assert tool_result.result["query"] == "workflow engine"
    assert tool_result.result["search_results"][0]["url"] == "https://example.test/one"
    assert tool_result.result["read_pages"][0]["content"] == "Full page content for research."
    assert tool_result.result["workflow_nodes"][0]["node_id"] == "search"


def test_workflow_records_failed_node_and_skips_dependents():
    def explode(_context):
        raise RuntimeError("search failed")

    graph = WorkflowGraph(
        name="broken_workflow",
        nodes=[
            WorkflowNode("search", "Search", explode),
            WorkflowNode("summarize", "Summarize", lambda _context: {"ok": True}),
        ],
        edges=[WorkflowEdge("search", "summarize")],
    )

    execution = graph.run({"query": "workflow engine"})

    assert execution.success is False
    assert execution.errors[0]["node_id"] == "search"
    assert execution.errors[0]["message"] == "search failed"
    assert execution.node_results[1].skipped is True
    assert execution.node_results[1].error_code == "DEPENDENCY_FAILED"
