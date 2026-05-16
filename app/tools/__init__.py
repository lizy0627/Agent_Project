"""Tool integration modules."""

from app.tools.calculator import CalculateTool
from app.tools.mcp_tool import MCPTool
from app.tools.summarize_text import SummarizeTextTool
from app.tools.time_tool import CurrentTimeTool
from app.tools.tool_manager import ToolManager
from app.tools.web_reader import WebReaderTool
from app.tools.web_search import WebSearchTool


def create_default_tool_manager(
    tavily_api_key: str | None = None,
    web_search_provider: str = "tavily",
    mcp_enabled: bool = True,
) -> ToolManager:
    manager = ToolManager()
    manager.register(CurrentTimeTool())
    manager.register(CalculateTool())
    manager.register(SummarizeTextTool())
    manager.register(WebSearchTool())
    manager.register(WebReaderTool())
    if mcp_enabled:
        manager.register(MCPTool())
    return manager
