"""Loguru structured logging configuration.

Provides JSON-formatted structured logging with configurable log level
and request context.
"""

import sys

from loguru import logger


def setup_logging(log_level: str = "INFO") -> None:
    """Configure Loguru for structured JSON logging.

    Args:
        log_level: Minimum log level to emit.
    """
    logger.remove()
    logger.add(
        sys.stderr,
        level=log_level.upper(),
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {name}:{function}:{line} | {message}",
        serialize=False,
    )
    logger.add(
        sys.stderr,
        level=log_level.upper(),
        serialize=True,
        filter=lambda record: record["extra"].get("json_output", False),
    )
