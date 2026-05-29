from collections.abc import Callable
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from app.tools.base import ToolResult


NodeHandler = Callable[[dict[str, Any]], Any]


@dataclass(frozen=True)
class WorkflowNode:
    """One executable workflow node."""

    node_id: str
    name: str
    handler: NodeHandler


@dataclass(frozen=True)
class WorkflowEdge:
    """Directed dependency between two workflow nodes."""

    source: str
    target: str


@dataclass(frozen=True)
class WorkflowNodeResult:
    """Execution result for one workflow node."""

    node_id: str
    name: str
    success: bool
    output: Any = None
    error: str | None = None
    error_code: str | None = None
    duration_ms: float = 0.0
    skipped: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "name": self.name,
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "error_code": self.error_code,
            "duration_ms": self.duration_ms,
            "skipped": self.skipped,
        }


@dataclass(frozen=True)
class WorkflowExecutionResult:
    """Complete workflow execution result that can be returned to Agent as ToolResult."""

    name: str
    success: bool
    output: Any
    node_results: list[WorkflowNodeResult] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow": self.name,
            "success": self.success,
            "output": self.output,
            "nodes": [result.to_dict() for result in self.node_results],
            "errors": self.errors,
            "duration_ms": self.duration_ms,
        }

    def to_tool_result(self) -> ToolResult:
        message = self.errors[0]["message"] if self.errors else None
        result_payload = dict(self.output) if isinstance(self.output, dict) else {"output": self.output}
        result_payload.setdefault("workflow", self.name)
        result_payload["workflow_errors"] = self.errors
        result_payload["workflow_nodes"] = [
            {
                "node_id": result.node_id,
                "name": result.name,
                "success": result.success,
                "error": result.error,
                "error_code": result.error_code,
                "duration_ms": result.duration_ms,
                "skipped": result.skipped,
            }
            for result in self.node_results
        ]
        return ToolResult(
            name=self.name,
            success=self.success,
            result=result_payload,
            error=message,
            duration_ms=self.duration_ms,
            error_code=self.errors[0].get("code") if self.errors else None,
            error_message=message,
            retryable=False,
        )


@dataclass
class WorkflowGraph:
    """Small DAG executor for deterministic workflows."""

    name: str
    nodes: list[WorkflowNode]
    edges: list[WorkflowEdge] = field(default_factory=list)

    def run(self, inputs: dict[str, Any] | None = None) -> WorkflowExecutionResult:
        started_at = perf_counter()
        context: dict[str, Any] = {
            "input": inputs or {},
            "results": {},
        }
        node_results: list[WorkflowNodeResult] = []
        errors: list[dict[str, Any]] = []
        results_by_id: dict[str, WorkflowNodeResult] = {}
        ordered_nodes = self._topological_nodes()

        for node in ordered_nodes:
            failed_dependencies = [
                dependency
                for dependency in self._dependencies(node.node_id)
                if not results_by_id.get(dependency, WorkflowNodeResult(dependency, dependency, False)).success
            ]
            if failed_dependencies:
                result = WorkflowNodeResult(
                    node_id=node.node_id,
                    name=node.name,
                    success=False,
                    error=f"Skipped because dependencies failed: {', '.join(failed_dependencies)}",
                    error_code="DEPENDENCY_FAILED",
                    skipped=True,
                )
                node_results.append(result)
                results_by_id[node.node_id] = result
                errors.append(self._error_record(result))
                continue

            result = self._run_node(node, context)
            node_results.append(result)
            results_by_id[node.node_id] = result
            context["results"][node.node_id] = result.output
            if not result.success:
                errors.append(self._error_record(result))

        output = self._final_output(node_results)
        return WorkflowExecutionResult(
            name=self.name,
            success=not errors,
            output=output,
            node_results=node_results,
            errors=errors,
            duration_ms=self._elapsed_ms(started_at),
        )

    def _run_node(self, node: WorkflowNode, context: dict[str, Any]) -> WorkflowNodeResult:
        started_at = perf_counter()
        try:
            output = node.handler(context)
        except Exception as exc:
            return WorkflowNodeResult(
                node_id=node.node_id,
                name=node.name,
                success=False,
                error=str(exc),
                error_code=exc.__class__.__name__,
                duration_ms=self._elapsed_ms(started_at),
            )

        if isinstance(output, ToolResult):
            return WorkflowNodeResult(
                node_id=node.node_id,
                name=node.name,
                success=output.success,
                output=output.result,
                error=output.error,
                error_code=output.error_code,
                duration_ms=output.duration_ms or self._elapsed_ms(started_at),
            )

        return WorkflowNodeResult(
            node_id=node.node_id,
            name=node.name,
            success=True,
            output=output,
            duration_ms=self._elapsed_ms(started_at),
        )

    def _topological_nodes(self) -> list[WorkflowNode]:
        node_by_id = {node.node_id: node for node in self.nodes}
        ordered: list[WorkflowNode] = []
        visited: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visited:
                return
            for dependency in self._dependencies(node_id):
                if dependency in node_by_id:
                    visit(dependency)
            visited.add(node_id)
            ordered.append(node_by_id[node_id])

        for node in self.nodes:
            visit(node.node_id)
        return ordered

    def _dependencies(self, node_id: str) -> list[str]:
        return [edge.source for edge in self.edges if edge.target == node_id]

    def _final_output(self, node_results: list[WorkflowNodeResult]) -> Any:
        for result in reversed(node_results):
            if result.success:
                return result.output
        return None

    def _error_record(self, result: WorkflowNodeResult) -> dict[str, Any]:
        return {
            "node_id": result.node_id,
            "node_name": result.name,
            "code": result.error_code or "WORKFLOW_NODE_FAILED",
            "message": result.error or "Workflow node failed.",
        }

    def _elapsed_ms(self, started_at: float) -> float:
        return round((perf_counter() - started_at) * 1000, 2)
