from __future__ import annotations

import tomllib
import os
import tempfile
from pathlib import Path
from typing import Any

import tomli_w
from pydantic import BaseModel, ConfigDict, Field

from app.models import Profile
from app.utils.paths import bundled_default_config_path, bundle_dir, user_config_path


ROOT_DIR = bundle_dir()
DEFAULT_CONFIG_PATH = bundled_default_config_path()
USER_CONFIG_PATH = user_config_path()


class AppSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = "dictado"
    version: str = "0.1.0"
    debug: bool = False
    active_profile: str = "default"
    polish_enabled: bool = True
    hardware_profile_initialized: bool = False


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
    force_language_es: str = "ctrl+win+s"
    force_language_en: str = "ctrl+win+e"
    apply_polish: str = "ctrl+win+enter"
    discard_polish: str = "ctrl+win+backspace"


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
    show_language: bool = True


class LanguageSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preferred: list[str] = Field(default_factory=lambda: ["es", "en"])
    default: str = "es"
    confidence_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    switch_penalty: float = Field(default=0.15, ge=0.0, le=1.0)


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
    language: LanguageSettings
    profiles: dict[str, Profile]
    _config_path: Path | None = None


def _read_toml(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _write_toml(path: Path, data: dict) -> None:
    path.write_text(tomli_w.dumps(data), encoding="utf-8")


def _write_toml_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(tomli_w.dumps(data))
        os.replace(tmp_name, path)
    finally:
        tmp_path = Path(tmp_name)
        if tmp_path.exists():
            tmp_path.unlink()


def _build_profile(name: str, raw_profile: dict[str, Any]) -> Profile:
    return Profile(
        name=name,
        stt_provider=raw_profile.get("stt_provider", "faster-whisper"),
        stt_config=dict(raw_profile.get("stt_config", {})),
        llm_provider=raw_profile.get("llm_provider") or None,
        llm_config=dict(raw_profile["llm_config"]) if isinstance(raw_profile.get("llm_config"), dict) else None,
        llm_fallback_provider=raw_profile.get("llm_fallback_provider") or None,
        llm_fallback_config=dict(raw_profile["llm_fallback_config"]) if isinstance(raw_profile.get("llm_fallback_config"), dict) else None,
        polish_enabled=bool(raw_profile.get("polish_enabled", False)),
        inject_raw_first=bool(raw_profile.get("inject_raw_first", False)),
        style=str(raw_profile.get("style", "default")),
    )


def _inject_default_profile(config_data: dict[str, Any]) -> None:
    profiles = config_data.setdefault("profiles", {})
    if profiles:
        return

    stt = config_data.get("stt", {})
    profiles["default"] = {
        "stt_provider": stt.get("provider", "faster-whisper"),
        "llm_provider": "",
        "polish_enabled": False,
            "inject_raw_first": False,
        "style": "default",
        "stt_config": {
            "model": stt.get("model", "large-v3-turbo"),
            "device": stt.get("device", "cuda"),
            "compute_type": stt.get("compute_type", "float16"),
            "local_files_only": stt.get("local_files_only", True),
            "warmup_on_startup": stt.get("warmup_on_startup", True),
        },
    }


def _ensure_builtin_profiles(config_data: dict[str, Any]) -> None:
    profiles = config_data.setdefault("profiles", {})
    profiles.setdefault(
        "fast",
        {
            "stt_provider": "faster-whisper",
            "llm_provider": "",
            "polish_enabled": False,
            "style": "default",
            "stt_config": {
                "model": "large-v3-turbo",
                "device": "cuda",
                "compute_type": "float16",
                "local_files_only": True,
                "warmup_on_startup": True,
                "beam_size": 1,
            },
        },
    )
    profiles.setdefault(
        "low-spec",
        {
            "stt_provider": "faster-whisper",
            "llm_provider": "",
            "llm_fallback_provider": "",
            "polish_enabled": False,
            "style": "default",
            "stt_config": {
                "model": "small",
                "device": "cpu",
                "compute_type": "int8",
                "local_files_only": True,
                "warmup_on_startup": False,
                "beam_size": 1,
            },
        },
    )


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
    config_data.setdefault("app", {})
    config_data["app"].setdefault("polish_enabled", True)
    config_data["app"].setdefault("hardware_profile_initialized", False)
    config_data.setdefault("injection", {})
    config_data.setdefault("overlay", {})
    config_data.setdefault("language", {})
    _inject_default_profile(config_data)
    _ensure_builtin_profiles(config_data)
    hotkey_data = config_data.setdefault("hotkey", {})
    if "toggle" in hotkey_data and "combo" not in hotkey_data:
        hotkey_data["combo"] = hotkey_data.pop("toggle")
    hotkey_data.setdefault("combo", "ctrl+win")
    hotkey_data.setdefault("mode", "hold")
    raw_profiles = config_data.get("profiles", {})
    profile_map = {name: _build_profile(name, raw_profile) for name, raw_profile in raw_profiles.items()}
    config_data["profiles"] = profile_map
    config = Config.model_validate(config_data)
    config._config_path = config_path
    return config


def config_to_toml_dict(config: Config) -> dict[str, Any]:
    data = config.model_dump(mode="python")
    data.get("app", {}).pop("polish_enabled", None)
    profiles: dict[str, Any] = {}
    for name, profile in config.profiles.items():
        profile_data = {
            "stt_provider": profile.stt_provider,
            "llm_provider": profile.llm_provider or "",
            "llm_fallback_provider": profile.llm_fallback_provider or "",
            "polish_enabled": profile.polish_enabled,
            "style": profile.style,
            "stt_config": dict(profile.stt_config),
        }
        if profile.llm_config is not None:
            profile_data["llm_config"] = dict(profile.llm_config)
        if profile.llm_fallback_config is not None:
            profile_data["llm_fallback_config"] = dict(profile.llm_fallback_config)
        profiles[name] = profile_data
    data["profiles"] = profiles
    data.pop("_config_path", None)
    return data


def save_config(config: Config, path: Path | None = None) -> None:
    target = path or config._config_path or USER_CONFIG_PATH
    _write_toml_atomic(target, config_to_toml_dict(config))
