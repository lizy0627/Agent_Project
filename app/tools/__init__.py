"""Tool integration modules."""

from app.tools.calculator import CalculateTool
from app.mcp.manager import MCPManager
from app.tools.mcp_tool import MCPTool
from app.tools.summarize_text import SummarizeTextTool
from app.tools.time_tool import CurrentTimeTool
from app.tools.tool_manager import ToolManager
from app.tools.web_reader import WebReaderTool
from app.tools.web_search import WebSearchTool


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
    if mcp_enabled:
        manager.register(MCPTool(manager=mcp_manager))
    return manager
