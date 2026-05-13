from openai import OpenAI

from app.core.config import Settings


class DashScopeAgent:
    """一个最小 Agent：负责组织消息并调用 DashScope 模型。"""

    def __init__(self, settings: Settings) -> None:
        """初始化 OpenAI 兼容客户端。"""

        # DashScope 提供 OpenAI 兼容模式，所以这里使用 openai SDK 调用。
        self.client = OpenAI(
            api_key=settings.dashscope_api_key,
            base_url=settings.dashscope_base_url,
        )

        # 保存默认模型，方便后续请求复用。
        self.model = settings.dashscope_model

    def chat(self, message: str, system_prompt: str | None = None) -> str:
        """发送一次基础聊天请求，并返回模型文本。"""

        # system 消息定义 Agent 的行为；user 消息承载用户输入。
        messages = [
            {
                "role": "system",
                "content": system_prompt or "你是一个简洁、可靠的中文 AI 助手。",
            },
            {
                "role": "user",
                "content": message,
            },
        ]

        # 调用 DashScope 的 Chat Completions 接口。
        completion = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
        )

        # 取出第一条候选回答；最小项目只处理普通文本响应。
        reply = completion.choices[0].message.content
        return reply or ""
