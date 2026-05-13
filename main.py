from fastapi import Depends, FastAPI

from app.core.config import Settings, get_settings
from app.schemas import ChatRequest, ChatResponse
from app.services.dashscope_agent import DashScopeAgent


app = FastAPI(
    title="DashScope Minimal Agent",
    description="基于 FastAPI 和 DashScope API 的最小聊天 Agent 示例。",
    version="0.1.0",
)


def get_agent(settings: Settings = Depends(get_settings)) -> DashScopeAgent:
    """创建 Agent 实例，并通过 Depends 注入到接口中。"""

    return DashScopeAgent(settings)


@app.get("/")
def health_check() -> dict[str, str]:
    """健康检查接口，用于确认服务已经启动。"""

    return {"status": "ok", "message": "DashScope Agent is running"}


@app.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    agent: DashScopeAgent = Depends(get_agent),
) -> ChatResponse:
    """基础聊天接口：接收用户消息，返回 Agent 回复。"""

    # 将请求交给 Agent，由 Agent 负责组织上下文并调用模型。
    reply = agent.chat(
        message=request.message,
        system_prompt=request.system_prompt,
    )

    return ChatResponse(reply=reply, model=agent.model)
