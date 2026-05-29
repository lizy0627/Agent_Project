from app.tools import create_default_tool_manager
from app.tools.base import BaseTool
from app.tools.registry import TOOL_EXECUTION_ERROR, ToolRegistry


class EchoTool(BaseTool):
    name = "echo"
    description = "Echo text."
    args_schema = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }

    def run(self, text: str) -> dict[str, str]:
        return {"text": text}


class FailingTool(BaseTool):
    name = "failing"
    description = "Always fail."
    args_schema = {"type": "object", "properties": {}}

    def run(self) -> dict[str, object]:
        return {"success": False, "error": "bad args"}


def test_tool_registry_runs_registered_tool():
    registry = ToolRegistry()
    registry.register(EchoTool())

    result = registry.run_tool("echo", {"text": "hello"})

    assert result.success is True
    assert result.result == {"text": "hello"}
    assert registry.get_tool("echo").name == "echo"
    assert registry.list_tools()[0]["args_schema"]["required"] == ["text"]


def test_tool_registry_normalizes_failed_tool_result():
    registry = ToolRegistry()
    registry.register(FailingTool())

    result = registry.run_tool("failing", {})

    assert result.success is False
    assert result.error == "bad args"
    assert result.error_code == TOOL_EXECUTION_ERROR


def test_default_tool_registry_includes_existing_tools_and_read_webpage_alias():
    registry = create_default_tool_manager(mcp_enabled=False)

    tool_names = {tool["name"] for tool in registry.list_tools()}

    assert {
        "calculate",
        "get_current_time",
        "read_webpage",
        "summarize_text",
        "web_reader",
        "web_search",
    }.issubset(tool_names)
