"""Loguru structured logging configuration.

Provides JSON-formatted structured logging with configurable log level
and request context.  Optionally writes to a rotating log file when a
``log_dir`` is provided.
"""

import sys
from pathlib import Path

from loguru import logger

_LOG_FORMAT = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {name}:{function}:{line} | {message}"


def setup_logging(log_level: str = "INFO", log_dir: str | None = None) -> None:
    """Configure Loguru for structured JSON logging.

    Args:
        log_level: Minimum log level to emit.
        log_dir: Optional directory for log files.  When set, a rotating
            file sink is added (rotated every 24 hours, retained 7 days).
    """
    logger.remove()
    logger.add(
        sys.stderr,
        level=log_level.upper(),
        format=_LOG_FORMAT,
        serialize=False,
    )
    logger.add(
        sys.stderr,
        level=log_level.upper(),
        serialize=True,
        filter=lambda record: record["extra"].get("json_output", False),
    )

    if log_dir:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        logger.add(
            log_path / "voter-api.log",
            level=log_level.upper(),
            format=_LOG_FORMAT,
            rotation="24h",
            retention="7 days",
        )
