from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from app.core.config import Settings
from app.core.logger import get_logger
from app.core.safe_logging import safe_log_data, safe_log_field
from app.mcp.manager import MCPManager
from app.mcp.router import MCPRouter


logger = get_logger(__name__)
ChatMessage = dict[str, str]
DEFAULT_WEB_SEARCH_MAX_RESULTS = 3
ROUTE_THRESHOLDS = {
    "calculate": 70,
    "get_current_time": 70,
    "mcp_tool": 75,
    "summarize_text": 70,
    "web_search": 65,
}
ROUTE_PRIORITIES = {
    "calculate": 50,
    "get_current_time": 50,
    "mcp_tool": 40,
    "summarize_text": 30,
    "web_search": 20,
}
ROUTE_PRIORITY_SCORE_MARGIN = 10
MODELSCOPE_MCP_KEYWORDS = (
    "魔搭",
    "modelscope",
    "数据集",
    "dataset",
    "创空间",
    "mcp服务",
    "mcp 服务",
    "search model",
    "search models",
    "search_model",
    "search_models",
    "搜索模型",
    "搜索 模型",
    "查找模型",
    "找模型",
    "模型搜索",
)
MODELSCOPE_DEFAULT_TOOL_CANDIDATES = (
    "search",
    "modelscope_search",
    "search_models",
    "search_model",
    "model_search",
)
MODELSCOPE_QUERY_NOISE_PHRASES = (
    "相关模型",
    "模型",
    "搜索",
    "帮我",
    "魔搭",
    "关于",
)


WEB_SEARCH_ROUTE_REASON = (
    "\u68c0\u6d4b\u5230\u6700\u65b0/\u641c\u7d22/\u5b98\u7f51/github\u7b49\u5173\u952e\u8bcd"
)
MODELSCOPE_MCP_ROUTE_REASON = (
    "\u68c0\u6d4b\u5230 ModelScope/MCP \u76f8\u5173\u5173\u952e\u8bcd"
)
TIME_ROUTE_REASON = "\u68c0\u6d4b\u5230\u65f6\u95f4/\u65e5\u671f\u7c7b\u95ee\u9898"
CALCULATE_ROUTE_REASON = "\u68c0\u6d4b\u5230\u6570\u5b66\u8868\u8fbe\u5f0f"
SUMMARIZE_ROUTE_REASON = "\u68c0\u6d4b\u5230\u603b\u7ed3\u7c7b\u6307\u4ee4"


def extract_search_keyword(query: str) -> str:
    """Extract the likely ModelScope search keyword from a Chinese request."""

    cleaned = " ".join(str(query or "").strip().split())
    if not cleaned:
        return ""

    patterns = (
        r"搜索\s*(?P<keyword>.+?)(?:相关模型|模型)?(?:[。！？?!，,；;]|$)",
        r"找\s*(?P<keyword>.+?)(?:相关模型|模型)(?:[。！？?!，,；;]|$)",
        r"关于\s*(?P<keyword>.+?)(?:相关模型|模型)?(?:[。！？?!，,；;]|$)",
    )
    for pattern in patterns:
        match = re.search(pattern, cleaned, flags=re.IGNORECASE)
        if match:
            keyword = match.group("keyword").strip()
            if keyword:
                return keyword

    return cleaned


def normalize_query(query: str) -> str:
    """Normalize a ModelScope search query before sending it to MCP."""

    normalized = str(query or "").strip()
    if not normalized:
        return ""

    normalized = re.sub(
        r"\bqwen\s*-\s*(\d+)\b",
        lambda match: f"Qwen{match.group(1)}",
        normalized,
        flags=re.IGNORECASE,
    )
    for phrase in MODELSCOPE_QUERY_NOISE_PHRASES:
        normalized = normalized.replace(phrase, "")

    normalized = re.sub(r"(?i)\bmodelscope\b", "", normalized)
    normalized = re.sub(r"^[请麻烦帮忙我想要查找一下在上有关的\s]+", "", normalized)
    normalized = re.sub(r"[。！？?!，,；;：:\s]+$", "", normalized)
    normalized = " ".join(normalized.split())
    return normalized.strip()


@dataclass(frozen=True)
class PlannedToolCall:
    """A local tool call selected for the latest user message."""

    name: str
    arguments: dict[str, Any]
    route_reason: str = ""
    route_score: int = 0


