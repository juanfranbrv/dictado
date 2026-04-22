from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from app.config import LoggingSettings, ROOT_DIR


def setup_logging(settings: LoggingSettings) -> None:
    log_path = ROOT_DIR / settings.file
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.level.upper(),
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    )
    logger.add(
        log_path,
        level=settings.level.upper(),
        rotation="5 MB",
        retention=5,
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}",
    )
    logger.debug("Logging initialized")
