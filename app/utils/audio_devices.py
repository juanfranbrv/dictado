from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import sounddevice as sd
from loguru import logger


@dataclass(slots=True)
class InputDevice:
    index: int
    name: str
    hostapi: str
    default_samplerate: float
    max_input_channels: int

    @property
    def label(self) -> str:
        return f"{self.name} [{self.hostapi}]"


def list_input_devices() -> list[InputDevice]:
    devices = sd.query_devices()
    hostapis = sd.query_hostapis()
    results: list[InputDevice] = []
    for index, raw_device in enumerate(devices):
        max_input_channels = int(raw_device.get("max_input_channels", 0))
        if max_input_channels <= 0:
            continue
        hostapi_index = int(raw_device.get("hostapi", -1))
        hostapi_name = ""
        if 0 <= hostapi_index < len(hostapis):
            hostapi_name = str(hostapis[hostapi_index].get("name", ""))
        results.append(
            InputDevice(
                index=index,
                name=str(raw_device.get("name", "")).strip(),
                hostapi=hostapi_name,
                default_samplerate=float(raw_device.get("default_samplerate", 0.0)),
                max_input_channels=max_input_channels,
            )
        )
    return sorted(results, key=_device_priority)


def resolve_input_device(configured_device: str) -> str | int | None:
    candidates = input_device_candidates(configured_device)
    if not candidates:
        return None
    return candidates[0][1]


def input_device_candidates(configured_device: str) -> list[tuple[str, str | int | None]]:
    devices = list_input_devices()
    if not devices:
        logger.warning("No input devices reported by sounddevice; using system default input")
        return [("system default", None)]

    configured_device = configured_device.strip()
    candidates: list[tuple[str, str | int | None]] = []
    seen: set[str] = set()

    def append_candidate(reason: str, device: str | int | None) -> None:
        key = repr(device)
        if key in seen:
            return
        seen.add(key)
        candidates.append((reason, device))

    if configured_device:
        matched = _find_device_by_name(devices, configured_device)
        if matched is not None:
            append_candidate(f"configured input {matched.label}", matched.index)
        else:
            logger.warning(
                "Configured input device not found: {}. Falling back automatically.",
                configured_device,
            )

    default_input = _resolve_default_input_device(devices)
    if default_input is not None:
        append_candidate(f"default input {default_input.label}", default_input.index)

    preferred_input = _pick_preferred_input(devices)
    append_candidate(f"preferred input {preferred_input.label}", preferred_input.index)

    if not candidates:
        append_candidate("system default", None)
    return candidates


def _find_device_by_name(devices: list[InputDevice], expected_name: str) -> InputDevice | None:
    expected_name = expected_name.casefold()
    for device in devices:
        if device.label.casefold() == expected_name:
            return device
    for device in devices:
        if device.name.casefold() == expected_name:
            return device
    for device in devices:
        if expected_name in device.name.casefold():
            return device
    return None


def _resolve_default_input_device(devices: list[InputDevice]) -> InputDevice | None:
    try:
        raw_default = sd.default.device
    except Exception as exc:
        logger.warning("Unable to read default audio device from sounddevice: {}", exc)
        return None

    input_index = _coerce_default_input_index(raw_default)
    if input_index is None:
        return None
    if input_index < 0:
        return None

    for device in devices:
        if device.index == input_index:
            return device
    return None


def _coerce_default_input_index(raw_default: Any) -> int | None:
    if isinstance(raw_default, int):
        return raw_default
    try:
        return int(raw_default[0])
    except (TypeError, ValueError, IndexError, KeyError):
        return None


def _pick_preferred_input(devices: list[InputDevice]) -> InputDevice:
    ranked = sorted(devices, key=_device_priority)
    return ranked[0]


def _device_priority(device: InputDevice) -> tuple[int, int, int, str]:
    name = device.name.casefold()
    looks_like_microphone = any(token in name for token in ("mic", "microphone", "micrófono"))
    looks_virtual = any(
        token in name
        for token in (
            "mapper",
            "asignador",
            "stereo mix",
            "mezcla estéreo",
            "line in",
            "línea de entrada",
            "linea de entrada",
            "hands-free",
            "manos libres",
            "bluetooth",
            "auriculares con micrófono",
        )
    )
    looks_dedicated = any(token in name for token in ("usb", "razer", "realtek", "seiren"))
    virtual_rank = 1 if looks_virtual else 0
    microphone_rank = 0 if looks_like_microphone else 1
    dedicated_rank = 0 if looks_dedicated else 1
    return (virtual_rank, microphone_rank, dedicated_rank, name)
