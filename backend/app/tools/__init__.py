"""Tool integration modules."""

from backend.app.tools.calculator import CalculateTool
from backend.app.mcp.manager import MCPManager
from backend.app.tools.mcp_tool import MCPTool
from backend.app.tools.summarize_text import SummarizeTextTool
from backend.app.tools.time_tool import CurrentTimeTool
from backend.app.tools.registry import ToolRegistry
from backend.app.tools.tool_manager import ToolManager
from backend.app.tools.read_webpage import ReadWebpageTool, WebReaderTool
from backend.app.tools.web_search import WebSearchTool


def create_default_tool_manager(
    tavily_api_key: str | None = None,
    web_search_provider: str = "tavily",
    web_search_timeout_seconds: float = 5.0,
    web_reader_timeout_seconds: float = 5.0,
    mcp_enabled: bool = True,
    mcp_manager: MCPManager | None = None,
) -> ToolManager:
    manager = ToolManager()
    manager.register(CurrentTimeTool())
    manager.register(CalculateTool())
    manager.register(SummarizeTextTool())
    manager.register(
        WebSearchTool(
            api_key=tavily_api_key,
            provider=web_search_provider,
            timeout_seconds=web_search_timeout_seconds,
        )
    )
    manager.register(WebReaderTool(timeout_seconds=web_reader_timeout_seconds))
    manager.register(ReadWebpageTool(timeout_seconds=web_reader_timeout_seconds))
    if mcp_enabled:
        manager.register(MCPTool(manager=mcp_manager))
    return manager


__all__ = [
    "CalculateTool",
    "CurrentTimeTool",
    "MCPManager",
    "MCPTool",
    "ReadWebpageTool",
    "SummarizeTextTool",
    "ToolManager",
    "ToolRegistry",
    "WebReaderTool",
    "WebSearchTool",
    "create_default_tool_manager",
]
