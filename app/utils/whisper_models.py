from __future__ import annotations

import shutil
from pathlib import Path

from faster_whisper.utils import download_model
from loguru import logger

from app.utils.paths import whisper_models_dir


def is_whisper_model_available(model_name: str) -> bool:
    path = resolve_whisper_model_path(model_name)
    if path is None:
        return False
    return _is_model_directory_usable(path)


def download_whisper_model(model_name: str) -> str:
    logger.info("Downloading Whisper model {}", model_name)
    target_dir = managed_whisper_model_dir(model_name)
    if target_dir.exists() and not _is_model_directory_usable(target_dir):
        logger.warning("Removing broken managed Whisper model at {}", target_dir)
        shutil.rmtree(target_dir, ignore_errors=True)
    target_dir.mkdir(parents=True, exist_ok=True)
    return str(
        download_model(
            model_name,
            output_dir=str(target_dir),
            local_files_only=False,
        )
    )


def resolve_whisper_model_path(model_name: str) -> Path | None:
    normalized = model_name.strip()
    if not normalized:
        return None

    candidate_path = Path(normalized)
    if _safe_exists(candidate_path):
        return candidate_path

    managed_dir = managed_whisper_model_dir(normalized)
    if _safe_exists(managed_dir):
        return managed_dir
    return None


def whisper_model_load_target(model_name: str) -> str:
    path = resolve_whisper_model_path(model_name)
    if path is not None:
        return str(path)
    return str(managed_whisper_model_dir(model_name))


def managed_whisper_model_dir(model_name: str) -> Path:
    sanitized = model_name.strip().replace("/", "__").replace("\\", "__").replace(":", "_")
    return whisper_models_dir() / sanitized


def _is_model_directory_usable(path: Path) -> bool:
    try:
        if path.is_file():
            return path.name == "model.bin" and path.stat().st_size > 0
    except OSError as exc:
        logger.warning("Unable to inspect Whisper model path {}: {}", path, exc)
        return False

    required_files = [
        path / "model.bin",
        path / "config.json",
        path / "tokenizer.json",
    ]
    for required in required_files:
        size = _safe_file_size(required)
        if size is None:
            return False
        if size <= 0:
            return False
    return True


def _safe_exists(path: Path) -> bool:
    try:
        return path.exists()
    except OSError as exc:
        logger.warning("Unable to inspect path {}: {}", path, exc)
        return False


def _safe_file_size(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except OSError as exc:
        logger.warning("Unable to inspect Whisper model file {}: {}", path, exc)
        return None
