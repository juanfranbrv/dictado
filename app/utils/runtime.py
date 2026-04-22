from __future__ import annotations

import os
import shutil
from pathlib import Path

from loguru import logger

from app.config import RuntimeSettings


def configure_runtime_paths(settings: RuntimeSettings) -> None:
    ffmpeg_bin = Path(settings.ffmpeg_bin)
    if not ffmpeg_bin.exists():
        logger.warning("Configured ffmpeg path does not exist: {}", ffmpeg_bin)
        return

    current_path = os.environ.get("PATH", "")
    path_entries = current_path.split(os.pathsep) if current_path else []
    ffmpeg_entry = str(ffmpeg_bin)

    if ffmpeg_entry not in path_entries:
        os.environ["PATH"] = os.pathsep.join([ffmpeg_entry, *path_entries]) if path_entries else ffmpeg_entry
        logger.info("Added ffmpeg bin to process PATH: {}", ffmpeg_entry)

    resolved = shutil.which("ffmpeg")
    if resolved:
        logger.info("ffmpeg available at {}", resolved)
    else:
        logger.warning("ffmpeg still not available on PATH after runtime setup")
