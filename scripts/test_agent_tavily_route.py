import json
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.core.config import get_settings
from app.core.logger import setup_logging
from app.mcp.schema import MCPToolInfo
from app.services.dashscope_agent import DashScopeAgent


USER_MESSAGE = "请使用 Tavily 搜索今天AI新闻"


def main() -> None:
    setup_logging()
    settings = get_settings()
    if not settings.dashscope_api_key:
        settings = settings.model_copy(update={"dashscope_api_key": "route-test-key"})

    agent = DashScopeAgent(settings)
    agent.mcp_manager._tools_cache["tavily"] = [
        MCPToolInfo(
            server_name="tavily",
            name="search",
            description="Tavily search",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                    },
                },
                "required": ["query"],
            },
            raw={},
        )
    ]

    planned = agent._plan_tool_call(
        [
            {
                "role": "user",
                "content": USER_MESSAGE,
            }
        ]
    )

    print("name=", planned.name if planned else None)
    print(
        "arguments=",
        json.dumps(planned.arguments if planned else None, ensure_ascii=False, indent=2),
    )


if __name__ == "__main__":
    main()
