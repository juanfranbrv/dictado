from __future__ import annotations

import tomllib
from pathlib import Path

import tomli_w
from pydantic import BaseModel, ConfigDict, Field


ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = ROOT_DIR / "config.default.toml"
USER_CONFIG_PATH = ROOT_DIR / "config.toml"


class AppSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = "dictado"
    version: str = "0.1.0"
    debug: bool = False


class LoggingSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: str = "INFO"
    file: str = "logs/dictado.log"


class RuntimeSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ffmpeg_bin: str = "C:/ffmpeg/bin"


class HotkeySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    combo: str = "ctrl+win"
    mode: str = "hold"


class AudioSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_rate: int = Field(default=16000, ge=8000)
    channels: int = Field(default=1, ge=1)
    device: str = ""
    blocksize: int = Field(default=0, ge=0)


class STTSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = "faster-whisper"
    model: str = "large-v3-turbo"
    device: str = "cuda"
    compute_type: str = "float16"
    local_files_only: bool = True
    warmup_on_startup: bool = True


class InjectionSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: str = "sendinput"
    fallback_to_clipboard: bool = True


class OverlaySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    position: str = "bottom-center"


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    app: AppSettings
    logging: LoggingSettings
    runtime: RuntimeSettings
    hotkey: HotkeySettings
    audio: AudioSettings
    stt: STTSettings
    injection: InjectionSettings
    overlay: OverlaySettings
    _config_path: Path | None = None


def _read_toml(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _write_toml(path: Path, data: dict) -> None:
    path.write_text(tomli_w.dumps(data), encoding="utf-8")


def ensure_user_config() -> Path:
    if USER_CONFIG_PATH.exists():
        return USER_CONFIG_PATH

    data = _read_toml(DEFAULT_CONFIG_PATH)
    _write_toml(USER_CONFIG_PATH, data)
    return USER_CONFIG_PATH


def load_config() -> Config:
    config_path = ensure_user_config()
    config_data = _read_toml(config_path)
    config_data.setdefault("runtime", {})
    config_data.setdefault("injection", {})
    config_data.setdefault("overlay", {})
    hotkey_data = config_data.setdefault("hotkey", {})
    if "toggle" in hotkey_data and "combo" not in hotkey_data:
        hotkey_data["combo"] = hotkey_data.pop("toggle")
    hotkey_data.setdefault("combo", "ctrl+win")
    hotkey_data.setdefault("mode", "hold")
    config = Config.model_validate(config_data)
    config._config_path = config_path
    return config
