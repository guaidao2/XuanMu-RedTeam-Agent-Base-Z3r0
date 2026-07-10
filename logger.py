import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import TextIO

from config import WORKSPACE


_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_DEFAULT_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(filename)s:%(lineno)d | %(message)s"
_UVICORN_LOGGERS = (
    "uvicorn",
    "uvicorn.error",
    "uvicorn.access",
    "uvicorn.asgi",
)
_LIBRARY_LOGGERS = (
    "openai",
    "openai.agents",
    "fastapi",
    "httpcore",
    "httpx",
    "asyncpg",
    "asyncssh",
    "websockets",
    "sqlalchemy",
)


_is_configured = False


def _coerce_level(level: str | int) -> int:
    if isinstance(level, int):
        return level
    normalized = level.strip().upper()
    resolved = getattr(logging, normalized, logging.INFO)
    return resolved if isinstance(resolved, int) else logging.INFO


def _build_formatter() -> logging.Formatter:
    return logging.Formatter(fmt=_DEFAULT_FORMAT, datefmt=_DATE_FORMAT)


def _clear_handlers(logger: logging.Logger) -> None:
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


def configure_library_loggers(level: str | int | None = None) -> None:
    for logger_name in _UVICORN_LOGGERS:
        uvicorn_logger = logging.getLogger(logger_name)
        _clear_handlers(uvicorn_logger)
        uvicorn_logger.disabled = True
        uvicorn_logger.propagate = False

    resolved_level = _coerce_level(level) if level is not None else None
    quiet_level = max(logging.WARNING, resolved_level or logging.WARNING)
    for logger_name in _LIBRARY_LOGGERS:
        library_logger = logging.getLogger(logger_name)
        _clear_handlers(library_logger)
        library_logger.propagate = True
        library_logger.disabled = False
        library_logger.setLevel(quiet_level)


def setup_logging(
    level: str | int = "INFO",
    file_path: Path = WORKSPACE / "app.log",
    console_stream: TextIO | None = None,
    force: bool = False,
) -> None:
    global _is_configured
    if _is_configured and not force:
        return

    resolved_level = _coerce_level(level)
    formatter = _build_formatter()
    root_logger = logging.getLogger()
    _clear_handlers(root_logger)

    stream_handler = logging.StreamHandler(console_stream or sys.stdout)
    stream_handler.setLevel(resolved_level)
    stream_handler.setFormatter(formatter)

    file_handler = TimedRotatingFileHandler(
        filename=file_path,
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
    )
    file_handler.setLevel(resolved_level)
    file_handler.setFormatter(formatter)

    root_logger.setLevel(resolved_level)
    root_logger.propagate = False
    root_logger.addHandler(stream_handler)
    root_logger.addHandler(file_handler)

    configure_library_loggers(resolved_level)
    _is_configured = True


def get_logger(name: str | None = None) -> logging.Logger:
    return logging.getLogger(name)
