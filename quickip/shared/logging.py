"""Structured logging configuration."""

import logging
import logging.handlers
import json
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Any, Dict


class _WinSafeTimedRotatingFileHandler(logging.handlers.TimedRotatingFileHandler):
    """TimedRotatingFileHandler that works on Windows.

    On Windows, os.rename() fails with WinError 32 if the file is still open
    by the handler itself. This subclass closes the stream before renaming and
    reopens it afterwards, matching the approach used in CPython issue #82821.
    """

    def doRollover(self) -> None:
        if self.stream:
            self.stream.close()
            self.stream = None  # type: ignore[assignment]
        try:
            super().doRollover()
        finally:
            if self.stream is None:
                self.stream = self._open()

    def rotate(self, source: str, dest: str) -> None:
        """Replace dest if it already exists (Windows won't overwrite via rename)."""
        if os.path.exists(dest):
            os.remove(dest)
        os.rename(source, dest)


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

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields from record
        if hasattr(record, "correlation_id"):
            log_data["correlation_id"] = getattr(record, "correlation_id")

        if hasattr(record, "profile_id"):
            log_data["profile_id"] = getattr(record, "profile_id")

        if hasattr(record, "adapter"):
            log_data["adapter"] = getattr(record, "adapter")

        return json.dumps(log_data, ensure_ascii=False)


def setup_logging(
    log_dir: Path | None = None,
    log_level: str = "INFO",
    enable_console: bool = True,
    enable_file: bool = True
) -> None:
    """
    Setup application logging.
    
    Args:
        log_dir: Directory for log files (None = current directory)
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        enable_console: Enable console logging
        enable_file: Enable file logging
    """
    # Create log directory if needed
    if enable_file:
        if log_dir is None:
            log_dir = Path.cwd()
        log_dir.mkdir(parents=True, exist_ok=True)

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # Clear existing handlers
    root_logger.handlers.clear()

    # Console handler
    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)

    # File handler — ротация по дням, максимум 7 файлов
    if enable_file and log_dir:
        log_file = log_dir / "netconnexion.log"
        file_handler = _WinSafeTimedRotatingFileHandler(
            log_file,
            when="midnight",      # ротация в полночь
            interval=1,
            backupCount=7,        # хранить 7 дней
            encoding="utf-8",
            utc=False,
        )
        # Устанавливаем суффикс формата даты для архивных файлов
        file_handler.suffix = "%Y-%m-%d"
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(StructuredFormatter())
        root_logger.addHandler(file_handler)

    # Log startup
    logger = logging.getLogger(__name__)
    logger.info(
        "Logging initialized",
        extra={"log_level": log_level, "log_dir": str(log_dir) if log_dir else None}
    )


def get_logger(name: str) -> logging.Logger:
    """Get logger instance with correlation ID support."""
    return logging.getLogger(name)


class CorrelationIdFilter(logging.Filter):
    """Add correlation ID to log records."""

    def __init__(self, correlation_id: str):
        super().__init__()
        self.correlation_id = correlation_id

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = self.correlation_id
        return True