@dataclass(frozen=True)
class ToolRouteCandidate:
    """A scored route candidate before threshold filtering."""

    tool_name: str
    planned_call: PlannedToolCall | None
    score: int
    threshold: int
    priority: int
    reason: str


class AgentPlanner:
    """Plan local tool calls for the latest user message."""

    def __init__(self, settings: Settings, mcp_router: MCPRouter | None = None) -> None:
        self.settings = settings
        self.mcp_router = mcp_router

    def plan(self, messages: list[ChatMessage]) -> PlannedToolCall | None:
        user_message = self.latest_user_message(messages)
        logger.info("USER=%s", safe_log_field("user_message", user_message))
        logger.info("USER_MESSAGE=%s", safe_log_field("user_message", user_message))
        if not user_message:
            return None

        candidates = self._route_candidates(user_message)
        for candidate in candidates:
            logger.info(
                "ROUTE_CANDIDATE tool=%s route_score=%s threshold=%s route_reason=%s",
                candidate.tool_name,
                candidate.score,
                candidate.threshold,
                candidate.reason,
            )

        eligible_candidates = [
            candidate
            for candidate in candidates
            if candidate.planned_call is not None and candidate.score >= candidate.threshold
        ]
        if not eligible_candidates:
            logger.info("SELECTED=%s route_score=%s route_reason=%s", None, 0, "no candidate met threshold")
            return None

        top_score = max(candidate.score for candidate in eligible_candidates)
        priority_band = [
            candidate
            for candidate in eligible_candidates
            if top_score - candidate.score <= ROUTE_PRIORITY_SCORE_MARGIN
        ]
        selected = max(
            priority_band,
            key=lambda candidate: (candidate.priority, candidate.score),
        ).planned_call
        if selected is None:
            logger.info("SELECTED=%s route_score=%s route_reason=%s", None, 0, "no route selected")
            return None
        logger.info(
            "SELECTED=%s route_score=%s route_reason=%s",
            selected.name,
            selected.route_score,
            selected.route_reason,
        )
        self._log_planned_tool(selected)
        return selected

    def _route_candidates(self, user_message: str) -> list[ToolRouteCandidate]:
        candidates: list[ToolRouteCandidate] = []
        for tool_name, planned_call, score, reason in (
            self._score_calculate_route(user_message),
            self._score_time_route(user_message),
            self._score_mcp_route(user_message),
            self._score_summarize_route(user_message),
            self._score_web_search_route(user_message),
        ):
            call = None
            if planned_call is not None:
                call = PlannedToolCall(
                    name=planned_call.name,
                    arguments=planned_call.arguments,
                    route_reason=reason,
                    route_score=score,
                )
            candidates.append(
                ToolRouteCandidate(
                    tool_name=tool_name,
                    planned_call=call,
                    score=score,
                    threshold=ROUTE_THRESHOLDS[tool_name],
                    priority=ROUTE_PRIORITIES[tool_name],
                    reason=reason,
                )
            )
        return candidates

    def _score_calculate_route(self, user_message: str) -> tuple[str, PlannedToolCall | None, int, str]:
        expression = self._extract_calculation_expression(user_message)
        if not expression:
            return "calculate", None, 0, "未检测到明确数学表达式"

        lowered = user_message.lower()
        explicit_intent = any(
            keyword in lowered
            for keyword in ("计算", "算一下", "等于多少", "calculate", "calc", "求值")
        )
        operator_count = len(re.findall(r"\*\*|[+\-*/%()]", expression))
        score = 90 if explicit_intent else 75
        if operator_count >= 2:
            score += 5
        score = min(score, 100)
        reason = f"{CALCULATE_ROUTE_REASON}，表达式={expression!r}"
        return (
            "calculate",
            PlannedToolCall(
                name="calculate",
                arguments={"expression": expression},
                route_reason=reason,
                route_score=score,
            ),
            score,
            reason,
        )

    def _score_time_route(self, user_message: str) -> tuple[str, PlannedToolCall | None, int, str]:
        if not self._looks_like_time_request(user_message):
            return "get_current_time", None, 0, "未检测到明确当前时间/日期请求"

        lowered = user_message.lower()
        exact_time_keywords = ("现在几点", "当前时间", "现在时间", "current time", "what time")
        exact_date_keywords = ("今天几号", "今天日期", "当前日期", "today's date", "today date")
        score = 95 if any(keyword in lowered for keyword in exact_time_keywords) else 90
        if any(keyword in lowered for keyword in exact_date_keywords):
            score = max(score, 90)

        return (
            "get_current_time",
            PlannedToolCall(
                name="get_current_time",
                arguments={"timezone": "Asia/Shanghai"},
                route_reason=TIME_ROUTE_REASON,
                route_score=score,
            ),
            score,
            TIME_ROUTE_REASON,
        )

    def _score_mcp_route(self, user_message: str) -> tuple[str, PlannedToolCall | None, int, str]:
        score, reason = self._mcp_route_score(user_message)
        if score < ROUTE_THRESHOLDS["mcp_tool"]:
            return "mcp_tool", None, score, reason

        planned_call = (
            self._plan_modelscope_explicit_mcp_tool(user_message)
            if self._looks_like_modelscope_mcp_request(user_message)
            else self._plan_mcp_tool(user_message)
        )
        if planned_call is None:
            return "mcp_tool", None, score, f"{reason}，但未匹配到可用 MCP 路由"

        server_name = str(planned_call.arguments.get("server_name") or "").strip().lower()
        if server_name == "modelscope" and not self._looks_like_modelscope_mcp_request(user_message):
            return "mcp_tool", None, 0, "ModelScope MCP 缺少明确关键词，拒绝普通模型词触发"

        base_reason = planned_call.route_reason or reason
        route_reason = reason if reason.startswith(base_reason) else f"{base_reason}；{reason}"
        planned_call = PlannedToolCall(
            name=planned_call.name,
            arguments=planned_call.arguments,
            route_reason=route_reason,
            route_score=score,
        )
        return "mcp_tool", planned_call, score, route_reason

    def _score_summarize_route(self, user_message: str) -> tuple[str, PlannedToolCall | None, int, str]:
        lowered = user_message.lower()
        has_summary_intent = any(
            keyword in lowered for keyword in ("总结", "摘要", "概括", "summarize", "summary")
        )
        text_to_summarize = self._extract_text_to_summarize(user_message)
        if not has_summary_intent:
            return "summarize_text", None, 0, "未检测到总结/摘要指令"
        if not text_to_summarize:
            return "summarize_text", None, 45, "检测到总结意图，但缺少足够长的待总结文本"

        score = 85
        if len(text_to_summarize) >= 120:
            score += 10
        score = min(score, 100)
        reason = f"{SUMMARIZE_ROUTE_REASON}，待总结文本长度={len(text_to_summarize)}"
        return (
            "summarize_text",
            PlannedToolCall(
                name="summarize_text",
                arguments={"text": text_to_summarize},
                route_reason=reason,
                route_score=score,
            ),
            score,
            reason,
        )

    def _score_web_search_route(self, user_message: str) -> tuple[str, PlannedToolCall | None, int, str]:
        score, reason = self._web_search_route_score(user_message)
        if score < ROUTE_THRESHOLDS["web_search"]:
            return "web_search", None, score, reason

        return (
            "web_search",
            PlannedToolCall(
                name="web_search",
                arguments={
                    "query": user_message,
                    "max_results": DEFAULT_WEB_SEARCH_MAX_RESULTS,
                    "search_depth": "basic",
                },
                route_reason=reason,
                route_score=score,
            ),
            score,
            reason,
        )

    def latest_user_message(self, messages: list[ChatMessage]) -> str:
        for message in reversed(messages):
            if message.get("role") == "user":
                return message.get("content", "")
        return ""

    def likely_tool_name_for_status(self, user_message: str) -> str | None:
        """Return a cheap high-confidence route hint for early streaming status."""

        if self._extract_calculation_expression(user_message):
            return "calculate"
        if self._looks_like_time_request(user_message):
            return "get_current_time"
        if self._mcp_route_score(user_message)[0] >= ROUTE_THRESHOLDS["mcp_tool"]:
            return "mcp_tool"
        if self._extract_text_to_summarize(user_message):
            return "summarize_text"
        if self._web_search_route_score(user_message)[0] >= ROUTE_THRESHOLDS["web_search"]:
            return "web_search"
        return None

    def _plan_mcp_tool(self, user_message: str) -> PlannedToolCall | None:
        if not self.settings.mcp_enabled:
            return None
        if self.mcp_router is None:
            return None

        route = self.mcp_router.route(user_message)
        if not route:
            return None

        server_name = str(route["server_name"])
        route_reason = str(route.get("reason") or "")
        if server_name.strip().lower() == "modelscope":
            route_reason = MODELSCOPE_MCP_ROUTE_REASON if not route_reason else f"{MODELSCOPE_MCP_ROUTE_REASON}；{route_reason}"
        planned_call = PlannedToolCall(
            name="mcp_tool",
            arguments={
                "server_name": server_name,
                "tool_name": route["tool_name"],
                "arguments": route.get("arguments") or {},
                "original_query": route.get("original_query") or user_message,
                "rewritten_query": route.get("rewritten_query") or "",
                "query_fallbacks": route.get("query_fallbacks") or [],
                "route_reason": route_reason,
            },
            route_reason=route_reason,
        )
        return planned_call

    def _plan_modelscope_explicit_mcp_tool(self, user_message: str) -> PlannedToolCall | None:
        if self.mcp_router is None:
            return None

        server_name = self.settings.mcp_default_server or "modelscope"
        if server_name != "modelscope":
            server_name = "modelscope"
        server = self.mcp_router.manager.get_server(server_name)
        if server is None or not server.enabled:
            return None

        rewritten_query = normalize_query(extract_search_keyword(user_message)) or normalize_query(user_message)
        route_reason = MODELSCOPE_MCP_ROUTE_REASON
        return PlannedToolCall(
            name="mcp_tool",
            arguments={
                "server_name": server_name,
                "tool_name": self._modelscope_fallback_tool_name(user_message),
                "arguments": {"query": rewritten_query},
                "original_query": user_message,
                "rewritten_query": rewritten_query,
                "query_fallbacks": self._modelscope_query_fallbacks(rewritten_query),
                "route_reason": route_reason,
            },
            route_reason=route_reason,
        )

    def _modelscope_fallback_tool_name(self, user_message: str) -> str:
        lowered = user_message.lower()
        if any(keyword in lowered for keyword in ("数据集", "dataset")):
            return "search_datasets"
        if any(keyword in lowered for keyword in ("创空间", "space", "studio")):
            return "search_spaces"
        if "mcp" in lowered and "服务" in lowered:
            return "search_mcp_servers"
        return "search_models"

    def _modelscope_query_fallbacks(self, query: str) -> list[str]:
        normalized = normalize_query(query)
        candidates = [normalized] if normalized else []
        lowered = normalized.lower()
        if lowered == "qwen3":
            candidates.append("Qwen")
        if lowered == "qwen-3":
            candidates.extend(["Qwen3", "Qwen"])
        return self._dedupe_nonempty(candidates)

    def _dedupe_nonempty(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        deduped: list[str] = []
        for value in values:
            cleaned = str(value or "").strip()
            if not cleaned:
                continue
            key = cleaned.casefold()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(cleaned)
        return deduped

    def _mcp_route_score(self, user_message: str) -> tuple[int, str]:
        if not self.settings.mcp_enabled:
            return 0, "MCP 未启用"
        if self.mcp_router is None:
            return 0, "MCP router 不可用"

        lowered = user_message.lower()
        if self._looks_like_modelscope_mcp_request(user_message):
            matched = self._matched_keywords(lowered, MODELSCOPE_MCP_KEYWORDS)
            score = 90 if any(keyword in matched for keyword in ("魔搭", "modelscope")) else 82
            if any(keyword in matched for keyword in ("search model", "search models", "搜索模型", "查找模型", "找模型", "模型搜索")):
                score = max(score, 88)
            return score, f"{MODELSCOPE_MCP_ROUTE_REASON}，明确关键词={matched}"

        if any(keyword in lowered for keyword in ("mcp", "工具", "tool")) and any(
            keyword in lowered for keyword in ("fetch", "抓取", "读取网页", "调用")
        ):
            return 95, "检测到明确 MCP 工具调用意图"

        if any(keyword in lowered for keyword in ("fetch", "抓取", "读取网页")) and re.search(
            r"https?://|www\.", lowered
        ):
            return 90, "检测到 fetch/网页抓取类 MCP 请求"

        if any(keyword in lowered for keyword in ("tavily", "请使用 tavily", "用 tavily")):
            return 96, "检测到明确 Tavily MCP 请求"

        if "模型" in lowered or "model" in lowered:
            return 20, "仅检测到普通模型词，未达到 ModelScope MCP 明确关键词要求"

        return 0, "未检测到明确 MCP 工具或服务关键词"

    def _plan_modelscope_mcp_tool(self, user_message: str) -> PlannedToolCall | None:
        if not self.settings.mcp_enabled:
            return None
        if not self._looks_like_modelscope_mcp_request(user_message):
            return None

        server_name = self.settings.mcp_default_server or "modelscope"
        tool = self._select_modelscope_tool(user_message, server_name)
        tool_name = str(tool.get("name") or "").strip()
        if not tool_name:
            tool_name = MODELSCOPE_DEFAULT_TOOL_CANDIDATES[0]

        rewritten_query = normalize_query(extract_search_keyword(user_message)) or normalize_query(user_message)
        arguments = self._build_mcp_tool_arguments(user_message, tool, rewritten_query)
        planned_call = PlannedToolCall(
            name="mcp_tool",
            arguments={
                "server_name": server_name,
                "tool_name": tool_name,
                "arguments": arguments,
                "original_query": user_message,
                "rewritten_query": rewritten_query,
                "route_reason": MODELSCOPE_MCP_ROUTE_REASON,
            },
            route_reason=MODELSCOPE_MCP_ROUTE_REASON,
        )
        return planned_call

    def _looks_like_modelscope_mcp_request(self, message: str) -> bool:
        lowered = message.lower()
        return any(keyword.lower() in lowered for keyword in MODELSCOPE_MCP_KEYWORDS)

    def _select_modelscope_tool(self, user_message: str, server_name: str) -> dict[str, Any]:
        try:
            manager = MCPManager(
                timeout_seconds=self.settings.mcp_timeout_seconds,
                modelscope_url=self.settings.modelscope_mcp_url,
            )
            list_result = manager.client.list_tools(server_name)
        except Exception as exc:
            logger.warning("ModelScope MCP list_tools planning failed: %s", exc)
            return {"name": MODELSCOPE_DEFAULT_TOOL_CANDIDATES[0]}

        if not list_result.get("success"):
            logger.warning("ModelScope MCP list_tools failed: error=%s", list_result.get("error"))
            return {"name": MODELSCOPE_DEFAULT_TOOL_CANDIDATES[0]}

        tools = (list_result.get("data") or {}).get("tools", [])
        if not isinstance(tools, list) or not tools:
            logger.warning("ModelScope MCP server returned no tools during planning")
            return {"name": MODELSCOPE_DEFAULT_TOOL_CANDIDATES[0]}

        selected_tool = max(
            [tool for tool in tools if isinstance(tool, dict)],
            key=lambda tool: self._modelscope_tool_score(user_message, tool),
            default={},
        )
        logger.info(
            "ModelScope MCP tool selected: tool=%s",
            selected_tool.get("name") if isinstance(selected_tool, dict) else "",
        )
        return selected_tool if isinstance(selected_tool, dict) else {}

    def _modelscope_tool_score(self, user_message: str, tool: dict[str, Any]) -> int:
        lowered_message = user_message.lower()
        tool_name = str(tool.get("name") or "").lower()
        description = str(tool.get("description") or "").lower()
        searchable = f"{tool_name} {description}"
        score = 0

        if "search" in searchable or "搜索" in searchable:
            score += 20
        if any(candidate in tool_name for candidate in MODELSCOPE_DEFAULT_TOOL_CANDIDATES):
            score += 12
        if any(keyword in lowered_message for keyword in ("模型", "model", "qwen", "通义千问")):
            score += self._category_score(searchable, ("model", "模型"))
        if any(keyword in lowered_message for keyword in ("数据集", "dataset")):
            score += self._category_score(searchable, ("dataset", "数据集"))
        if any(keyword in lowered_message for keyword in ("创空间", "space", "studio")):
            score += self._category_score(searchable, ("space", "创空间", "studio"))
        if any(keyword in lowered_message for keyword in ("论文", "paper")):
            score += self._category_score(searchable, ("paper", "论文"))
        if "mcp" in lowered_message:
            score += self._category_score(searchable, ("mcp", "服务"))

        return score

    def _category_score(self, searchable: str, category_keywords: tuple[str, ...]) -> int:
        return 10 if any(keyword in searchable for keyword in category_keywords) else 0

    def _build_mcp_tool_arguments(
        self,
        user_message: str,
        tool: dict[str, Any],
        rewritten_query: str | None = None,
    ) -> dict[str, Any]:
        input_schema = tool.get("inputSchema") or tool.get("input_schema") or {}
        properties = input_schema.get("properties", {}) if isinstance(input_schema, dict) else {}
        query = rewritten_query or normalize_query(extract_search_keyword(user_message)) or user_message
        if not isinstance(properties, dict) or not properties:
            return {"query": query}

        arguments: dict[str, Any] = {}
        for property_name, property_schema in properties.items():
            lowered_name = str(property_name).lower()
            if self._looks_like_query_argument(lowered_name):
                arguments[property_name] = query
                continue
            if self._looks_like_limit_argument(lowered_name):
                arguments[property_name] = 5
                continue

            default_value = self._schema_default_value(property_schema)
            if default_value is not None:
                arguments[property_name] = default_value

        required = input_schema.get("required", []) if isinstance(input_schema, dict) else []
        if isinstance(required, list):
            for property_name in required:
                if property_name not in arguments:
                    arguments[property_name] = query

        if not arguments:
            arguments["query"] = query
        return arguments

    def _looks_like_time_request(self, message: str) -> bool:
        lowered = message.lower()
        time_keywords = (
            "现在几点",
            "当前时间",
            "现在时间",
            "今天几号",
            "今天日期",
            "当前日期",
            "current time",
            "what time",
            "today's date",
            "today date",
        )
        return any(keyword in lowered for keyword in time_keywords)

    def _extract_calculation_expression(self, message: str) -> str | None:
        lowered = message.lower()
        has_calculation_intent = any(
            keyword in lowered
            for keyword in ("计算", "算一下", "等于多少", "calculate", "calc", "=", "求值")
        )
        if not has_calculation_intent:
            return None

        normalized = (
            message.replace("×", "*")
            .replace("÷", "/")
            .replace("^", "**")
            .replace("（", "(")
            .replace("）", ")")
        )
        allowed_chunks = re.findall(
            r"(?:sqrt|sin|cos|tan|log10|log|ceil|floor|round|abs|pow|pi|tau|e|[0-9+\-*/().,%\s])+",
            normalized,
            flags=re.IGNORECASE,
        )
        candidates = [
            chunk.strip().rstrip("=?？。")
            for chunk in allowed_chunks
            if any(char.isdigit() for char in chunk)
        ]
        if not candidates:
            return None

        expression = max(candidates, key=len).replace(",", "")
        if len(re.findall(r"[+\-*/%()]|\*\*", expression)) == 0:
            return None
        return expression

    def _extract_text_to_summarize(self, message: str) -> str | None:
        lowered = message.lower()
        if not any(keyword in lowered for keyword in ("总结", "摘要", "概括", "summarize", "summary")):
            return None

        split_match = re.search(r"[:：]\s*(.+)", message, flags=re.DOTALL)
        if split_match:
            text = split_match.group(1).strip()
        else:
            text = re.sub(
                r"^(请|帮我|麻烦)?(总结|摘要|概括|summarize|summary)(一下|下)?",
                "",
                message,
                flags=re.IGNORECASE,
            ).strip()

        return text if len(text) >= 20 else None

    def _looks_like_search_request(self, message: str) -> bool:
        """Return True when a user asks for current or external web information."""

        clean_message = message.strip()
        if not clean_message:
            return False

        lowered = message.lower()
        casual_phrases = (
            "你好",
            "您好",
            "在吗",
            "谢谢",
            "你是谁",
            "你好吗",
            "你现在好吗",
            "你怎么样",
            "hello",
            "hi",
            "thanks",
            "thank you",
            "who are you",
            "how are you",
        )
        if lowered in casual_phrases:
            return False

        chinese_keywords = (
            "搜索",
            "查一下",
            "联网",
            "最新",
            "新闻",
            "资料",
            "官网",
            "最近",
            "价格",
            "github",
            "论文",
            "教程",
        )
        english_keywords = (
            "search",
            "latest",
            "news",
            "current",
            "recent",
            "github",
            "website",
            "official",
            "price",
        )
        extra_search_keywords = (
            "联网搜索",
            "网络搜索",
            "网上搜索",
            "帮我查",
            "项目",
            "today",
        )
        strong_keywords = chinese_keywords + english_keywords + extra_search_keywords
        if any(keyword in lowered for keyword in strong_keywords):
            return True

        ambiguous_keywords = (
            "今天",
            "现在",
            "是什么",
            "怎么样",
        )
        if not any(keyword in lowered for keyword in ambiguous_keywords):
            return False

        if lowered.startswith("你"):
            return False

        if lowered.startswith("我") and not self._has_external_subject_hint(lowered):
            return False

        return self._has_external_subject_hint(lowered)

    def _web_search_route_score(self, message: str) -> tuple[int, str]:
        clean_message = message.strip()
        if not clean_message:
            return 0, "空消息"

        lowered = clean_message.lower()
        if not self._looks_like_search_request(message):
            return 0, "未检测到联网搜索意图"

        explicit_search_keywords = (
            "搜索",
            "查一下",
            "联网",
            "联网搜索",
            "网络搜索",
            "网上搜索",
            "search",
        )
        freshness_keywords = (
            "最新",
            "新闻",
            "最近",
            "今日",
            "今天",
            "实时",
            "latest",
            "news",
            "recent",
            "today",
            "current",
        )
        source_keywords = (
            "官网",
            "website",
            "official",
            "github",
            "论文",
            "paper",
            "教程",
            "资料",
            "价格",
            "price",
        )

        score = 0
        reasons: list[str] = []
        if any(keyword in lowered for keyword in explicit_search_keywords):
            score += 45
            reasons.append("明确搜索/联网词")
        if any(keyword in lowered for keyword in freshness_keywords):
            score += 50
            reasons.append("时效性词")
        if any(keyword in lowered for keyword in source_keywords):
            score += 25
            reasons.append("外部来源/资料词")
        if self._has_external_subject_hint(lowered):
            score += 15
            reasons.append("外部主体")

        if not reasons:
            return 0, "未检测到足够强的联网搜索信号"

        score = min(score, 100)
        return score, f"{WEB_SEARCH_ROUTE_REASON}，{','.join(reasons)}"

    def _has_external_subject_hint(self, lowered_message: str) -> bool:
        external_subject_keywords = (
            "公司",
            "产品",
            "品牌",
            "平台",
            "官网",
            "网站",
            "app",
            "软件",
            "版本",
            "发布",
            "更新",
            "技术",
            "框架",
            "库",
            "api",
            "模型",
            "价格",
            "股价",
            "github",
            "项目",
            "论文",
            "教程",
            "文档",
            "资料",
            "新闻",
            "天气",
            "汇率",
            "股票",
            "基金",
            "国家",
            "城市",
            "地区",
            "总统",
            "政策",
            "赛事",
            "榜单",
            "招聘",
            "fastapi",
            "python",
            "javascript",
            "typescript",
            "react",
            "vue",
            "openai",
            "dashscope",
            "tavily",
        )
        if any(keyword in lowered_message for keyword in external_subject_keywords):
            return True

        return bool(re.search(r"[a-z0-9][a-z0-9_.-]{1,}", lowered_message))

    def _matched_keywords(self, lowered_message: str, keywords: tuple[str, ...]) -> list[str]:
        return [keyword for keyword in keywords if keyword.lower() in lowered_message]

    def _looks_like_query_argument(self, name: str) -> bool:
        query_keywords = ("query", "keyword", "keywords", "search", "q", "text", "name")
        return any(keyword in name for keyword in query_keywords)

    def _looks_like_limit_argument(self, name: str) -> bool:
        limit_keywords = ("limit", "count", "size", "page_size", "max_results", "top_k")
        return any(keyword in name for keyword in limit_keywords)

    def _schema_default_value(self, schema: Any) -> Any:
        if not isinstance(schema, dict):
            return None
        if "default" in schema:
            return schema["default"]
        if "enum" in schema and isinstance(schema["enum"], list) and schema["enum"]:
            return schema["enum"][0]
        return None

    def _safe_planned_tool_log(self, planned_call: PlannedToolCall | None) -> dict[str, Any] | None:
        if planned_call is None:
            return None
        return {
            "name": planned_call.name,
            "arguments": safe_log_data(planned_call.arguments),
            "route_score": planned_call.route_score,
            "route_reason": planned_call.route_reason,
        }

    def _log_planned_tool(self, planned_call: PlannedToolCall) -> None:
        logger.info(
            "PLANNED_TOOL=%s route_score=%s route_reason=%s ARGS=%s",
            planned_call.name,
            planned_call.route_score,
            planned_call.route_reason,
            safe_log_data(planned_call.arguments),
        )
