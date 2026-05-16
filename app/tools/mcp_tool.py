from typing import Any

from app.core.config import get_settings
from app.core.logger import get_logger
from app.mcp.manager import MCPManager


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
            return {
                "success": False,
                "server": server_name,
                "tool": tool_name,
                "data": None,
                "error": "MCP is disabled by configuration.",
            }

        try:
            manager = self.manager or MCPManager()
            return manager.call_tool(server_name, tool_name, arguments or {})
        except Exception as exc:
            logger.exception("MCP tool wrapper failed: server=%s tool=%s", server_name, tool_name)
            return {
                "success": False,
                "server": server_name,
                "tool": tool_name,
                "data": None,
                "error": str(exc),
            }
