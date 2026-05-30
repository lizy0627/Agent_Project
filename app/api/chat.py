import json
from queue import Empty, Queue
from threading import Lock, Thread
from time import perf_counter
from uuid import uuid4

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import JSONResponse, StreamingResponse

from app.agents import ManagerAgent
from app.api.auth import CurrentUser, get_current_user
from app.core.config import Settings, get_settings
from app.core.exceptions import (
    AgentError,
    InvalidArgumentsError,
    UnknownAgentError,
    error_payload,
    error_response,
)
from app.core.logger import get_logger
from app.memory import MemoryManager
from app.memory.vector_store import MemoryEmbeddingProvider
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ConversationClearResponse,
    ConversationListResponse,
    ConversationMessagesResponse,
    ErrorDetail,
)
from app.services.conversation_store import ConversationStoreProtocol, create_conversation_store
from app.services.dashscope_agent import AgentTraceStep as AgentTraceStepData
from app.services.dashscope_agent import DashScopeAgent
from app.services.message_builder import MessageBuilder


router = APIRouter()
logger = get_logger(__name__)
agent_lock = Lock()
store_lock = Lock()
cached_agent: DashScopeAgent | None = None
cached_agent_signature: tuple[
    str | None,
    str,
    str,
    float,
    str | None,
    str,
    float,
    float,
    int,
    bool,
    str,
    int,
    int,
] | None = None
cached_manager_agent: ManagerAgent | None = None
cached_manager_agent_source: DashScopeAgent | None = None
cached_conversation_store: ConversationStoreProtocol | None = None
cached_conversation_store_signature: tuple[str, str, str | None, int] | None = None
cached_memory_manager: MemoryManager | None = None
cached_memory_manager_signature: tuple[str, int, int, bool, int, str, str | None, str] | None = None
DEFAULT_SYSTEM_PROMPT = "\u4f60\u662f\u4e00\u4e2a\u7b80\u6d01\u3001\u53ef\u9760\u7684\u4e2d\u6587 AI \u52a9\u624b\u3002"
ALLOWED_CHAT_MODELS = {"qwen-plus", "qwen-turbo", "qwen-max"}
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
        settings.web_search_timeout_seconds,
        settings.web_reader_timeout_seconds,
        settings.search_workflow_read_top_k,
        settings.mcp_enabled,
        settings.modelscope_mcp_url,
        settings.mcp_timeout_seconds,
        settings.max_agent_steps,
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


def get_manager_agent(agent: DashScopeAgent) -> ManagerAgent:
    """Return a ManagerAgent bound to the current model client and tool manager."""

    global cached_manager_agent, cached_manager_agent_source

    with agent_lock:
        if cached_manager_agent is None or cached_manager_agent_source is not agent:
            cached_manager_agent = ManagerAgent(
                llm_client=agent.llm_client,
                tool_manager=agent.tool_manager,
            )
            cached_manager_agent_source = agent
            logger.info("ManagerAgent initialized for multi-agent mode")

        return cached_manager_agent


def get_conversation_store(settings: Settings = Depends(get_settings)) -> ConversationStoreProtocol:
    """Return the configured conversation store singleton."""

    global cached_conversation_store, cached_conversation_store_signature

    signature = (
        settings.conversation_store,
        str(settings.conversation_db_path),
        settings.conversation_database_url,
        settings.conversation_max_rounds,
    )
    with store_lock:
        if cached_conversation_store is None or cached_conversation_store_signature != signature:
            cached_conversation_store = create_conversation_store(
                store_type=settings.conversation_store,
                db_path=settings.conversation_db_path,
                max_rounds=settings.conversation_max_rounds,
                database_url=settings.conversation_database_url,
            )
            cached_conversation_store_signature = signature
            logger.info(
                "Conversation store initialized: type=%s db_path=%s max_rounds=%s",
                settings.conversation_store,
                settings.conversation_db_path,
                settings.conversation_max_rounds,
            )

        return cached_conversation_store


def get_memory_manager(settings: Settings = Depends(get_settings)) -> MemoryManager:
    """Return the JSON-backed memory manager singleton."""

    global cached_memory_manager, cached_memory_manager_signature

    signature = (
        str(settings.memory_json_path),
        settings.memory_search_limit,
        settings.memory_recent_context_limit,
        settings.memory_vector_enabled,
        settings.memory_vector_top_k,
        settings.memory_embedding_model,
        settings.dashscope_api_key,
        settings.dashscope_base_url,
    )
    with store_lock:
        if cached_memory_manager is None or cached_memory_manager_signature != signature:
            embedding_provider = (
                MemoryEmbeddingProvider.from_settings(settings) if settings.memory_vector_enabled else None
            )
            cached_memory_manager = MemoryManager(
                json_path=settings.memory_json_path,
                short_limit=max(settings.memory_recent_context_limit * 2, 2),
                vector_enabled=settings.memory_vector_enabled,
                vector_top_k=settings.memory_vector_top_k,
                embedding_provider=embedding_provider,
            )
            cached_memory_manager_signature = signature
            logger.info(
                "MemoryManager initialized: json_path=%s vector_enabled=%s vector_top_k=%s",
                settings.memory_json_path,
                settings.memory_vector_enabled,
                settings.memory_vector_top_k,
            )

        return cached_memory_manager


