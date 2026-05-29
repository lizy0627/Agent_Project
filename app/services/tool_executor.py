from typing import Any

from app.core.logger import get_logger
from app.core.safe_logging import safe_log_data
from app.mcp.manager import MCPManager
from app.services.agent_planner import PlannedToolCall
from app.tools.base import ToolResult
from app.tools.registry import ToolRegistry


logger = get_logger(__name__)


class ToolExecutor:
    """Execute planned tool calls through the unified ToolRegistry."""

    def __init__(self, tool_registry: ToolRegistry, mcp_manager: MCPManager) -> None:
        self.tool_registry = tool_registry
        self.mcp_manager = mcp_manager

    def call_planned_tool(self, planned_call: PlannedToolCall | None) -> ToolResult | None:
        logger.info(
            "EXEC_TOOL=%s ARGS=%s",
            planned_call.name if planned_call else None,
            safe_log_data(planned_call.arguments) if planned_call else None,
        )
        if planned_call is None:
            logger.info("No tool call needed for current user message")
            return None

        tool_result = self.tool_registry.run_tool(planned_call.name, planned_call.arguments)
        return self._with_route_reason(tool_result, self._planned_route_reason(planned_call))

    def _planned_route_reason(self, planned_call: PlannedToolCall) -> str:
        return planned_call.route_reason or str(planned_call.arguments.get("route_reason") or "")

    def _with_route_reason(self, tool_result: ToolResult, route_reason: str) -> ToolResult:
        if not route_reason or not isinstance(tool_result.result, dict):
            return tool_result

        result = dict(tool_result.result)
        result.setdefault("route_reason", route_reason)
        return ToolResult(
            name=tool_result.name,
            success=tool_result.success,
            result=result,
            error=tool_result.error,
            duration_ms=tool_result.duration_ms,
            error_code=tool_result.error_code,
            error_message=tool_result.error_message,
            retryable=tool_result.retryable,
        )

    def _safe_planned_tool_log(self, planned_call: PlannedToolCall | None) -> dict[str, Any] | None:
        if planned_call is None:
            return None
        return {
            "name": planned_call.name,
            "arguments": safe_log_data(planned_call.arguments),
            "route_score": planned_call.route_score,
            "route_reason": planned_call.route_reason,
        }
