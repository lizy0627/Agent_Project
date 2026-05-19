import re
from dataclasses import dataclass
from typing import Any

from app.core.logger import get_logger
from app.mcp.manager import MCPManager
from app.mcp.schema import MCPServerConfig


logger = get_logger(__name__)

MODELSCOPE_PRIORITY_WORDS = ("魔搭", "modelscope", "模型", "数据集", "论文", "创空间")
QUERY_NOISE_WORDS = (
    "帮我",
    "请",
    "麻烦",
    "在魔搭上",
    "在魔搭",
    "在 modelscope 上",
    "在modelscope上",
    "ModelScope",
    "modelscope",
    "魔搭",
    "搜索",
    "查找",
    "找一下",
    "找",
    "相关",
    "模型",
    "数据集",
    "论文",
    "创空间",
    "服务",
    "工具",
)
QUERY_ARGUMENT_HINTS = ("query", "keyword", "search", "q", "name", "text")
LIMIT_ARGUMENT_HINTS = ("limit", "count", "size", "max_results", "top_k", "num")
FETCH_REQUEST_KEYWORDS = (
    "fetch",
    "抓取",
    "读取网页",
    "网页",
    "网站",
    "url",
    "http://",
    "https://",
)
FETCH_MAX_LENGTH = 2000
TAVILY_SERVER_NAME = "tavily"
TAVILY_REQUEST_KEYWORDS = (
    "搜索",
    "联网",
    "新闻",
    "查一下",
    "今日",
    "AI新闻",
    "热点",
    "实时",
    "Tavily",
)
TAVILY_TOOL_CANDIDATES = ("search", "tavily_search", "web_search")
TAVILY_QUERY_NOISE_WORDS = (
    "请使用",
    "使用",
    "请用",
    "用",
    "Tavily",
    "tavily",
    "搜索",
    "联网",
    "查一下",
    "查询",
    "查找",
    "检索",
    "帮我",
    "麻烦",
)


@dataclass(frozen=True)
class MCPRoute:
    server_name: str
    tool_name: str
    arguments: dict[str, Any]
    reason: str
    original_query: str
    rewritten_query: str
    query_fallbacks: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "server_name": self.server_name,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "reason": self.reason,
            "original_query": self.original_query,
            "rewritten_query": self.rewritten_query,
            "query_fallbacks": self.query_fallbacks,
        }


