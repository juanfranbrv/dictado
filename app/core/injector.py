from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from typing import Any

import win32clipboard
import win32con
import win32api
from loguru import logger

from app.config import InjectionSettings
from app.events import EventBus


INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
CF_UNICODETEXT = 13
VK_CONTROL = 0x11
VK_V = 0x56
ULONG_PTR = ctypes.c_size_t


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("union",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", INPUTUNION),
    ]


class TextInjector:
    """Inject transcript text into the active window."""

    def __init__(self, event_bus: EventBus, settings: InjectionSettings) -> None:
        self._event_bus = event_bus
        self._settings = settings
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._send_input = self._user32.SendInput
        self._send_input.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
        self._send_input.restype = wintypes.UINT

    def attach(self) -> None:
        self._event_bus.subscribe("TRANSCRIPT_READY", self._handle_transcript_ready)

    def inject_text(self, text: str) -> None:
        if not text:
            logger.info("Skipping injection for empty transcript")
            return

        try:
            if self._settings.method == "clipboard":
                self._inject_via_clipboard(text)
            else:
                self._inject_via_sendinput(text)
        except Exception as exc:
            if not self._settings.fallback_to_clipboard or self._settings.method == "clipboard":
                raise
            logger.warning("SendInput injection failed ({}). Falling back to clipboard.", exc)
            self._inject_via_clipboard(text)

    def _handle_transcript_ready(self, payload: dict[str, Any]) -> None:
        transcript = payload["transcript"]
        self.inject_text(transcript.text)

    def _inject_via_sendinput(self, text: str) -> None:
        logger.info("Injecting text via SendInput ({} chars)", len(text))
        inputs: list[INPUT] = []
        for char in text:
            inputs.append(self._keyboard_input(0, ord(char), KEYEVENTF_UNICODE))
            inputs.append(self._keyboard_input(0, ord(char), KEYEVENTF_UNICODE | KEYEVENTF_KEYUP))
        self._dispatch_inputs(inputs)

    def _inject_via_clipboard(self, text: str) -> None:
        logger.info("Injecting text via clipboard fallback ({} chars)", len(text))
        previous_text: str | None = None
        had_previous_text = False

        win32clipboard.OpenClipboard()
        try:
            if win32clipboard.IsClipboardFormatAvailable(CF_UNICODETEXT):
                previous_text = win32clipboard.GetClipboardData(CF_UNICODETEXT)
                had_previous_text = True
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(text, CF_UNICODETEXT)
        finally:
            win32clipboard.CloseClipboard()

        self._send_virtual_key_combo(VK_CONTROL, VK_V)
        time.sleep(0.05)

        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            if had_previous_text and previous_text is not None:
                win32clipboard.SetClipboardText(previous_text, CF_UNICODETEXT)
        finally:
            win32clipboard.CloseClipboard()

    def _send_virtual_key_combo(self, modifier_vk: int, key_vk: int) -> None:
        logger.info("Sending key combo via win32api: {} + {}", modifier_vk, key_vk)
        win32api.keybd_event(modifier_vk, 0, 0, 0)
        win32api.keybd_event(key_vk, 0, 0, 0)
        win32api.keybd_event(key_vk, 0, win32con.KEYEVENTF_KEYUP, 0)
        win32api.keybd_event(modifier_vk, 0, win32con.KEYEVENTF_KEYUP, 0)

    def _dispatch_inputs(self, inputs: list[INPUT]) -> None:
        if not inputs:
            return

        array = (INPUT * len(inputs))(*inputs)
        ctypes.set_last_error(0)
        sent = self._send_input(len(inputs), array, ctypes.sizeof(INPUT))
        if sent != len(inputs):
            error_code = ctypes.get_last_error()
            raise OSError(error_code, f"SendInput sent {sent}/{len(inputs)} events")

    def _keyboard_input(self, vk: int, scan: int, flags: int) -> INPUT:
        return INPUT(
            type=INPUT_KEYBOARD,
            union=INPUTUNION(
                ki=KEYBDINPUT(
                    wVk=vk,
                    wScan=scan,
                    dwFlags=flags,
                    time=0,
                    dwExtraInfo=0,
                )
            ),
        )
