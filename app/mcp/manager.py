from typing import Any

from app.core.config import get_settings
from app.core.logger import get_logger
from app.mcp.client import MCPClient
from app.mcp.config import load_server_configs
from app.mcp.schema import MCPServerConfig, MCPToolInfo


logger = get_logger(__name__)


class MCPManager:
    """Manage configured MCP servers, tool discovery, cache, and calls."""

    def __init__(
        self,
        servers: dict[str, MCPServerConfig] | None = None,
        timeout_seconds: int | None = None,
        modelscope_url: str | None = None,
    ) -> None:
        settings = get_settings()
        resolved_timeout = timeout_seconds or settings.mcp_timeout_seconds
        self.servers = servers or load_server_configs(modelscope_url=modelscope_url)
        self.client = MCPClient(self.servers, timeout_seconds=resolved_timeout)
        self._tools_cache: dict[str, list[MCPToolInfo]] = {}
        self._tool_errors: dict[str, str] = {}

    def list_servers(self) -> list[dict[str, Any]]:
        return [server.model_dump(mode="json") for server in self.servers.values()]

    def list_enabled_servers(self) -> list[dict[str, Any]]:
        return [
            server.model_dump(mode="json")
            for server in self.servers.values()
            if server.enabled
        ]

    def get_server(self, server_name: str) -> MCPServerConfig | None:
        return self.servers.get(server_name)

    def list_tools(self, server_name: str) -> list[dict[str, Any]]:
        """Return cached tools for one server, discovering them on first use."""

        if server_name in self._tools_cache:
            return [tool.model_dump(mode="json") for tool in self._tools_cache[server_name]]

        server = self.get_server(server_name)
        if server is None:
            logger.warning("MCP list_tools skipped; server not configured: server_name=%s", server_name)
            return []
        if not server.enabled:
            logger.info("MCP list_tools skipped; server disabled: server_name=%s", server_name)
            return []

        result = self.client.list_tools(server)
        if not result.get("success"):
            error = str(result.get("error") or "Unknown MCP list_tools error")
            self._tool_errors[server_name] = error
            logger.warning("MCP list_tools failed: server_name=%s error=%s", server_name, error)
            return []

        tools = self._normalize_tools(server_name, (result.get("data") or {}).get("tools", []))
        self._tools_cache[server_name] = tools
        self._tool_errors.pop(server_name, None)
        return [tool.model_dump(mode="json") for tool in tools]

    def list_all_tools(self) -> dict[str, list[dict[str, Any]]]:
        """Return tools from every enabled server; failed servers do not stop others."""

        results: dict[str, list[dict[str, Any]]] = {}
        for server in self.servers.values():
            if not server.enabled:
                continue
            try:
                results[server.key] = self.list_tools(server.key)
            except Exception as exc:
                self._tool_errors[server.key] = str(exc)
                logger.exception("MCP list_all_tools failed for server: server_name=%s", server.key)
                results[server.key] = []
        return results

    def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        server = self.get_server(server_name)
        if server is None:
            return self.client.call_tool(server_name, tool_name, arguments or {})
        return self.client.call_tool(server, tool_name, arguments or {})

    def refresh_tools_cache(self) -> dict[str, dict[str, Any]]:
        """Refresh every enabled server cache and return discovery status."""

        self._tools_cache.clear()
        self._tool_errors.clear()
        results: dict[str, dict[str, Any]] = {}
        for server in self.servers.values():
            if not server.enabled:
                continue
            result = self.client.list_tools(server)
            results[server.key] = result
            if not result.get("success"):
                self._tool_errors[server.key] = str(result.get("error") or "")
                logger.warning(
                    "MCP tool cache refresh failed: server_name=%s error=%s",
                    server.key,
                    result.get("error"),
                )
                continue
            self._tools_cache[server.key] = self._normalize_tools(
                server.key,
                (result.get("data") or {}).get("tools", []),
            )
        return results

    def get_tool_errors(self) -> dict[str, str]:
        return dict(self._tool_errors)

    def _normalize_tools(self, server_name: str, tools: Any) -> list[MCPToolInfo]:
        if not isinstance(tools, list):
            return []

        normalized: list[MCPToolInfo] = []
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            name = str(tool.get("name") or tool.get("tool_name") or "").strip()
            if not name:
                continue
            input_schema = tool.get("inputSchema") or tool.get("input_schema") or {}
            if not isinstance(input_schema, dict):
                input_schema = {}
            normalized.append(
                MCPToolInfo(
                    server_name=server_name,
                    name=name,
                    description=str(tool.get("description") or tool.get("title") or ""),
                    input_schema=input_schema,
                    raw=tool,
                )
            )
        return normalized
