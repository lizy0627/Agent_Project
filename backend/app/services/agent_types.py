from dataclasses import dataclass
from typing import Any, Callable

from backend.app.tools.base import ToolResult


ChatMessage = dict[str, str]
StatusCallback = Callable[[str], None]
DEFAULT_SEARCH_WORKFLOW_READ_TOP_K = 2
MAX_SEARCH_WORKFLOW_READ_TOP_K = 5
WEB_SEARCH_TOOL_ARGUMENTS = {"query", "max_results", "search_depth"}
STATUS_WEB_SEARCHING = "正在联网搜索..."
STATUS_WEB_READING = "正在读取网页内容..."
STATUS_MCP_CONNECTING = "正在连接 MCP 服务..."
STATUS_MCP_CALLING = "正在调用 MCP 工具..."
STATUS_CALCULATING = "正在计算..."
STATUS_SUMMARIZING = "正在总结文本..."
STATUS_GETTING_TIME = "正在获取当前时间..."
STATUS_GENERATING = "正在生成回答..."
MAX_SEARCH_SUMMARY_RESULTS = 3
MAX_PAGE_SUMMARY_RESULTS = 2
MAX_PAGE_CONTENT_CHARS = 2500
MIN_PAGE_CONTENT_CHARS = 800
MAX_SEARCH_CONTEXT_CHARS = 8000
MAX_SEARCH_SNIPPET_CHARS = 500
NOISY_PAGE_KEYWORDS = (
    "广告",
    "推广",
    "赞助",
    "相关阅读",
    "相关推荐",
    "点击加载更多",
    "发表评论",
    "评论区",
    "advertisement",
    "advertising",
    "sponsored",
    "related articles",
    "recommended",
    "subscribe",
    "newsletter",
    "cookie policy",
)


@dataclass(frozen=True)
class AgentTraceStep:
    """Stable, JSON-friendly trace event for one agent execution step."""

    step: str
    status: str
    message: str | None = None
    duration_ms: float | None = None
    tool_name: str | None = None
    observation: Any | None = None
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a compact dict without empty fields for SSE and API responses."""

        payload: dict[str, Any] = {
            "step": self.step,
            "status": self.status,
        }
        if self.message is not None:
            payload["message"] = self.message
        if self.tool_name is not None:
            payload["tool_name"] = self.tool_name
        if self.observation is not None:
            payload["observation"] = self.observation
        if self.duration_ms is not None:
            payload["duration_ms"] = self.duration_ms
        if self.metadata is not None:
            payload["metadata"] = self.metadata
        return payload


@dataclass(frozen=True)
class AgentReply:
    """Final agent reply plus optional tool execution metadata."""

    content: str
    tool_result: ToolResult | None = None
    trace: list[AgentTraceStep] | None = None

    @property
    def used_tool(self) -> bool:
        return self.tool_result is not None


@dataclass(frozen=True)
class SearchWorkflowPerformance:
    """Timing and page-count metrics for one search workflow run."""

    started_at: float
    search_seconds: float = 0.0
    reader_seconds: float = 0.0
    success_pages: int = 0
    failed_pages: int = 0
    cache_hit_count: int = 0
