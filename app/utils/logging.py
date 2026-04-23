from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from app.config import LoggingSettings
from app.utils.paths import logs_dir


def setup_logging(settings: LoggingSettings) -> None:
    log_path = logs_dir() / Path(settings.file).name
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger.remove()
    console_sink = sys.stderr or sys.stdout
    if console_sink is not None:
        logger.add(
            console_sink,
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
