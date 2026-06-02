import json
import logging
from types import SimpleNamespace
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import chat as chat_api
from app.api.auth import CurrentUser
from app.core.exceptions import ModelProviderError
from app.agent.executor import tool_result_to_observation
from app.services.agent_types import AgentReply, AgentTraceStep
from app.services.conversation_store import create_conversation_store
from app.tools.base import ToolResult


class FakeAgent:
    model = "qwen-plus"

    def chat(self, messages, model=None, agent_mode=None):
        return AgentReply(content="hello from fake agent", trace=[])

    def stream_chat_with_tool_result(self, messages, model=None, status_callback=None, agent_mode=None, trace_callback=None):
        return iter(["hello", " stream"]), None, []


class TraceAgent(FakeAgent):
    def chat(self, messages, model=None, agent_mode=None):
        return AgentReply(
            content="trace response",
            trace=[
                AgentTraceStep(step="planner", status="running", message="Planning request."),
                AgentTraceStep(step="planner", status="success", message="Planned direct answer.", duration_ms=1.2),
                AgentTraceStep(
                    step="tool_call",
                    status="failed",
                    message="Search service is unavailable.",
                    tool_name="web_search",
                    duration_ms=45.6,
                    error_code="NETWORK_ERROR",
                    retryable=True,
                ),
                AgentTraceStep(step="final_answer", status="success", duration_ms=12.3),
            ],
        )

    def stream_chat_with_tool_result(self, messages, model=None, status_callback=None, agent_mode=None, trace_callback=None):
        return (
            iter(["trace", " stream"]),
            None,
            [
                AgentTraceStep(step="planner", status="running", message="Planning request."),
                AgentTraceStep(step="planner", status="success", message="Planned direct answer.", duration_ms=1.2),
            ],
        )


def failed_tool_result() -> ToolResult:
    return ToolResult(
        name="web_search",
        success=False,
        result={"query": "hello", "error": "raw provider failure"},
        error="raw provider failure",
        duration_ms=45.6,
        error_code="NETWORK_ERROR",
        error_message="Search service is unavailable.",
        retryable=True,
    )


class ToolFailureAgent(FakeAgent):
    def chat(self, messages, model=None, agent_mode=None):
        return AgentReply(
            content="Search service is unavailable.",
            tool_result=failed_tool_result(),
            trace=[],
        )

    def stream_chat_with_tool_result(self, messages, model=None, status_callback=None, agent_mode=None, trace_callback=None):
        return iter(["Search service is unavailable."]), failed_tool_result(), []


class FailingStreamAgent(FakeAgent):
    def stream_chat_with_tool_result(self, messages, model=None, status_callback=None, agent_mode=None, trace_callback=None):
        raise ModelProviderError()


class ErrorAfterMetadataStreamAgent(FakeAgent):
    def stream_chat_with_tool_result(self, messages, model=None, status_callback=None, agent_mode=None, trace_callback=None):
        def stream():
            yield "partial"
            raise ModelProviderError()

        return stream(), None, []


class FailingChatAgent(FakeAgent):
    def chat(self, messages, model=None, agent_mode=None):
        raise ModelProviderError()


class BrokenChatAgent(FakeAgent):
    def chat(self, messages, model=None, agent_mode=None):
        raise RuntimeError("internal traceback should not leak")


class BrokenStreamAgent(FakeAgent):
    def stream_chat_with_tool_result(self, messages, model=None, status_callback=None, agent_mode=None, trace_callback=None):
        raise RuntimeError("internal traceback should not leak")


class FakeMemory:
    def build_memory_context(
        self,
        *,
        user_id,
        conversation_id,
        query,
        search_limit,
        recent_limit,
    ):
        return [], 0

    def add_memory(self, *, user_id, conversation_id, question, answer):
        return None


def make_test_client(monkeypatch, agent):
    original_get_agent = chat_api.get_agent
    monkeypatch.setattr(chat_api, "get_agent", lambda settings=None: agent)

    app = FastAPI()
    app.include_router(chat_api.router)
    app.dependency_overrides[chat_api.get_current_user] = lambda: CurrentUser(user_id="alice", username="alice")
    app.dependency_overrides[original_get_agent] = lambda: agent
    app.dependency_overrides[chat_api.get_conversation_store] = lambda: create_conversation_store(
        store_type="memory",
        max_rounds=10,
    )
    app.dependency_overrides[chat_api.get_memory_manager] = lambda: FakeMemory()
    app.dependency_overrides[chat_api.get_settings] = lambda: SimpleNamespace(
        dashscope_model="qwen-plus",
        memory_search_limit=5,
        memory_recent_context_limit=6,
    )
    return TestClient(app)


