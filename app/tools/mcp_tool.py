from typing import Any

from app.core.config import get_settings
from app.core.logger import get_logger
from app.mcp.manager import MCPManager
from app.mcp.schema import MCPCallResult


logger = get_logger(__name__)


class MCPTool:
    """Expose MCP servers as one ordinary ToolManager tool."""

    name = "mcp_tool"
    description = "Call a tool from a configured MCP server."

    def __init__(self, manager: MCPManager | None = None) -> None:
        self.manager = manager

    def run(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        settings = get_settings()
        if not settings.mcp_enabled:
            return MCPCallResult(
                success=False,
                server_name=server_name,
                tool_name=tool_name,
                arguments=arguments or {},
                data=None,
                error="MCP is disabled by configuration.",
            ).model_dump(mode="json")

        try:
            if self.manager is None:
                self.manager = MCPManager()
            result = self.manager.call_tool(server_name, tool_name, arguments or {})
            if not result.get("success") and not result.get("error"):
                result["error"] = "MCP tool call failed. Please check whether the MCP Server is running."
            return result
        except Exception as exc:
            logger.exception("MCP tool wrapper failed: server=%s tool=%s", server_name, tool_name)
            return MCPCallResult(
                success=False,
                server_name=server_name,
                tool_name=tool_name,
                arguments=arguments or {},
                data=None,
                error=str(exc),
            ).model_dump(mode="json")
