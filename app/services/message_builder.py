import json

from app.services.agent_types import ChatMessage
from app.tools.base import ToolResult


class MessageBuilder:
    """Build model messages by adding tool and search workflow context."""

    def build_chat_messages(
        self,
        system_prompt: str,
        history: list[ChatMessage],
        user_message: str,
        max_context_rounds: int | None = None,
    ) -> list[ChatMessage]:
        """Build system prompt, bounded history, and the current user message."""

        selected_history = history
        if max_context_rounds is not None:
            selected_history = history[-max_context_rounds * 2 :] if max_context_rounds > 0 else []

        return [
            {
                "role": "system",
                "content": system_prompt,
            },
            *selected_history,
            {
                "role": "user",
                "content": user_message,
            },
        ]

    def with_tool_result(
            self,
            messages: list[ChatMessage],
            tool_result: ToolResult | None,
        ) -> list[ChatMessage]:
            if tool_result is None:
                return messages

            payload = {
                "tool_name": tool_result.name,
                "success": tool_result.success,
                "result": tool_result.result,
                "error": tool_result.error,
                "error_code": tool_result.error_code,
                "error_message": tool_result.error_message,
                "retryable": tool_result.retryable,
            }
            if tool_result.name == "web_search":
                search_system_prompt = (
                    "你正在基于 web_search 返回的 Tavily 搜索结果回答用户问题。必须遵守："
                    "1. 将搜索结果整理成自然语言回答，不要直接输出或复述 JSON；"
                    "2. 只基于搜索结果回答，不编造搜索结果中没有的信息；"
                    "3. 对多个来源进行交叉总结，合并重复信息，指出关键信息差异；"
                    "4. 如果搜索结果不足、冲突或无法支持结论，要明确说明信息不足；"
                    "5. 使用中文分点总结，结构清晰；"
                    "6. 最后列出“参考来源”，来源格式必须是 [标题](URL)。"
                )
                tool_context = (
                    "已先执行 web_search 联网搜索工具。请根据下面的 JSON 搜索结果回答用户最初的问题。\n"
                    f"{json.dumps(payload, ensure_ascii=False)}"
                )
                return [
                    *messages,
                    {
                        "role": "system",
                        "content": search_system_prompt,
                    },
                    {
                        "role": "user",
                        "content": tool_context,
                    },
                ]

            if tool_result.name == "mcp_tool":
                mcp_system_prompt = """
    你正在基于 MCP 工具返回结果回答。

    绝对规则：

    1. 先检查 JSON:

    success=true / false

    2. 如果 success=true：

    说明工具调用成功。

    严禁输出：

    * MCP SDK未安装
    * 请执行 pip install
    * MCP失败
    * Server未启动

    除非 error 字段真实包含这些内容。

    3. success=true 时：

    必须基于 result.data 内容回答。

    4. success=false 时：

    只能复述 error 字段。

    禁止编造错误。

    5. 不要猜测失败原因。

    6. 不要复述 JSON。

    7. 使用中文。

    """
                tool_execution_status = (
                    "工具调用成功"
                    if tool_result.success
                    else "工具调用失败"
                )
                tool_context = f"""
    状态:

    {tool_execution_status}

    工具结果:

    {json.dumps(payload,ensure_ascii=False)}

    请回答原问题。
    """
                return [
                    *messages,
                    {
                        "role": "system",
                        "content": mcp_system_prompt,
                    },
                    {
                        "role": "user",
                        "content": tool_context,
                    },
                ]

            tool_context = (
                "已先执行本地工具调用。请基于工具结果回答用户最初的问题；"
                "如果工具失败，请说明失败原因并给出可行的下一步。\n"
                f"{json.dumps(payload, ensure_ascii=False)}"
            )
            return [
                *messages,
                {
                    "role": "user",
                    "content": tool_context,
                },
            ]
    def with_search_workflow_result(
            self,
            messages: list[ChatMessage],
            tool_result: ToolResult,
        ) -> list[ChatMessage]:
            payload = {
                "tool_name": tool_result.name,
                "success": tool_result.success,
                "result": tool_result.result,
                "error": tool_result.error,
                "error_code": tool_result.error_code,
                "error_message": tool_result.error_message,
                "retryable": tool_result.retryable,
            }
            search_system_prompt = (
                "你是一个严谨的联网研究助手。你已经获得 Tavily 搜索摘要；"
                "对需要深度分析的问题，JSON 中还可能包含前几个网页的正文摘录。"
                "请只基于这些材料回答用户最初的问题，不要编造材料中没有的信息。"
                "需要对多个来源进行交叉总结，合并重复信息，并说明材料中的差异或不确定性。"
                "如果 JSON 中 read_pages 为空，请只基于 search_results 中的 title、url、content/snippet 总结。"
                "如果 JSON 中 context_limited 为 true，或搜索、网页读取信息不足，要明确说明哪些结论无法确认。"
                "最终回答必须使用中文，并包含以下四个部分："
                "一、结论；二、关键要点；三、详细解释；四、参考来源。"
                "参考来源必须使用 Markdown 链接格式：[标题](URL)。"
            )
            tool_context = (
                "已完成联网搜索工作流：用户问题 -> Tavily 搜索 -> 按需读取网页 -> 汇总材料。"
                "请基于下面 JSON 中的搜索摘要和可用网页正文生成最终回答。\n"
                f"{json.dumps(payload, ensure_ascii=False)}"
            )
            return [
                *messages,
                {
                    "role": "system",
                    "content": search_system_prompt,
                },
                {
                    "role": "user",
                    "content": tool_context,
                },
            ]