def parse_sse_events(body: str) -> list[dict]:
    events = []
    current_event = None
    current_data = []

    for line in body.splitlines():
        if not line:
            if current_event is not None:
                events.append(
                    {
                        "event": current_event,
                        "data": json.loads("\n".join(current_data)),
                    }
                )
            current_event = None
            current_data = []
            continue
        if line.startswith("event: "):
            current_event = line.removeprefix("event: ")
        elif line.startswith("data: "):
            current_data.append(line.removeprefix("data: "))

    return events


def assert_uuid(value: str) -> None:
    assert str(UUID(value)) == value


def test_chat_response_includes_generated_request_id(monkeypatch, caplog):
    client = make_test_client(monkeypatch, FakeAgent())

    with caplog.at_level(logging.INFO, logger="app.api.chat"):
        response = client.post(
            "/chat",
            json={
                "message": "do not log this complete user sentence",
                "conversation_id": "conversation-1",
                "model": "qwen-turbo",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert_uuid(payload["request_id"])
    assert payload["conversation_id"] == "conversation-1"
    assert payload["model"] == "qwen-turbo"

    log_text = caplog.text
    assert payload["request_id"] in log_text
    assert "conversation_id=conversation-1" in log_text
    assert "model=qwen-turbo" in log_text
    assert "agent_mode=plan_execute" in log_text
    assert "do not log this complete user sentence" not in log_text


def test_stream_metadata_and_done_include_same_request_id(monkeypatch):
    client = make_test_client(monkeypatch, FakeAgent())

    response = client.post(
        "/chat/stream",
        json={"message": "hello", "conversation_id": "stream-conversation"},
    )

    assert response.status_code == 200
    events = parse_sse_events(response.text)
    metadata = next(event["data"] for event in events if event["event"] == "metadata")
    done = next(event["data"] for event in events if event["event"] == "done")

    assert_uuid(metadata["request_id"])
    assert done["request_id"] == metadata["request_id"]
    assert metadata["conversation_id"] == "stream-conversation"
    assert done["conversation_id"] == "stream-conversation"
    assert done["model"] == "qwen-plus"


def test_chat_trace_steps_include_request_id_and_failure_detail(monkeypatch):
    client = make_test_client(monkeypatch, TraceAgent())

    response = client.post(
        "/chat",
        json={"message": "hello", "conversation_id": "trace-conversation"},
    )

    assert response.status_code == 200
    payload = response.json()
    failed_step = next(step for step in payload["trace"] if step["status"] == "failed")

    assert all(step["request_id"] == payload["request_id"] for step in payload["trace"])
    assert failed_step["step"] == "tool_call"
    assert failed_step["error_code"] == "NETWORK_ERROR"
    assert failed_step["retryable"] is True


def test_stream_trace_metadata_done_and_trace_events_share_request_id(monkeypatch):
    client = make_test_client(monkeypatch, TraceAgent())

    response = client.post(
        "/chat/stream",
        json={"message": "hello", "conversation_id": "stream-trace-conversation"},
    )

    assert response.status_code == 200
    events = parse_sse_events(response.text)
    metadata = next(event["data"] for event in events if event["event"] == "metadata")
    done = next(event["data"] for event in events if event["event"] == "done")
    trace_event = next(event["data"] for event in events if event["event"] == "trace")

    assert all(step["request_id"] == metadata["request_id"] for step in metadata["trace"])
    assert all(step["request_id"] == done["request_id"] for step in done["trace"])
    assert trace_event["step"]["request_id"] == metadata["request_id"]


def test_trace_observation_summarizes_tool_result_without_full_raw_payload():
    raw_payload = {
        "query": "private user query should not be copied as raw result",
        "search_results": [
            {"title": "A", "content": "long private source text " * 50},
            {"title": "B", "content": "another source " * 50},
        ],
    }

    observation = tool_result_to_observation(
        ToolResult(
            name="web_search",
            success=True,
            result=raw_payload,
            duration_ms=10.0,
        )
    )

    serialized = json.dumps(observation, ensure_ascii=False)
    assert "result" not in observation
    assert observation["result_summary"]["type"] == "object"
    assert observation["result_summary"]["search_results_count"] == 2
    assert "long private source text" not in serialized


def test_chat_tool_failure_detail_fields_are_consistent(monkeypatch):
    client = make_test_client(monkeypatch, ToolFailureAgent())

    response = client.post(
        "/chat",
        json={"message": "search please", "conversation_id": "tool-failure-conversation"},
    )

    assert response.status_code == 200
    payload = response.json()
    expected_detail = {
        "code": "NETWORK_ERROR",
        "message": "Search service is unavailable.",
        "retryable": True,
        "tool_name": "web_search",
        "duration_ms": 45.6,
    }

    assert payload["used_tool"] is True
    assert payload["tool_name"] == "web_search"
    assert payload["tool_status"] == "failed"
    assert payload["tool_error_code"] == expected_detail["code"]
    assert payload["tool_error_message"] == expected_detail["message"]
    assert payload["tool_retryable"] is True
    assert payload["tool_duration_ms"] == expected_detail["duration_ms"]
    assert payload["tool_error_detail"] == expected_detail


def test_stream_tool_failure_metadata_and_done_fields_are_consistent(monkeypatch):
    client = make_test_client(monkeypatch, ToolFailureAgent())

    response = client.post(
        "/chat/stream",
        json={"message": "search please", "conversation_id": "stream-tool-failure"},
    )

    assert response.status_code == 200
    events = parse_sse_events(response.text)
    metadata = next(event["data"] for event in events if event["event"] == "metadata")
    done = next(event["data"] for event in events if event["event"] == "done")
    expected_detail = {
        "code": "NETWORK_ERROR",
        "message": "Search service is unavailable.",
        "retryable": True,
        "tool_name": "web_search",
        "duration_ms": 45.6,
    }

    for payload in (metadata, done):
        assert payload["used_tool"] is True
        assert payload["tool_name"] == "web_search"
        assert payload["tool_status"] == "failed"
        assert payload["tool_error_code"] == expected_detail["code"]
        assert payload["tool_error_message"] == expected_detail["message"]
        assert payload["tool_retryable"] is True
        assert payload["tool_duration_ms"] == expected_detail["duration_ms"]
        assert payload["tool_error_detail"] == expected_detail

    assert done["tool_error_detail"] == metadata["tool_error_detail"]


def test_stream_error_event_includes_request_id(monkeypatch):
    client = make_test_client(monkeypatch, FailingStreamAgent())

    response = client.post(
        "/chat/stream",
        json={"message": "hello", "conversation_id": "error-conversation"},
    )

    assert response.status_code == 200
    events = parse_sse_events(response.text)
    error = next(event["data"] for event in events if event["event"] == "error")

    assert_uuid(error["request_id"])
    assert error["error"]["request_id"] == error["request_id"]
    assert error["error"]["code"] == "MODEL_PROVIDER_ERROR"
    assert error["error"]["message"]
    assert error["error"]["retryable"] is True
    assert "detail" not in error["error"]
    assert "traceback" not in error["error"]


def test_stream_metadata_and_error_events_share_request_id_with_structured_error(monkeypatch):
    client = make_test_client(monkeypatch, ErrorAfterMetadataStreamAgent())

    response = client.post(
        "/chat/stream",
        json={"message": "hello", "conversation_id": "stream-error-after-metadata"},
    )

    assert response.status_code == 200
    events = parse_sse_events(response.text)
    metadata = next(event["data"] for event in events if event["event"] == "metadata")
    error = next(event["data"] for event in events if event["event"] == "error")

    assert_uuid(metadata["request_id"])
    assert error["request_id"] == metadata["request_id"]
    assert error["error"] == {
        "code": "MODEL_PROVIDER_ERROR",
        "message": error["error"]["message"],
        "retryable": True,
        "request_id": metadata["request_id"],
    }
    assert "detail" not in error["error"]
    assert "traceback" not in error["error"]


def test_chat_agent_error_includes_request_id_and_retryable(monkeypatch):
    client = make_test_client(monkeypatch, FailingChatAgent())

    response = client.post(
        "/chat",
        json={"message": "hello", "conversation_id": "error-conversation"},
    )

    assert response.status_code == 502
    payload = response.json()
    error = payload["error"]

    assert payload["success"] is False
    assert_uuid(error["request_id"])
    assert error["code"] == "MODEL_PROVIDER_ERROR"
    assert error["message"]
    assert error["retryable"] is True
    assert "detail" not in error
    assert "traceback" not in error


def test_chat_unknown_error_includes_request_id_without_traceback(monkeypatch):
    client = make_test_client(monkeypatch, BrokenChatAgent())

    response = client.post(
        "/chat",
        json={"message": "hello", "conversation_id": "unknown-conversation"},
    )

    assert response.status_code == 500
    payload = response.json()
    error = payload["error"]

    assert payload["success"] is False
    assert_uuid(error["request_id"])
    assert error["code"] == "UNKNOWN_ERROR"
    assert error["message"]
    assert error["retryable"] is True
    assert "internal traceback should not leak" not in json.dumps(payload)
    assert "traceback" not in error


def test_stream_unknown_error_event_includes_request_id_without_traceback(monkeypatch):
    client = make_test_client(monkeypatch, BrokenStreamAgent())

    response = client.post(
        "/chat/stream",
        json={"message": "hello", "conversation_id": "stream-unknown-conversation"},
    )

    assert response.status_code == 200
    events = parse_sse_events(response.text)
    error = next(event["data"] for event in events if event["event"] == "error")

    assert_uuid(error["request_id"])
    assert error["error"]["request_id"] == error["request_id"]
    assert error["error"]["code"] == "UNKNOWN_ERROR"
    assert error["error"]["message"]
    assert error["error"]["retryable"] is True
    assert "internal traceback should not leak" not in json.dumps(error)
    assert "traceback" not in error["error"]
