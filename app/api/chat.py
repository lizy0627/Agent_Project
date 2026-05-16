import json
from threading import Lock
from uuid import uuid4

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.config import Settings, get_settings
from app.core.errors import AgentError, UnknownAgentError
from app.core.logger import get_logger
from app.schemas.chat import ChatRequest, ChatResponse, ErrorResponse
from app.services.conversation_store import ConversationStore
from app.services.dashscope_agent import DashScopeAgent


router = APIRouter()
logger = get_logger(__name__)
conversation_store = ConversationStore(max_rounds=30)
agent_lock = Lock()
cached_agent: DashScopeAgent | None = None
cached_agent_signature: tuple[str | None, str, str, float, str | None, str, bool, str, int] | None = None
DEFAULT_SYSTEM_PROMPT = "\u4f60\u662f\u4e00\u4e2a\u7b80\u6d01\u3001\u53ef\u9760\u7684\u4e2d\u6587 AI \u52a9\u624b\u3002"
WEB_SEARCH_STATUS_SEARCHING = "正在联网搜索..."
WEB_SEARCH_STATUS_ORGANIZING = "正在搜索并整理资料..."
SEARCH_INTENT_KEYWORDS = (
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
    "search",
    "latest",
    "news",
    "current",
    "recent",
    "website",
    "official",
    "price",
)
PLAIN_TIME_KEYWORDS = (
    "几点",
    "时间",
    "日期",
    "今天几号",
    "现在几点",
    "current time",
    "what time",
    "today's date",
    "today date",
)


def get_agent(settings: Settings = Depends(get_settings)) -> DashScopeAgent:
    """Return a cached agent so requests can reuse the model client."""

    global cached_agent, cached_agent_signature

    signature = (
        settings.dashscope_api_key,
        settings.dashscope_base_url,
        settings.dashscope_model,
        settings.dashscope_timeout_seconds,
        settings.tavily_api_key,
        settings.web_search_provider,
        settings.mcp_enabled,
        settings.modelscope_mcp_url,
        settings.mcp_timeout_seconds,
    )
    with agent_lock:
        if cached_agent is None or cached_agent_signature != signature:
            cached_agent = DashScopeAgent(settings)
            cached_agent_signature = signature
            logger.info(
                "DashScopeAgent initialized: model=%s timeout_seconds=%s",
                settings.dashscope_model,
                settings.dashscope_timeout_seconds,
            )

        return cached_agent


def get_conversation_store() -> ConversationStore:
    """Return the in-memory conversation store singleton."""

    return conversation_store


@router.get("/")
def health_check() -> dict[str, str]:
    """Return a simple service health response."""

    return {"status": "ok", "message": "DashScope Agent is running"}


@router.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    agent: DashScopeAgent = Depends(get_agent),
    store: ConversationStore = Depends(get_conversation_store),
) -> ChatResponse | JSONResponse:
    """Send a user message to the agent and return its reply."""

    conversation_id = request.conversation_id or str(uuid4())
    model_messages = build_model_messages(request, conversation_id, store)
    requested_model = normalize_requested_model(request.model)

    try:
        reply = agent.chat(messages=model_messages, model=requested_model)
        store.append_exchange(conversation_id, request.message, reply.content)
        return ChatResponse(
            reply=reply.content,
            model=requested_model or agent.model,
            conversation_id=conversation_id,
            used_tool=reply.used_tool,
            tool_name=reply.tool_result.name if reply.tool_result else None,
            tool_status=get_tool_status(reply.tool_result),
            tool_result=reply.tool_result.result if reply.tool_result else None,
            tool_error=reply.tool_result.error if reply.tool_result else None,
            tool_duration_ms=reply.tool_result.duration_ms if reply.tool_result else None,
        )
    except AgentError as exc:
        logger.info("Chat request failed: code=%s status=%s", exc.code, exc.status_code)
        return error_response(exc)
    except Exception as exc:
        logger.exception("Unhandled chat request error")
        return error_response(UnknownAgentError())