@router.get("/")
def health_check() -> dict[str, str]:
    """Return a simple service health response."""

    return {"status": "ok", "message": "DashScope Agent is running"}


@router.get("/conversations", response_model=ConversationListResponse)
def list_conversations(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: CurrentUser = Depends(get_current_user),
    store: ConversationStoreProtocol = Depends(get_conversation_store),
) -> ConversationListResponse:
    """Return paginated conversations owned by the current user."""

    page = store.list_conversations(user_id=current_user.user_id, limit=limit, offset=offset)
    return ConversationListResponse(
        conversations=[conversation.__dict__ for conversation in page.conversations],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
        has_more=page.has_more,
    )


@router.get("/conversations/{conversation_id}/messages", response_model=ConversationMessagesResponse)
def get_conversation_messages(
    conversation_id: str = Path(..., min_length=1, max_length=100),
    limit: int = Query(default=60, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: CurrentUser = Depends(get_current_user),
    store: ConversationStoreProtocol = Depends(get_conversation_store),
) -> ConversationMessagesResponse:
    """Return stored history for one conversation."""

    clean_conversation_id = conversation_id.strip()
    if not clean_conversation_id:
        raise InvalidArgumentsError()

    page = store.get_message_page(
        clean_conversation_id,
        user_id=current_user.user_id,
        limit=limit,
        offset=offset,
    )
    return ConversationMessagesResponse(
        conversation_id=clean_conversation_id,
        messages=page.messages,
        total=page.total,
        limit=page.limit,
        offset=page.offset,
        has_more=page.has_more,
    )


@router.delete("/conversations/{conversation_id}", response_model=ConversationClearResponse)
def clear_conversation(
    conversation_id: str = Path(..., min_length=1, max_length=100),
    current_user: CurrentUser = Depends(get_current_user),
    store: ConversationStoreProtocol = Depends(get_conversation_store),
) -> ConversationClearResponse:
    """Clear stored history for one conversation."""

    clean_conversation_id = conversation_id.strip()
    if not clean_conversation_id:
        raise InvalidArgumentsError()

    store.clear(clean_conversation_id, user_id=current_user.user_id)
    return ConversationClearResponse(
        conversation_id=clean_conversation_id,
        message="\u4f1a\u8bdd\u5df2\u6e05\u7a7a",
    )


@router.delete("/conversations", include_in_schema=False)
@router.delete("/conversations/", include_in_schema=False)
def clear_conversation_missing_id(current_user: CurrentUser = Depends(get_current_user)) -> JSONResponse:
    """Return a stable error when conversation id is missing."""

    return error_response(InvalidArgumentsError())


@router.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    current_user: CurrentUser = Depends(get_current_user),
    agent: DashScopeAgent = Depends(get_agent),
    store: ConversationStoreProtocol = Depends(get_conversation_store),
    memory: MemoryManager = Depends(get_memory_manager),
    settings: Settings = Depends(get_settings),
) -> ChatResponse | JSONResponse:
    """Send a user message to the agent and return its reply."""

    conversation_id = request.conversation_id or str(uuid4())
    model_messages = build_model_messages(request, conversation_id, store, current_user.user_id)
    model_messages = with_memory_context(
        model_messages,
        memory.build_memory_messages(
            user_id=current_user.user_id,
            conversation_id=conversation_id,
            query=request.message,
            search_limit=settings.memory_search_limit,
            recent_limit=settings.memory_recent_context_limit,
        ),
    )
    requested_model = normalize_requested_model(request.model)

    try:
        reply = (
            get_manager_agent(agent).chat(messages=model_messages, model=requested_model)
            if request.multi_agent
            else agent.chat(
                messages=model_messages,
                model=requested_model,
                agent_mode=request.agent_mode,
            )
        )
        store.append_exchange(conversation_id, request.message, reply.content, user_id=current_user.user_id)
        memory.add_memory(
            user_id=current_user.user_id,
            conversation_id=conversation_id,
            question=request.message,
            answer=reply.content,
        )
        return ChatResponse(
            reply=reply.content,
            model=requested_model or agent.model,
            conversation_id=conversation_id,
            multi_agent=request.multi_agent,
            agent_results=multi_agent_results_payload(reply.trace) if request.multi_agent else [],
            used_tool=reply.used_tool,
            tool_name=reply.tool_result.name if reply.tool_result else None,
            tool_status=get_tool_status(reply.tool_result),
            tool_result=reply.tool_result.result if reply.tool_result else None,
            tool_error=reply.tool_result.error if reply.tool_result else None,
            tool_duration_ms=reply.tool_result.duration_ms if reply.tool_result else None,
            tool_error_code=reply.tool_result.error_code if reply.tool_result else None,
            tool_error_message=reply.tool_result.error_message if reply.tool_result else None,
            tool_retryable=reply.tool_result.retryable if reply.tool_result else None,
            tool_error_detail=tool_error_detail(reply.tool_result),
            trace=trace_payload(reply.trace),
        )
    except AgentError as exc:
        logger.info("Chat request failed: code=%s status=%s", exc.code, exc.status_code)
        return error_response(exc)
    except Exception:
        logger.exception("Unhandled chat request error")
        return error_response(UnknownAgentError())