class MCPRouter:
    """Choose a configured MCP server/tool from user text using metadata scores."""

    def __init__(self, manager: MCPManager | None = None) -> None:
        self.manager = manager or MCPManager()

    def route(self, user_input: str) -> dict[str, Any] | None:
        message = str(user_input or "").strip()
        if not message:
            return None

        tavily_route = self._route_tavily_request(message)
        if tavily_route:
            return tavily_route.to_dict()

        fetch_route = self._route_fetch_request(message)
        if fetch_route:
            return fetch_route.to_dict()

        candidates = self._candidate_servers(message)
        if not candidates:
            return None

        rewritten_query = rewrite_query(message)
        fallback_route: MCPRoute | None = None
        for server, server_score in candidates:
            tools = self.manager.list_tools(server.key)
            if not tools:
                if fallback_route is None:
                    fallback_route = self._fallback_route(server, server_score, message, rewritten_query)
                continue

            selected_tool, tool_score = self._select_tool(message, rewritten_query, tools)
            if not selected_tool:
                continue

            tool_name = str(selected_tool.get("name") or "")
            arguments = self._build_arguments(rewritten_query, selected_tool)
            reason = (
                f"命中 server 关键词/描述得分 {server_score}，"
                f"工具 {tool_name} 的名称、描述或入参匹配得分 {tool_score}。"
            )
            route = MCPRoute(
                server_name=server.key,
                tool_name=tool_name,
                arguments=arguments,
                reason=reason,
                original_query=message,
                rewritten_query=rewritten_query,
                query_fallbacks=query_fallbacks(rewritten_query),
            )
            logger.info(
                "MCP route selected: server_name=%s tool_name=%s reason=%s",
                route.server_name,
                route.tool_name,
                route.reason,
            )
            return route.to_dict()

        return fallback_route.to_dict() if fallback_route else None

    def _fallback_route(
        self,
        server: MCPServerConfig,
        server_score: int,
        message: str,
        rewritten_query: str,
    ) -> MCPRoute:
        tool_name = _fallback_tool_name(server.key, message)
        return MCPRoute(
            server_name=server.key,
            tool_name=tool_name,
            arguments={"query": rewritten_query},
            reason=(
                f"命中 server 关键词/描述得分 {server_score}，"
                f"但工具列表暂不可用，使用兜底工具名 {tool_name} 触发 MCP 调用并暴露连接错误。"
            ),
            original_query=message,
            rewritten_query=rewritten_query,
            query_fallbacks=query_fallbacks(rewritten_query),
        )

    def should_use_mcp(self, user_input: str) -> bool:
        return bool(self._candidate_servers(user_input))

    def _route_fetch_request(self, message: str) -> MCPRoute | None:
        if not _looks_like_fetch_request(message):
            return None

        server = self.manager.get_server("fetch")
        if server is None or not server.enabled:
            return None

        url = extract_url(message)
        rewritten_query = url or rewrite_query(message)
        tools = self.manager.list_tools(server.key)
        selected_tool = _find_tool(tools, "fetch")
        tool_name = "fetch"
        if selected_tool:
            arguments = self._build_fetch_arguments(rewritten_query, selected_tool)
            reason = "Fetch request matched fetch server and fetch tool."
        else:
            arguments = {"url": rewritten_query, "max_length": FETCH_MAX_LENGTH}
            reason = "Fetch request matched fetch server; tool discovery unavailable, using fetch fallback."

        route = MCPRoute(
            server_name=server.key,
            tool_name=tool_name,
            arguments=arguments,
            reason=reason,
            original_query=message,
            rewritten_query=rewritten_query,
            query_fallbacks=[rewritten_query] if rewritten_query else [],
        )
        logger.info(
            "MCP fetch route selected: server_name=%s tool_name=%s arguments=%s reason=%s",
            route.server_name,
            route.tool_name,
            route.arguments,
            route.reason,
        )
        return route

    def _route_tavily_request(self, message: str) -> MCPRoute | None:
        if not _looks_like_tavily_request(message):
            return None

        server_name = TAVILY_SERVER_NAME
        server = self.manager.get_server(server_name)
        if server is None or not server.enabled:
            return None

        tools = self.manager.list_tools(server.key)
        selected_tool = _find_first_tool(tools, TAVILY_TOOL_CANDIDATES)
        tool_name = str(selected_tool.get("name") or "") if selected_tool else TAVILY_TOOL_CANDIDATES[0]
        query = extract_tavily_query(message)
        reason = "Tavily request matched realtime search keywords."
        if not selected_tool:
            reason = (
                "Tavily request matched realtime search keywords; "
                "tool discovery unavailable, using search fallback."
            )

        route = MCPRoute(
            server_name=server.key,
            tool_name=tool_name,
            arguments={"query": query},
            reason=reason,
            original_query=message,
            rewritten_query=query,
            query_fallbacks=[query] if query else [],
        )
        logger.info(
            "Tavily route selected: server=%s tool=%s query=%s",
            server_name,
            tool_name,
            query,
        )
        return route

    def _candidate_servers(self, message: str) -> list[tuple[MCPServerConfig, int]]:
        lowered = message.lower()
        candidates: list[tuple[MCPServerConfig, int]] = []
        for server in self.manager.servers.values():
            if not server.enabled:
                continue

            searchable = " ".join(
                [
                    server.key,
                    server.name,
                    server.description,
                    server.category or "",
                    " ".join(server.keywords),
                ]
            ).lower()
            score = 0
            for keyword in server.keywords:
                if keyword and keyword.lower() in lowered:
                    score += 20
            for token in _message_tokens(message):
                if token and token.lower() in searchable:
                    score += 2
            if server.key == "modelscope" and any(word.lower() in lowered for word in MODELSCOPE_PRIORITY_WORDS):
                score += 50
            if server.key == "fetch" and _looks_like_fetch_request(message):
                score += 100
            if score > 0:
                candidates.append((server, score))

        candidates.sort(key=lambda item: item[1], reverse=True)
        return candidates

    def _select_tool(
        self,
        message: str,
        rewritten_query: str,
        tools: list[dict[str, Any]],
    ) -> tuple[dict[str, Any] | None, int]:
        if not tools:
            return None, 0

        scored_tools = [
            (tool, self._tool_score(message, rewritten_query, tool))
            for tool in tools
            if tool.get("name")
        ]
        if not scored_tools:
            return None, 0

        scored_tools.sort(key=lambda item: item[1], reverse=True)
        return scored_tools[0]

    def _tool_score(self, message: str, rewritten_query: str, tool: dict[str, Any]) -> int:
        lowered = message.lower()
        tool_name = str(tool.get("name") or "").lower()
        description = str(tool.get("description") or "").lower()
        input_schema = tool.get("input_schema") or {}
        schema_text = str(input_schema).lower()
        searchable = f"{tool_name} {description} {schema_text}"

        score = 0
        if any(word in lowered for word in ("搜索", "查找", "找", "search")):
            score += _keyword_score(searchable, ("search", "搜索", "find", "query"), 20)
        score += _keyword_score(searchable, _message_tokens(message), 2)
        score += _keyword_score(searchable, _category_keywords(message), 12)
        if any(hint in schema_text for hint in QUERY_ARGUMENT_HINTS):
            score += 4
        if rewritten_query and rewritten_query.lower() in searchable:
            score += 3
        return score

    def _build_arguments(self, query: str, tool: dict[str, Any]) -> dict[str, Any]:
        input_schema = tool.get("input_schema") or {}
        properties = input_schema.get("properties", {}) if isinstance(input_schema, dict) else {}
        if not isinstance(properties, dict) or not properties:
            return {"query": query}

        arguments: dict[str, Any] = {}
        for property_name, property_schema in properties.items():
            lowered_name = str(property_name).lower()
            if any(hint in lowered_name for hint in QUERY_ARGUMENT_HINTS):
                arguments[property_name] = query
            elif any(hint in lowered_name for hint in LIMIT_ARGUMENT_HINTS):
                arguments[property_name] = _schema_default(property_schema, 5)
            else:
                default = _schema_default(property_schema, None)
                if default is not None:
                    arguments[property_name] = default

        required = input_schema.get("required", []) if isinstance(input_schema, dict) else []
        if isinstance(required, list):
            for property_name in required:
                arguments.setdefault(property_name, query)

        return arguments or {"query": query}

    def _build_fetch_arguments(self, url: str, tool: dict[str, Any]) -> dict[str, Any]:
        input_schema = tool.get("input_schema") or tool.get("inputSchema") or {}
        properties = input_schema.get("properties", {}) if isinstance(input_schema, dict) else {}
        arguments = {"url": url, "max_length": FETCH_MAX_LENGTH}

        if not isinstance(properties, dict) or not properties:
            return arguments

        for property_name, property_schema in properties.items():
            lowered_name = str(property_name).lower()
            if lowered_name == "url" or "url" in lowered_name:
                arguments[property_name] = url
            elif lowered_name == "max_length" or lowered_name == "maxlength":
                arguments[property_name] = FETCH_MAX_LENGTH
            elif any(hint in lowered_name for hint in LIMIT_ARGUMENT_HINTS):
                arguments[property_name] = _schema_default(property_schema, FETCH_MAX_LENGTH)

        return arguments


