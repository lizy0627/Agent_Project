from typing import Any

from app.core.config import get_settings
from app.core.logger import get_logger
from app.mcp.client import MCPClient
from app.mcp.config import MCPServerConfig, load_server_configs


logger = get_logger(__name__)


class MCPManager:
    """Manage configured MCP servers and route tool calls."""

    def __init__(
        self,
        servers: dict[str, MCPServerConfig] | None = None,
        timeout_seconds: int | None = None,
        modelscope_url: str | None = None,
    ) -> None:
        settings = get_settings()
        resolved_modelscope_url = modelscope_url or settings.modelscope_mcp_url
        resolved_timeout = timeout_seconds or settings.mcp_timeout_seconds
        self.servers = servers or load_server_configs(modelscope_url=resolved_modelscope_url)
        self.client = MCPClient(self.servers, timeout_seconds=resolved_timeout)

    def list_servers(self) -> list[dict[str, Any]]:
        """Return configured MCP servers."""

        return [
            {
                "key": config.key,
                "name": config.name,
                "transport": config.transport,
                "url": config.url,
                "enabled": config.enabled,
                "description": config.description,
            }
            for config in self.servers.values()
        ]

    def list_all_tools(self) -> dict[str, Any]:
        """List tools from every enabled MCP server."""

        results: dict[str, Any] = {}
        for server_name, config in self.servers.items():
            if not config.enabled:
                continue
            results[server_name] = self.client.list_tools(server_name)
        return results

    def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Call a tool on a named MCP server."""

        return self.client.call_tool(server_name, tool_name, arguments or {})

    def search_tool_by_keyword(self, keyword: str) -> list[dict[str, Any]]:
        """Find MCP tools whose name or description contains the keyword."""

        normalized_keyword = keyword.strip().lower()
        if not normalized_keyword:
            return []

        matches: list[dict[str, Any]] = []
        for server_name, list_result in self.list_all_tools().items():
            if not list_result.get("success"):
                continue

            tools = (list_result.get("data") or {}).get("tools", [])
            if not isinstance(tools, list):
                continue

            for tool in tools:
                if not isinstance(tool, dict):
                    continue
                searchable = " ".join(
                    str(tool.get(field) or "")
                    for field in ("name", "description", "title")
                ).lower()
                if normalized_keyword in searchable:
                    matches.append(
                        {
                            "server": server_name,
                            "tool": tool,
                        }
                    )

        return matches