@router.post("/chat/stream")
def stream_chat(
    request: ChatRequest,
    current_user: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    store: ConversationStoreProtocol = Depends(get_conversation_store),
    memory: MemoryManager = Depends(get_memory_manager),
) -> StreamingResponse:
    """Stream a chat response using server-sent events."""

    conversation_id = request.conversation_id or str(uuid4())
    model_messages = build_model_messages(request, conversation_id, store, current_user.user_id)
    model_messages = with_memory_context(
        model_messages,
        memory.build_memory_messages(
            user_id=current_user.user_id,
            conversation_id=conversation_id,
            query=request.message,
            search_limit=settings.memory_search_limit,
            recent_limit=settings.memory_recent_context_limit,
        ),
    )
    requested_model = normalize_requested_model(request.model)
    likely_web_search = _looks_like_search_request(request.message)

    def event_stream():
        assistant_chunks: list[str] = []
        status_queue: Queue[str] = Queue()
        result_queue: Queue[tuple[str, object]] = Queue(maxsize=1)
        sent_statuses: set[str] = set()

        def queue_status(message: str) -> None:
            clean_message = str(message or "").strip()
            if clean_message:
                status_queue.put(clean_message)

        def status_event(message: str) -> str | None:
            clean_message = str(message or "").strip()
            if not clean_message or clean_message in sent_statuses:
                return None
            sent_statuses.add(clean_message)
            return sse_event(
                "status",
                {
                    "message": clean_message,
                    "trace": [status_trace_step(clean_message)],
                },
            )

        def drain_status_events():
            while True:
                try:
                    message = status_queue.get_nowait()
                except Empty:
                    break

                event = status_event(message)
                if event is not None:
                    yield event

        try:
            if request.multi_agent:
                prepared_agent = get_agent(settings)
                reply = get_manager_agent(prepared_agent).chat(messages=model_messages, model=requested_model)
                metadata = {
                    "success": True,
                    "conversation_id": conversation_id,
                    "model": requested_model or prepared_agent.model,
                    "multi_agent": True,
                    "agent_results": multi_agent_results_payload(reply.trace),
                    **tool_response_metadata(None),
                    "trace": trace_payload(reply.trace),
                }
                yield sse_event("metadata", metadata)
                assistant_reply = reply.content
                if assistant_reply:
                    yield sse_event("chunk", {"content": assistant_reply})
                store.append_exchange(conversation_id, request.message, assistant_reply, user_id=current_user.user_id)
                memory.add_memory(
                    user_id=current_user.user_id,
                    conversation_id=conversation_id,
                    question=request.message,
                    answer=assistant_reply,
                )
                yield sse_event("done", metadata)
                return

            if likely_web_search:
                event = status_event(WEB_SEARCH_STATUS_SEARCHING)
                if event is not None:
                    yield event

            def prepare_stream() -> None:
                try:
                    prepared_agent = get_agent(settings)
                    stream, tool_result, trace = prepared_agent.stream_chat_with_tool_result(
                        messages=model_messages,
                        model=requested_model,
                        status_callback=queue_status,
                        agent_mode=request.agent_mode,
                    )
                    result_queue.put(("ok", (prepared_agent, stream, tool_result, trace)))
                except Exception as exc:
                    result_queue.put(("error", exc))

            prepare_thread = Thread(target=prepare_stream, daemon=True)
            prepare_thread.start()
            while prepare_thread.is_alive():
                try:
                    message = status_queue.get(timeout=0.1)
                except Empty:
                    continue

                event = status_event(message)
                if event is not None:
                    yield event

            yield from drain_status_events()
            result_status, result_payload = result_queue.get()
            if result_status == "error":
                if isinstance(result_payload, Exception):
                    raise result_payload
                raise UnknownAgentError()

            agent, stream, tool_result, trace = result_payload

            yield sse_event(
                "metadata",
                {
                    "success": True,
                    "conversation_id": conversation_id,
                    "model": requested_model or agent.model,
                    **tool_response_metadata(tool_result),
                    "trace": trace_payload(trace),
                },
            )

            model_started_at = perf_counter()
            try:
                for chunk in stream:
                    assistant_chunks.append(chunk)
                    yield sse_event("chunk", {"content": chunk})
            except Exception as exc:
                trace.append(
                    AgentTraceStepData(
                        step="final_answer",
                        status="failed",
                        message=str(exc),
                        duration_ms=elapsed_ms(model_started_at),
                    )
                )
                raise
            if request.agent_mode != "react":
                trace.append(
                    AgentTraceStepData(
                        step="final_answer",
                        status="success",
                        duration_ms=elapsed_ms(model_started_at),
                    )
                )

            assistant_reply = "".join(assistant_chunks)
            store.append_exchange(conversation_id, request.message, assistant_reply, user_id=current_user.user_id)
            memory.add_memory(
                user_id=current_user.user_id,
                conversation_id=conversation_id,
                question=request.message,
                answer=assistant_reply,
            )
            yield sse_event(
                "done",
                {
                    "success": True,
                    "conversation_id": conversation_id,
                    "model": requested_model or agent.model,
                    **tool_response_metadata(tool_result),
                    "trace": trace_payload(trace),
                },
            )
        except AgentError as exc:
            logger.info("Streaming chat failed: code=%s status=%s", exc.code, exc.status_code)
            yield sse_event("error", error_payload(exc))
        except GeneratorExit:
            logger.info("Streaming chat client disconnected: conversation_id=%s", conversation_id)
            raise
        except Exception:
            logger.exception("Unhandled streaming chat error")
            error = UnknownAgentError()
            yield sse_event("error", error_payload(error))

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
    store: ConversationStoreProtocol,
    user_id: str,
) -> list[dict[str, str]]:
    """Build system prompt, stored history, and the current user message."""

    history = store.get_messages(conversation_id, user_id=user_id)
    return MessageBuilder().build_chat_messages(
        system_prompt=request.system_prompt or DEFAULT_SYSTEM_PROMPT,
        history=history,
        user_message=request.message,
        max_context_rounds=request.max_context_rounds,
    )