def rewrite_query(user_input: str) -> str:
    """Extract the search phrase and normalize common ModelScope aliases."""

    query = " ".join(str(user_input or "").strip().split())
    if not query:
        return ""

    query = re.sub(r"\bqwen\s*-\s*(\d+)\b", lambda match: f"Qwen{match.group(1)}", query, flags=re.I)
    query = re.sub(r"通义千问", "Qwen", query, flags=re.I)

    for word in QUERY_NOISE_WORDS:
        query = re.sub(re.escape(word), " ", query, flags=re.I)

    query = re.sub(r"[，,。！？?!；;：:]+", " ", query)
    query = " ".join(query.split())
    return query.strip() or str(user_input or "").strip()


def extract_url(text: str) -> str:
    match = re.search(r"https?://[^\s<>\]）)，。！？；;\"']+", str(text or ""), flags=re.I)
    if not match:
        return ""
    return match.group(0).rstrip(".,!?;:，。！？；：)")


def extract_tavily_query(text: str) -> str:
    query = " ".join(str(text or "").strip().split())
    if not query:
        return ""

    for word in TAVILY_QUERY_NOISE_WORDS:
        query = re.sub(re.escape(word), " ", query, flags=re.I)

    query = re.sub(r"[，。！？?！:：；;]+", " ", query)
    query = " ".join(query.split())
    return query.strip() or str(text or "").strip()


