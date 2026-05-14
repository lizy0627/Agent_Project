"""Tool integration modules."""

from app.tools.calculator import CalculateTool
from app.tools.summarize_text import SummarizeTextTool
from app.tools.time_tool import CurrentTimeTool
from app.tools.tool_manager import ToolManager


def create_default_tool_manager() -> ToolManager:
    manager = ToolManager()
    manager.register(CurrentTimeTool())
    manager.register(CalculateTool())
    manager.register(SummarizeTextTool())
    return manager
