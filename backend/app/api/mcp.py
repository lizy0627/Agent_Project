import re
from typing import Any

from fastapi import APIRouter

from backend.app.core.logger import get_logger
from backend.app.mcp.manager import MCPManager


logger = get_logger(__name__)
router = APIRouter(prefix="/mcp", tags=["mcp"])
SENSITIVE_ERROR_PATTERN = re.compile(
    r"(?i)(authorization|token|secret|api[_-]?key|password)(\s*[=:]\s*)([^\s,;]+)"
)


@router.get("/health")
def mcp_health() -> dict[str, Any]:
    """Return per-server MCP discovery health without exposing secrets."""

    manager = MCPManager()
    enabled_server_names = {
        str(server.get("key") or "")
        for server in manager.list_enabled_servers()
    }
    servers = []

    for server in manager.list_servers():
        server_name = str(server.get("key") or server.get("name") or "")
        enabled = bool(server.get("enabled")) and server_name in enabled_server_names
        tools_count = 0
        error = ""

        if enabled:
            try:
                tools_count = len(manager.list_tools(server_name))
                error = _sanitize_error(manager.get_tool_errors().get(server_name, ""))
            except Exception as exc:
                logger.warning(
                    "MCP health check failed for server: server_name=%s error_type=%s",
                    server_name,
                    exc.__class__.__name__,
                )
                error = _sanitize_error(str(exc))

        servers.append(
            {
                "server_name": server_name,
                "enabled": enabled,
                "transport": server.get("transport"),
                "url": server.get("url"),
                "tools_count": tools_count,
                "error": error,
            }
        )

    return {
        "success": True,
        "servers": servers,
    }


def _sanitize_error(error: str) -> str:
    return SENSITIVE_ERROR_PATTERN.sub(r"\1\2***", str(error or ""))