@router.post("/chat/stream")
def stream_chat(
    request: ChatRequest,
    settings: Settings = Depends(get_settings),
    store: ConversationStore = Depends(get_conversation_store),
) -> StreamingResponse:
    """Stream a chat response using server-sent events."""

    conversation_id = request.conversation_id or str(uuid4())
    model_messages = build_model_messages(request, conversation_id, store)
    requested_model = normalize_requested_model(request.model)
    likely_web_search = _looks_like_search_request(request.message)

    def event_stream():
        assistant_chunks: list[str] = []

        try:
            if likely_web_search:
                yield sse_event("status", {"message": WEB_SEARCH_STATUS_SEARCHING})

            agent = get_agent(settings)
            stream, tool_result = agent.stream_chat_with_tool_result(
                messages=model_messages,
                model=requested_model,
            )
            if tool_result and tool_result.name == "web_search":
                yield sse_event("status", {"message": WEB_SEARCH_STATUS_ORGANIZING})

            yield sse_event(
                "metadata",
                {
                    "success": True,
                    "conversation_id": conversation_id,
                    "model": requested_model or agent.model,
                    **tool_response_metadata(tool_result),
                },
            )

            for chunk in stream:
                assistant_chunks.append(chunk)
                yield sse_event("chunk", {"content": chunk})

            assistant_reply = "".join(assistant_chunks)
            store.append_exchange(conversation_id, request.message, assistant_reply)
            yield sse_event(
                "done",
                {
                    "success": True,
                    "conversation_id": conversation_id,
                    "model": requested_model or agent.model,
                    **tool_response_metadata(tool_result),
                },
            )
        except AgentError as exc:
            logger.info("Streaming chat failed: code=%s status=%s", exc.code, exc.status_code)
            yield sse_event("error", {"success": False, "error": exc.message})
        except GeneratorExit:
            logger.info("Streaming chat client disconnected: conversation_id=%s", conversation_id)
            raise
        except Exception:
            logger.exception("Unhandled streaming chat error")
            error = UnknownAgentError()
            yield sse_event("error", {"success": False, "error": error.message})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def build_model_messages(
    request: ChatRequest,
    conversation_id: str,
    store: ConversationStore,
) -> list[dict[str, str]]:
    """Build system prompt, stored history, and the current user message."""

    history = store.get_messages(conversation_id)
    if request.max_context_rounds is not None:
        history = history[-request.max_context_rounds * 2 :] if request.max_context_rounds > 0 else []

    return [
        {
            "role": "system",
            "content": request.system_prompt or DEFAULT_SYSTEM_PROMPT,
        },
        *history,
        {
            "role": "user",
            "content": request.message,
        },
    ]


def normalize_requested_model(model: str | None) -> str | None:
    """Return a clean model name, or None to use the configured default model."""

    if model is None:
        return None

    clean_model = model.strip()
    return clean_model or None


def _looks_like_search_request(message: str) -> bool:
    """Return True when a message likely needs web search status immediately."""

    clean_message = message.strip()
    if not clean_message:
        return False

    lowered = clean_message.lower()
    if _looks_like_plain_time_request(lowered):
        return False

    return any(keyword in lowered for keyword in SEARCH_INTENT_KEYWORDS)


def _looks_like_plain_time_request(lowered_message: str) -> bool:
    """Avoid showing web-search status for simple time/date tool requests."""

    if not any(keyword in lowered_message for keyword in PLAIN_TIME_KEYWORDS):
        return False

    non_time_search_keywords = tuple(
        keyword for keyword in SEARCH_INTENT_KEYWORDS if keyword not in {"current", "recent"}
    )
    return not any(keyword in lowered_message for keyword in non_time_search_keywords)


def get_tool_status(tool_result) -> str | None:
    if tool_result is None:
        return None

    return "success" if tool_result.success else "failed"


def tool_response_metadata(tool_result) -> dict:
    if tool_result is None:
        return {
            "used_tool": False,
            "tool_name": None,
            "tool_status": None,
            "tool_result": None,
            "tool_error": None,
            "tool_duration_ms": None,
        }

    return {
        "used_tool": True,
        "tool_name": tool_result.name,
        "tool_status": get_tool_status(tool_result),
        "tool_result": tool_result.result,
        "tool_error": tool_result.error,
        "tool_duration_ms": tool_result.duration_ms,
    }


def sse_event(event: str, data: dict) -> str:
    """Encode one server-sent event."""

    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def error_response(error: AgentError) -> JSONResponse:
    """Return all chat errors in a stable JSON shape."""

    body = ErrorResponse(error=error.message)
    return JSONResponse(
        status_code=error.status_code,
        content=body.model_dump(),
    )
