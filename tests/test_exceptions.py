import json

from app.core.exceptions import AgentError, ErrorCode, ModelProviderError, error_payload, error_response, public_error_message


def test_error_payload_includes_retryable_and_keeps_legacy_fields():
    payload = error_payload(ModelProviderError())

    assert payload["success"] is False
    assert payload["error"]["code"] == "MODEL_PROVIDER_ERROR"
    assert payload["error"]["message"]
    assert payload["error"]["retryable"] is True
    assert "request_id" not in payload["error"]
    assert "detail" not in payload["error"]
    assert "traceback" not in payload["error"]


def test_error_payload_supports_request_id_and_explicit_detail_only():
    error = AgentError(
        message="Bad arguments",
        code=ErrorCode.INVALID_ARGUMENTS,
        status_code=422,
        retryable=False,
    )

    payload = error_payload(
        error,
        message="Invalid field.",
        request_id="req-123",
        detail={"field": "message", "reason": "required"},
    )

    assert payload == {
        "success": False,
        "error": {
            "code": "INVALID_ARGUMENTS",
            "message": "Invalid field.",
            "retryable": False,
            "request_id": "req-123",
            "detail": {"field": "message", "reason": "required"},
        },
    }


def test_error_response_forwards_structured_error_options():
    response = error_response(
        AgentError("missing", code=ErrorCode.NOT_FOUND, status_code=404, retryable=False),
        request_id="req-404",
        detail={"resource": "document"},
    )

    assert response.status_code == 404
    payload = json.loads(response.body)
    assert payload["error"]["request_id"] == "req-404"
    assert payload["error"]["detail"] == {"resource": "document"}
    assert payload["error"]["retryable"] is False


def test_public_error_message_supports_rate_limit():
    message = public_error_message(
        AgentError(
            "rate limited",
            code=ErrorCode.RATE_LIMIT,
            status_code=429,
            retryable=True,
        )
    )

    assert message == "请求过于频繁，请稍后重试。"
