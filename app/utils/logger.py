"""
app/utils/logger.py

Structured logging configuration using structlog.
Import and use get_logger() anywhere in the app.

Usage:
    from app.utils.logger import get_logger
    logger = get_logger(__name__)
    logger.info("price_fetched", ticker="NVDA", price=112.50, source="finnhub")
    logger.error("price_fetch_failed", ticker="HY9H.F", error=str(e))
"""

import logging
import sys

import structlog

from app.config.settings import get_settings


def configure_logging() -> None:
    """
    Configure structlog for the application.

    In development: human-readable coloured console output.
    In production: JSON output suitable for log aggregation.

    Called once at application startup in main.py.
    """
    settings = get_settings()

    # Set the standard library logging level
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.DEBUG if settings.is_development else logging.INFO,
    )

    # Shared processors applied to every log entry
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M.%S", utc=False),
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.is_development:
        # Development: coloured, human-readable output
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True),
        ]
    else:
        # Production: machine-readable JSON
        processors = shared_processors + [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.DEBUG if settings.is_development else logging.INFO
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """
    Return a named structlog logger.

    Args:
        name: typically __name__ from the calling module

    Returns:
        A bound structlog logger instance with the module name in every log entry.
    """
    return structlog.get_logger().bind(logger=name)