def query_fallbacks(query: str) -> list[str]:
    normalized = rewrite_query(query)
    candidates = [normalized] if normalized else []
    lowered = normalized.lower()
    if lowered == "qwen3":
        candidates.append("Qwen")
    if lowered == "qwen-3":
        candidates.extend(["Qwen3", "Qwen"])
    return _dedupe(candidates)


def _fallback_tool_name(server_name: str, message: str) -> str:
    if server_name == "fetch":
        return "fetch"
    if server_name != "modelscope":
        return "search"

    lowered = message.lower()
    tool_map = {
        ("数据集", "dataset"): "search_datasets",
        ("论文", "paper"): "search_papers",
        ("创空间", "space", "studio"): "search_spaces",
        ("mcp", "服务"): "search_mcp_servers",
    }
    for triggers, tool_name in tool_map.items():
        if any(trigger in lowered for trigger in triggers):
            return tool_name
    return "search_models"


def _message_tokens(message: str) -> list[str]:
    return [
        token
        for token in re.split(r"[\s，,。！？?!；;：:/\\|()（）\[\]【】]+", message)
        if token
    ]


def _category_keywords(message: str) -> tuple[str, ...]:
    category_map = {
        "模型": ("model", "模型"),
        "数据集": ("dataset", "数据集"),
        "论文": ("paper", "论文"),
        "创空间": ("space", "studio", "创空间"),
        "路线": ("route", "路线", "导航"),
        "地图": ("map", "地图", "位置"),
        "天气": ("weather", "天气"),
        "github": ("github", "repo", "issue", "pull"),
        "文件": ("file", "filesystem", "文件"),
        "数据库": ("database", "sql", "数据库"),
        "浏览器": ("browser", "search", "浏览器"),
    }
    lowered = message.lower()
    keywords: list[str] = []
    for trigger, values in category_map.items():
        if trigger.lower() in lowered:
            keywords.extend(values)
    return tuple(keywords)


def _keyword_score(searchable: str, keywords: tuple[str, ...] | list[str], weight: int) -> int:
    return sum(weight for keyword in keywords if keyword and keyword.lower() in searchable)


def _looks_like_fetch_request(message: str) -> bool:
    lowered = str(message or "").lower()
    return any(keyword.lower() in lowered for keyword in FETCH_REQUEST_KEYWORDS)


def _looks_like_tavily_request(message: str) -> bool:
    lowered = str(message or "").lower()
    return any(keyword.lower() in lowered for keyword in TAVILY_REQUEST_KEYWORDS)


def _find_tool(tools: list[dict[str, Any]], tool_name: str) -> dict[str, Any] | None:
    expected = _normalize_tool_name(tool_name)
    for tool in tools:
        actual = str(tool.get("name") or tool.get("tool_name") or "").strip()
        if _normalize_tool_name(actual) == expected:
            return tool
    return None


def _find_first_tool(tools: list[dict[str, Any]], tool_names: tuple[str, ...]) -> dict[str, Any] | None:
    for tool_name in tool_names:
        tool = _find_tool(tools, tool_name)
        if tool:
            return tool
    return None


def _normalize_tool_name(tool_name: str) -> str:
    return str(tool_name or "").strip().replace("-", "_").casefold()


def _schema_default(schema: Any, fallback: Any) -> Any:
    if isinstance(schema, dict) and "default" in schema:
        return schema["default"]
    return fallback


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = value.strip()
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result
