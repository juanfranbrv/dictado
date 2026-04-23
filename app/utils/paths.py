from __future__ import annotations

import os
import sys
from pathlib import Path


APP_NAME = "dictado"


def bundle_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[2]


def user_data_dir() -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        path = Path(local_appdata) / APP_NAME
    else:
        path = Path.home() / "AppData" / "Local" / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_dir() -> Path:
    path = user_data_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def data_dir() -> Path:
    path = user_data_dir() / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir() -> Path:
    path = user_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def recordings_dir() -> Path:
    path = user_data_dir() / "recordings"
    path.mkdir(parents=True, exist_ok=True)
    return path


def whisper_models_dir() -> Path:
    path = user_data_dir() / "models" / "whisper"
    path.mkdir(parents=True, exist_ok=True)
    return path


def database_path() -> Path:
    return data_dir() / "dictado.sqlite3"


def language_state_path() -> Path:
    return data_dir() / "language_state.json"


def user_config_path() -> Path:
    return config_dir() / "config.toml"


def bundled_default_config_path() -> Path:
    return bundle_dir() / "config.default.toml"
