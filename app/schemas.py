from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """聊天请求体。"""

    # 用户输入的问题或指令。
    message: str = Field(..., min_length=1, description="用户消息")

    # 可选系统提示词，用于定义 Agent 的角色和行为边界。
    system_prompt: str | None = Field(
        default=None,
        description="系统提示词",
    )


class ChatResponse(BaseModel):
    """聊天响应体。"""

    # Agent 返回给用户的回答。
    reply: str

    # 本次调用使用的模型名称。
    model: str
