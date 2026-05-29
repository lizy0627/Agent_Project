import json
import sys
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.core.logger import get_logger, setup_logging
from app.mcp.manager import MCPManager


logger = get_logger(__name__)
TOOL_CANDIDATES = ("search", "tavily_search", "web_search")
QUERY = "今天AI新闻"


def main() -> None:
    setup_logging()
    manager = MCPManager()

    try:
        tools = manager.list_tools("tavily")
        logger.info("tools:")
        for tool in tools:
            logger.info("* %s", tool.get("name"))

        tool_name = _select_tool_name(tools)
        if not tool_name:
            logger.info("success=%s", False)
            logger.info("error=%s", f"No Tavily search tool found in candidates: {TOOL_CANDIDATES}")
            return

        result = manager.call_tool("tavily", tool_name, {"query": QUERY})
        text = json.dumps(result, ensure_ascii=False, indent=2)

        logger.info("tool=%s", tool_name)
        logger.info("success=%s", result.get("success"))
        logger.info("error=%s", result.get("error") or "")
        logger.info("response_length=%s", len(text))
        logger.info("first_500_chars=")
        logger.info("%s", text[:500])
    except Exception:
        logger.exception("Tavily connection test failed")


def _select_tool_name(tools: list[dict[str, Any]]) -> str:
    by_name = {
        _normalize_tool_name(str(tool.get("name") or tool.get("tool_name") or "")): str(tool.get("name") or "").strip()
        for tool in tools
    }
    for candidate in TOOL_CANDIDATES:
        tool_name = by_name.get(_normalize_tool_name(candidate))
        if tool_name:
            return tool_name
    return ""


def _normalize_tool_name(tool_name: str) -> str:
    return str(tool_name or "").strip().replace("-", "_").casefold()


if __name__ == "__main__":
    main()
