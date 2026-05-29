import json
import sys
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.core.config import get_settings
from app.core.logger import get_logger, setup_logging
from app.mcp.manager import MCPManager


logger = get_logger(__name__)
SERVER_NAME = "fetch"
PREFERRED_TOOL_NAME = "fetch"
TEST_URL = "https://docs.python.org/3/tutorial/"
FETCH_ARGUMENTS = {"url": TEST_URL, "max_length": 2000}


def main() -> None:
    setup_logging()
    settings = get_settings()
    manager = MCPManager(
        timeout_seconds=settings.mcp_timeout_seconds,
        modelscope_url=settings.modelscope_mcp_url,
    )

    tools_result = manager.client.list_tools(SERVER_NAME)
    _raise_if_failed(tools_result, "list fetch tools")
    tools = (tools_result.get("data") or {}).get("tools", [])
    tool_names = _tool_names(tools)
    tool_name = _select_fetch_tool_name(tool_names)

    logger.info("tools:")
    for name in tool_names:
        logger.info("- %s", name)
    if tool_name != PREFERRED_TOOL_NAME:
        logger.info("selected_tool_name: %s", tool_name)

    call_result = manager.call_tool(SERVER_NAME, tool_name, FETCH_ARGUMENTS)
    if not call_result.get("success"):
        logger.info("success: false")
        logger.info("error: %s", call_result.get("error") or call_result)
        _raise_if_failed(call_result, f"call {tool_name} tool")

    text = _extract_text(call_result.get("data"))
    logger.info("success: true")
    logger.info("error:")
    logger.info("content_length: %s", len(text))
    logger.info("first_500_chars:")
    logger.info("%s", text[:500])


def _tool_names(tools: Any) -> list[str]:
    if not isinstance(tools, list):
        return []

    names: list[str] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        name = str(tool.get("name") or tool.get("tool_name") or "").strip()
        if name:
            names.append(name)
    return names


def _select_fetch_tool_name(tool_names: list[str]) -> str:
    if PREFERRED_TOOL_NAME in tool_names:
        return PREFERRED_TOOL_NAME
    if tool_names:
        return tool_names[0]
    raise RuntimeError("Fetch MCP server returned no tools.")


def _raise_if_failed(result: dict[str, Any], action: str) -> None:
    if result.get("success"):
        return
    raise RuntimeError(f"MCP {action} failed: {result.get('error') or result}")


def _extract_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        parts: list[str] = []
        for key in ("text", "content", "result", "data", "structuredContent", "structured_content"):
            if key in value:
                parts.append(_extract_text(value[key]))
        if parts:
            return "\n".join(part for part in parts if part)
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "\n".join(_extract_text(item) for item in value)
    return str(value)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("Fetch connection test failed")
        raise
