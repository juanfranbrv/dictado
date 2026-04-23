from __future__ import annotations

from dataclasses import dataclass

from loguru import logger
from pynput import keyboard

from app.events import EventBus


@dataclass(frozen=True)
class ParsedHotkey:
    parts: frozenset[keyboard.Key | keyboard.KeyCode]


class GlobalHotkey:
    """Global hotkey listener that emits start/stop events while the chord is held."""

    def __init__(self, event_bus: EventBus, combo: str) -> None:
        self._event_bus = event_bus
        self._combo = combo
        self._parsed = self._parse_combo(combo)
        self._pressed: set[keyboard.Key | keyboard.KeyCode] = set()
        self._active = False
        self._enabled = True
        self._listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)

    def start(self) -> None:
        logger.info("Starting hotkey listener with combo {}", self._combo)
        self._listener.start()

    def stop(self) -> None:
        logger.info("Stopping hotkey listener")
        self._listener.stop()

    def set_enabled(self, enabled: bool) -> None:
        if self._enabled == enabled:
            return
        self._enabled = enabled
        logger.info("Hotkey listener enabled={}", enabled)
        if not enabled and self._active:
            self._active = False
            self._event_bus.publish("STOP_RECORDING", {"combo": self._combo, "reason": "paused"})

    def _parse_combo(self, combo: str) -> ParsedHotkey:
        parts = [part.strip().lower() for part in combo.split("+") if part.strip()]
        if not parts:
            raise ValueError(f"Invalid hotkey combo '{combo}'")

        parsed_parts = [self._parse_part(part) for part in parts]
        return ParsedHotkey(parts=frozenset(parsed_parts))

    def _parse_part(self, part: str) -> keyboard.Key | keyboard.KeyCode:
        aliases: dict[str, keyboard.Key] = {
            "alt": keyboard.Key.alt,
            "alt_l": keyboard.Key.alt_l,
            "alt_r": keyboard.Key.alt_r,
            "backspace": keyboard.Key.backspace,
            "ctrl": keyboard.Key.ctrl,
            "ctrl_l": keyboard.Key.ctrl_l,
            "ctrl_r": keyboard.Key.ctrl_r,
            "enter": keyboard.Key.enter,
            "shift": keyboard.Key.shift,
            "shift_l": keyboard.Key.shift_l,
            "shift_r": keyboard.Key.shift_r,
            "space": keyboard.Key.space,
            "win": keyboard.Key.cmd,
            "cmd": keyboard.Key.cmd,
        }
        if part in aliases:
            return aliases[part]
        if len(part) == 1:
            return keyboard.KeyCode.from_char(part)
        raise ValueError(f"Unsupported hotkey token '{part}'")

    def _canonical(self, key: keyboard.Key | keyboard.KeyCode) -> keyboard.Key | keyboard.KeyCode:
        try:
            key = self._listener.canonical(key)
        except AttributeError:
            pass

        normalize_modifiers = {
            keyboard.Key.alt_l: keyboard.Key.alt,
            keyboard.Key.alt_r: keyboard.Key.alt,
            keyboard.Key.ctrl_l: keyboard.Key.ctrl,
            keyboard.Key.ctrl_r: keyboard.Key.ctrl,
            keyboard.Key.shift_l: keyboard.Key.shift,
            keyboard.Key.shift_r: keyboard.Key.shift,
            keyboard.Key.cmd_l: keyboard.Key.cmd,
            keyboard.Key.cmd_r: keyboard.Key.cmd,
        }
        return normalize_modifiers.get(key, key)

    def _on_press(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        if not self._enabled:
            return
        canonical = self._canonical(key)
        self._pressed.add(canonical)

        if self._active:
            return

        if self._parsed.parts.issubset(self._pressed):
            self._active = True
            logger.info("Hotkey engaged")
            self._event_bus.publish("START_RECORDING", {"combo": self._combo})

    def _on_release(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        canonical = self._canonical(key)
        self._pressed.discard(canonical)

        if self._active and not self._parsed.parts.issubset(self._pressed):
            self._active = False
            logger.info("Hotkey released")
            self._event_bus.publish("STOP_RECORDING", {"combo": self._combo})


class TriggerHotkey:
    """One-shot global hotkey listener that emits a single event on press."""

    def __init__(self, event_bus: EventBus, combo: str, event_name: str) -> None:
        self._event_bus = event_bus
        self._combo = combo
        self._event_name = event_name
        parser = GlobalHotkey(event_bus, combo)
        self._parsed = parser._parse_combo(combo)
        self._pressed: set[keyboard.Key | keyboard.KeyCode] = set()
        self._active = False
        self._enabled = True
        self._listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)

    def start(self) -> None:
        logger.info("Starting trigger hotkey listener with combo {}", self._combo)
        self._listener.start()

    def stop(self) -> None:
        logger.info("Stopping trigger hotkey listener {}", self._combo)
        self._listener.stop()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        if not enabled:
            self._active = False

    def _canonical(self, key: keyboard.Key | keyboard.KeyCode) -> keyboard.Key | keyboard.KeyCode:
        try:
            key = self._listener.canonical(key)
        except AttributeError:
            pass

        normalize_modifiers = {
            keyboard.Key.alt_l: keyboard.Key.alt,
            keyboard.Key.alt_r: keyboard.Key.alt,
            keyboard.Key.ctrl_l: keyboard.Key.ctrl,
            keyboard.Key.ctrl_r: keyboard.Key.ctrl,
            keyboard.Key.shift_l: keyboard.Key.shift,
            keyboard.Key.shift_r: keyboard.Key.shift,
            keyboard.Key.cmd_l: keyboard.Key.cmd,
            keyboard.Key.cmd_r: keyboard.Key.cmd,
        }
        return normalize_modifiers.get(key, key)

    def _on_press(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        if not self._enabled:
            return

        canonical = self._canonical(key)
        self._pressed.add(canonical)
        if self._active:
            return

        if self._parsed.parts.issubset(self._pressed):
            self._active = True
            logger.info("Trigger hotkey fired {}", self._combo)
            self._event_bus.publish(self._event_name, {"combo": self._combo})

    def _on_release(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        canonical = self._canonical(key)
        self._pressed.discard(canonical)
        if self._active and not self._parsed.parts.issubset(self._pressed):
            self._active = False
