from app.api.chat import stream_error_payload, tool_error_detail, tool_response_metadata
from app.core.exceptions import ModelProviderError
from app.schemas.chat import ChatResponse
from app.tools.base import ToolResult


def failed_tool_result() -> ToolResult:
    return ToolResult(
        name="web_search",
        success=False,
        error="raw search failure",
        duration_ms=12.34,
        error_code="NETWORK_ERROR",
        error_message="Search service is unavailable.",
        retryable=True,
    )


def test_tool_error_detail_includes_retryable_tool_name_and_duration():
    detail = tool_error_detail(failed_tool_result())

    assert detail == {
        "code": "NETWORK_ERROR",
        "message": "Search service is unavailable.",
        "retryable": True,
        "tool_name": "web_search",
        "duration_ms": 12.34,
    }


def test_tool_response_metadata_uses_same_error_detail_shape():
    metadata = tool_response_metadata(failed_tool_result())

    assert metadata["tool_error_detail"] == {
        "code": "NETWORK_ERROR",
        "message": "Search service is unavailable.",
        "retryable": True,
        "tool_name": "web_search",
        "duration_ms": 12.34,
    }


def test_chat_response_preserves_tool_error_detail_fields():
    response = ChatResponse(
        request_id="req-123",
        reply="工具调用失败，请查看错误原因后重试。",
        model="qwen-plus",
        conversation_id="conversation-1",
        used_tool=True,
        tool_name="web_search",
        tool_status="failed",
        tool_error_detail=tool_error_detail(failed_tool_result()),
    )

    assert response.model_dump()["request_id"] == "req-123"
    assert response.model_dump()["tool_error_detail"] == {
        "code": "NETWORK_ERROR",
        "message": "Search service is unavailable.",
        "retryable": True,
        "tool_name": "web_search",
        "duration_ms": 12.34,
    }


def test_stream_error_payload_includes_request_id_at_top_level_and_error_detail():
    payload = stream_error_payload(ModelProviderError(), request_id="req-stream")

    assert payload["request_id"] == "req-stream"
    assert payload["error"]["request_id"] == "req-stream"
