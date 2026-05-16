import json
import sys
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.core.config import get_settings
from app.core.logger import setup_logging
from app.mcp.manager import MCPManager


EXAMPLE_QUERY = "搜索 Qwen3 相关模型"


def main() -> None:
    setup_logging()
    settings = get_settings()
    manager = MCPManager(
        timeout_seconds=settings.mcp_timeout_seconds,
        modelscope_url=settings.modelscope_mcp_url,
    )

    list_result = manager.client.list_tools("modelscope")
    if not list_result.get("success"):
        print(json.dumps(list_result, ensure_ascii=False, indent=2))
        return

    tool = select_tool((list_result.get("data") or {}).get("tools", []))
    tool_name = str(tool.get("name") or "search")
    arguments = build_arguments(EXAMPLE_QUERY, tool)
    result = manager.call_tool("modelscope", tool_name, arguments)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def select_tool(tools: Any) -> dict[str, Any]:
    if not isinstance(tools, list):
        return {"name": "search"}

    valid_tools = [tool for tool in tools if isinstance(tool, dict)]
    if not valid_tools:
        return {"name": "search"}

    def score(tool: dict[str, Any]) -> int:
        name = str(tool.get("name") or "").lower()
        description = str(tool.get("description") or "").lower()
        searchable = f"{name} {description}"
        value = 0
        if "search" in searchable or "搜索" in searchable:
            value += 20
        if "model" in searchable or "模型" in searchable:
            value += 10
        return value

    return max(valid_tools, key=score)


def build_arguments(query: str, tool: dict[str, Any]) -> dict[str, Any]:
    input_schema = tool.get("inputSchema") or tool.get("input_schema") or {}
    properties = input_schema.get("properties", {}) if isinstance(input_schema, dict) else {}
    if not isinstance(properties, dict) or not properties:
        return {"query": query}

    arguments: dict[str, Any] = {}
    for property_name, property_schema in properties.items():
        lowered_name = str(property_name).lower()
        if any(keyword in lowered_name for keyword in ("query", "keyword", "search", "q", "name")):
            arguments[property_name] = query
        elif any(keyword in lowered_name for keyword in ("limit", "count", "size", "max_results", "top_k")):
            arguments[property_name] = 5
        elif isinstance(property_schema, dict) and "default" in property_schema:
            arguments[property_name] = property_schema["default"]

    required = input_schema.get("required", []) if isinstance(input_schema, dict) else []
    if isinstance(required, list):
        for property_name in required:
            arguments.setdefault(property_name, query)

    return arguments or {"query": query}


if __name__ == "__main__":
    main()
