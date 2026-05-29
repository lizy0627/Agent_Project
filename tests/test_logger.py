import logging

from app.core.logger import LOG_FILE, get_logger, setup_logging
from app.core.safe_logging import mask_sensitive_text, safe_log_data
from backend.app.core.logger import get_logger as get_backend_logger


def test_setup_logging_writes_to_logs_app_log():
    setup_logging()

    logger = get_logger("tests.logger")
    logger.info("logger smoke test")

    assert LOG_FILE.name == "app.log"
    assert LOG_FILE.parent.name == "logs"
    assert LOG_FILE.exists()


def test_logging_masks_sensitive_values(caplog):
    setup_logging()
    logger = get_logger("tests.sensitive")

    with caplog.at_level(logging.INFO):
        logger.info("payload=%s", {"api_key": "secret-key", "message": "token=abc123"})

    output = caplog.text
    assert "secret-key" not in output
    assert "abc123" not in output
    assert "***" in output


def test_safe_logging_masks_free_text_and_nested_data():
    assert mask_sensitive_text("Authorization: Bearer abc123") == "Authorization: ***"
    assert safe_log_data({"password": "pw", "nested": {"API_KEY": "key"}}) == {
        "password": "***",
        "nested": {"API_KEY": "***"},
    }


def test_backend_logger_import_uses_same_logger():
    assert get_backend_logger("same").name == get_logger("same").name