def with_memory_context(
    messages: list[dict[str, str]],
    memory_messages: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Insert memory context after the system prompt without moving the latest user message."""

    if not memory_messages:
        return messages
    if messages and messages[0].get("role") == "system":
        return [messages[0], *memory_messages, *messages[1:]]
    return [*memory_messages, *messages]


def normalize_requested_model(model: str | None) -> str | None:
    """Return a clean model name, or None to use the configured default model."""

    if model is None:
        return None

    clean_model = model.strip()
    if not clean_model:
        return None
    if clean_model not in ALLOWED_CHAT_MODELS:
        raise InvalidArgumentsError()
    return clean_model


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
            "tool_error_code": None,
            "tool_error_message": None,
            "tool_retryable": None,
            "tool_error_detail": None,
        }

    return {
        "used_tool": True,
        "tool_name": tool_result.name,
        "tool_status": get_tool_status(tool_result),
        "tool_result": tool_result.result,
        "tool_error": tool_result.error,
        "tool_duration_ms": tool_result.duration_ms,
        "tool_error_code": tool_result.error_code,
        "tool_error_message": tool_result.error_message,
        "tool_retryable": tool_result.retryable,
        "tool_error_detail": tool_error_detail(tool_result),
    }


def trace_payload(trace: list[AgentTraceStepData] | None) -> list[dict]:
    """Serialize agent trace steps while preserving the stable front-end shape."""

    if not trace:
        return []
    return [step.to_dict() if hasattr(step, "to_dict") else dict(step) for step in trace]


def multi_agent_results_payload(trace: list[AgentTraceStepData] | None) -> list[dict]:
    """Extract structured sub-agent outputs from the execution trace."""

    results: list[dict] = []
    if not trace:
        return results

    for step in trace:
        step_name = getattr(step, "step", None)
        observation = getattr(step, "observation", None)
        if step_name == "multi_agent_sub_agent" and isinstance(observation, dict):
            results.append(observation)
    return results


def status_trace_step(message: str) -> dict:
    """Represent an in-flight SSE status as a trace-compatible running step."""

    return {
        "step": "status",
        "status": "running",
        "message": message,
    }


def elapsed_ms(started_at: float) -> float:
    return round((perf_counter() - started_at) * 1000, 2)


def tool_error_detail(tool_result) -> dict | None:
    if tool_result is None or tool_result.success:
        return None

    code = tool_result.error_code or "TOOL_EXECUTION_ERROR"
    message = tool_result.error_message or tool_result.error or "工具调用失败，请调整问题后重试。"
    return ErrorDetail(code=code, message=message).model_dump()


def sse_event(event: str, data: dict) -> str:
    """Encode one server-sent event."""

    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"
