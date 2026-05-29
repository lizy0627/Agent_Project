import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys

from app.core.safe_logging import mask_sensitive_text, safe_log_data

BASE_DIR = Path(__file__).resolve().parents[2]
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "app.log"
LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
DEFAULT_LOG_LEVEL = logging.INFO
MAX_LOG_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 5


class SensitiveDataFilter(logging.Filter):
    """Mask common secrets in log messages and structured arguments."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = mask_sensitive_text(str(record.msg))
        if isinstance(record.args, dict):
            record.args = safe_log_data(record.args)
        elif isinstance(record.args, tuple):
            record.args = tuple(
                safe_log_data(value) if isinstance(value, (dict, list, tuple)) else mask_sensitive_text(value)
                if isinstance(value, str)
                else value
                for value in record.args
            )
        return True


def setup_logging() -> None:
    """Configure application logging once for console and logs/app.log."""

    root_logger = logging.getLogger()
    if getattr(root_logger, "_agent_logging_configured", False):
        return

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
    sensitive_filter = SensitiveDataFilter()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(sensitive_filter)

    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=MAX_LOG_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(sensitive_filter)

    root_logger.setLevel(DEFAULT_LOG_LEVEL)
    root_logger.handlers.clear()
    root_logger.addFilter(sensitive_filter)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    root_logger._agent_logging_configured = True

    logging.getLogger("uvicorn.access").addFilter(sensitive_filter)
    logging.getLogger("uvicorn.error").addFilter(sensitive_filter)


def get_logger(name: str) -> logging.Logger:
    """Return a named application logger."""

    return logging.getLogger(name)
