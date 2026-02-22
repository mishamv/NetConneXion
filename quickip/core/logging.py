"""Structured logging configuration."""

import logging
import logging.handlers
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Any, Dict


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        if hasattr(record, "correlation_id"):
            log_data["correlation_id"] = record.correlation_id

        if hasattr(record, "profile_id"):
            log_data["profile_id"] = record.profile_id

        if hasattr(record, "adapter"):
            log_data["adapter"] = record.adapter

        return json.dumps(log_data, ensure_ascii=False)


def setup_logging(
    log_dir: Path | None = None,
    log_level: str = "INFO",
    enable_console: bool = True,
    enable_file: bool = True,
) -> None:
    """
    Setup application logging.

    Args:
        log_dir: Directory for log files (None = current directory).
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR).
        enable_console: Enable console logging.
        enable_file: Enable file logging.
    """
    if enable_file:
        if log_dir is None:
            log_dir = Path.cwd()
        log_dir.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    root_logger.handlers.clear()

    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        root_logger.addHandler(console_handler)

    if enable_file and log_dir:
        log_file = log_dir / "quickip.log"
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(StructuredFormatter())
        root_logger.addHandler(file_handler)

    logger = logging.getLogger(__name__)
    logger.info("Logging initialized", extra={
        "log_level": log_level,
        "log_dir": str(log_dir) if log_dir else None,
    })


def get_logger(name: str) -> logging.Logger:
    """Get logger instance."""
    return logging.getLogger(name)


class CorrelationIdFilter(logging.Filter):
    """Add correlation ID to log records."""

    def __init__(self, correlation_id: str) -> None:
        super().__init__()
        self.correlation_id = correlation_id

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = self.correlation_id
        return True
