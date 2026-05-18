import sys
from pathlib import Path
from pprint import pformat
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.core.config import get_settings
from app.core.logger import setup_logging
from app.services.dashscope_agent import DashScopeAgent


USER_MESSAGE = "请使用 MCP fetch 工具抓取 https://docs.python.org/3/tutorial/"


def print_diagnostics(agent: DashScopeAgent, user_message: str, planned: Any) -> None:
    route_result = agent.mcp_router.route(user_message)
    summarize_result = agent._extract_text_to_summarize(user_message)
    web_search_result = agent._looks_like_search_request(user_message)

    print("user_message=", user_message)
    print("route结果=", pformat(route_result))
    print("summarize结果=", summarize_result)
    print("web_search结果=", web_search_result)

    if planned is None:
        print("reason=", "_plan_tool_call returned None")
    elif getattr(planned, "name", None) != "mcp_tool":
        print("reason=", f"_plan_tool_call selected {getattr(planned, 'name', None)!r}, expected 'mcp_tool'")
    elif planned.arguments.get("server_name") != "fetch":
        print("reason=", f"server_name is {planned.arguments.get('server_name')!r}, expected 'fetch'")
    elif planned.arguments.get("tool_name") != "fetch":
        print("reason=", f"tool_name is {planned.arguments.get('tool_name')!r}, expected 'fetch'")


def main() -> None:
    setup_logging()
    settings = get_settings()
    if not settings.dashscope_api_key:
        settings = settings.model_copy(update={"dashscope_api_key": "route-test-key"})

    agent = DashScopeAgent(settings)
    messages = [
        {
            "role": "user",
            "content": USER_MESSAGE,
        }
    ]

    planned = agent._plan_tool_call(messages)
    if planned is None:
        print("name=", None)
        print("arguments=", None)
        print_diagnostics(agent, USER_MESSAGE, planned)
        return

    print("name=", planned.name)
    print("arguments=", planned.arguments)

    if (
        planned.name != "mcp_tool"
        or planned.arguments.get("server_name") != "fetch"
        or planned.arguments.get("tool_name") != "fetch"
    ):
        print_diagnostics(agent, USER_MESSAGE, planned)


if __name__ == "__main__":
    main()
