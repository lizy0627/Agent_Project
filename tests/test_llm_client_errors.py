import logging

import httpx
import pytest
from openai import APIConnectionError, APIStatusError, APITimeoutError, AuthenticationError, OpenAIError

from app.core.exceptions import (
    ApiKeyInvalidError,
    ErrorCode,
    InvalidArgumentsError,
    ModelNetworkError,
    ModelProviderError,
    ModelTimeoutError,
)
from app.services.llm_client import LLMClient


class FakeCompletions:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def create(self, **_) -> object:
        raise self.error


class FakeChat:
    def __init__(self, error: Exception) -> None:
        self.completions = FakeCompletions(error)


class FakeOpenAIClient:
    def __init__(self, error: Exception) -> None:
        self.chat = FakeChat(error)


def client_raising(error: Exception) -> LLMClient:
    client = LLMClient.__new__(LLMClient)
    client.model = "qwen-test"
    client.client = FakeOpenAIClient(error)
    return client


def api_status_error(status_code: int, error_type: str = "provider_error") -> APIStatusError:
    request = httpx.Request("POST", "https://example.test/v1/chat/completions")
    body = {
        "error": {
            "type": error_type,
            "message": "safe provider message with api_key=sk-test-secret",
        },
    }
    response = httpx.Response(status_code, request=request, json=body)
    return APIStatusError("provider error with api_key=sk-test-secret", response=response, body=body)


def authentication_error() -> AuthenticationError:
    request = httpx.Request("POST", "https://example.test/v1/chat/completions")
    body = {"error": {"type": "authentication_error"}}
    response = httpx.Response(401, request=request, json=body)
    return AuthenticationError("bad api_key=sk-test-secret", response=response, body=body)


@pytest.mark.parametrize(
    ("status_code", "expected_type", "expected_code", "expected_retryable", "expected_status"),
    [
        (401, ApiKeyInvalidError, ErrorCode.API_KEY_INVALID, False, 401),
        (403, ApiKeyInvalidError, ErrorCode.API_KEY_INVALID, False, 401),
        (408, ModelTimeoutError, ErrorCode.MODEL_TIMEOUT, True, 504),
        (504, ModelTimeoutError, ErrorCode.MODEL_TIMEOUT, True, 504),
        (429, ModelProviderError, ErrorCode.RATE_LIMIT, True, 429),
        (500, ModelProviderError, ErrorCode.MODEL_PROVIDER_ERROR, True, 500),
        (503, ModelProviderError, ErrorCode.MODEL_PROVIDER_ERROR, True, 503),
        (400, InvalidArgumentsError, ErrorCode.INVALID_ARGUMENTS, False, 422),
        (422, InvalidArgumentsError, ErrorCode.INVALID_ARGUMENTS, False, 422),
    ],
)
def test_complete_chat_maps_api_status_errors(
    status_code: int,
    expected_type: type[Exception],
    expected_code: ErrorCode,
    expected_retryable: bool,
    expected_status: int,
):
    client = client_raising(api_status_error(status_code, "rate_limit_error"))

    with pytest.raises(expected_type) as exc_info:
        client.complete_chat([])

    error = exc_info.value
    assert error.code == expected_code
    assert error.retryable is expected_retryable
    assert error.status_code == expected_status


def test_stream_complete_chat_maps_api_status_errors():
    client = client_raising(api_status_error(429, "rate_limit_error"))

    with pytest.raises(ModelProviderError) as exc_info:
        list(client.stream_complete_chat([]))

    assert exc_info.value.code == ErrorCode.RATE_LIMIT
    assert exc_info.value.retryable is True
    assert exc_info.value.status_code == 429


@pytest.mark.parametrize(
    ("error", "expected_type", "expected_code", "expected_retryable", "expected_status"),
    [
        (
            authentication_error(),
            ApiKeyInvalidError,
            ErrorCode.API_KEY_INVALID,
            False,
            401,
        ),
        (
            APITimeoutError(request=httpx.Request("POST", "https://example.test/v1/chat/completions")),
            ModelTimeoutError,
            ErrorCode.MODEL_TIMEOUT,
            True,
            504,
        ),
        (
            APIConnectionError(
                message="connection failed with api_key=sk-test-secret",
                request=httpx.Request("POST", "https://example.test/v1/chat/completions"),
            ),
            ModelNetworkError,
            ErrorCode.NETWORK_ERROR,
            True,
            503,
        ),
    ],
)
def test_complete_chat_maps_openai_errors(
    error: Exception,
    expected_type: type[Exception],
    expected_code: ErrorCode,
    expected_retryable: bool,
    expected_status: int,
):
    client = client_raising(error)

    with pytest.raises(expected_type) as exc_info:
        client.complete_chat([])

    mapped_error = exc_info.value
    assert mapped_error.code == expected_code
    assert mapped_error.retryable is expected_retryable
    assert mapped_error.status_code == expected_status


@pytest.mark.parametrize(
    ("error", "expected_type", "expected_code"),
    [
        (
            APITimeoutError(request=httpx.Request("POST", "https://example.test/v1/chat/completions")),
            ModelTimeoutError,
            ErrorCode.MODEL_TIMEOUT,
        ),
        (
            APIConnectionError(
                message="connection failed",
                request=httpx.Request("POST", "https://example.test/v1/chat/completions"),
            ),
            ModelNetworkError,
            ErrorCode.NETWORK_ERROR,
        ),
        (authentication_error(), ApiKeyInvalidError, ErrorCode.API_KEY_INVALID),
        (api_status_error(429, "rate_limit_error"), ModelProviderError, ErrorCode.RATE_LIMIT),
        (api_status_error(500, "server_error"), ModelProviderError, ErrorCode.MODEL_PROVIDER_ERROR),
    ],
)
def test_complete_chat_stability_error_mapping(error: Exception, expected_type: type[Exception], expected_code: ErrorCode):
    client = client_raising(error)

    with pytest.raises(expected_type) as exc_info:
        client.complete_chat([])

    assert exc_info.value.code == expected_code


def test_stream_complete_chat_maps_direct_openai_errors():
    client = client_raising(APITimeoutError(request=httpx.Request("POST", "https://example.test/v1/chat/completions")))

    with pytest.raises(ModelTimeoutError) as exc_info:
        list(client.stream_complete_chat([]))

    assert exc_info.value.code == ErrorCode.MODEL_TIMEOUT
    assert exc_info.value.retryable is True
    assert exc_info.value.status_code == 504


def test_openai_errors_log_safe_type_without_secret_or_traceback(caplog):
    client = client_raising(OpenAIError("provider exploded with api_key=sk-test-secret"))

    with caplog.at_level(logging.WARNING):
        with pytest.raises(ModelProviderError):
            client.complete_chat([])

    assert "OpenAIError" in caplog.text
    assert "sk-test-secret" not in caplog.text
    assert "Traceback" not in caplog.text
