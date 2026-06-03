from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np

from app.config import OverlaySettings
from app.ui import overlay
from app.ui.overlay import RecordingOverlay


class FakeTimer:
    def __init__(self) -> None:
        self.started = False

    def start(self) -> None:
        self.started = True


def _overlay_instance() -> RecordingOverlay:
    instance = RecordingOverlay.__new__(RecordingOverlay)
    instance._settings = OverlaySettings(enabled=True)
    instance._timer = FakeTimer()
    instance._tick = 0
    instance._hwnd = 123
    instance._audio_levels = [0.0] * 64
    return instance


class RecordingOverlayTopmostTests(unittest.TestCase):
    def test_show_recording_reasserts_topmost_without_activating(self) -> None:
        instance = _overlay_instance()
        calls = []

        with (
            patch.object(RecordingOverlay, "_redraw", lambda self: calls.append(("redraw",))),
            patch.object(overlay.win32gui, "ShowWindow", lambda hwnd, flag: calls.append(("show", hwnd, flag))),
            patch.object(
                overlay.win32gui,
                "SetWindowPos",
                lambda hwnd, insert_after, x, y, cx, cy, flags: calls.append(
                    ("setpos", hwnd, insert_after, x, y, cx, cy, flags)
                ),
            ),
        ):
            instance.show_recording()

        self.assertTrue(instance._timer.started)
        self.assertIn(("show", 123, overlay.win32con.SW_SHOWNOACTIVATE), calls)
        self.assertIn(_expected_setpos_call(), calls)


class RecordingOverlayStyleTests(unittest.TestCase):
    def test_default_style_keeps_red_circle_overlay(self) -> None:
        self.assertEqual(OverlaySettings().style, "red-circle")

    def test_waveform_render_responds_to_audio_level(self) -> None:
        instance = _overlay_instance()

        instance._audio_levels = [0.0] * 64
        silent = instance._render_waveform_rgba(160, 64)

        instance._audio_levels = [0.9] * 64
        loud = instance._render_waveform_rgba(160, 64)

        self.assertGreater(
            _max_waveform_height(loud, 160, 64),
            _max_waveform_height(silent, 160, 64),
        )

    def test_waveform_stays_flat_when_audio_is_flat(self) -> None:
        instance = _overlay_instance()
        instance._audio_levels = [0.0] * 64

        instance._tick = 0
        first = instance._render_waveform_rgba(120, 42)
        instance._tick = 8
        second = instance._render_waveform_rgba(120, 42)

        self.assertEqual(first, second)
        self.assertLessEqual(_waveform_height_variance(second, 120, 42), 1)

    def test_waveform_shape_reflects_volume_changes(self) -> None:
        instance = _overlay_instance()
        instance._audio_levels = ([0.0] * 16) + ([0.01] * 16) + ([0.08] * 16) + ([0.0] * 16)

        rendered = instance._render_waveform_rgba(120, 42)

        self.assertGreater(_waveform_height_variance(rendered, 120, 42), 12)
        self.assertLess(_white_pixel_count(rendered), 120 * 10)
        self.assertGreaterEqual(_visible_bar_count(rendered, 120, 42), 10)

    def test_waveform_has_rounded_transparent_corners(self) -> None:
        instance = _overlay_instance()
        instance._audio_levels = [0.0] * 64

        rendered = instance._render_waveform_rgba(120, 42)
        pixels = np.frombuffer(rendered, dtype=np.uint8).reshape((42, 120, 4))

        self.assertEqual(int(pixels[0, 0, 3]), 0)
        self.assertGreater(int(pixels[21, 60, 3]), 0)

    def test_waveform_bars_are_rounded(self) -> None:
        instance = _overlay_instance()
        instance._audio_levels = [0.08] * 64

        rendered = instance._render_waveform_rgba(120, 42)
        pixels = np.frombuffer(rendered, dtype=np.uint8).reshape((42, 120, 4))
        bar_columns = np.nonzero(
            (pixels[:, :, 0] >= 245)
            & (pixels[:, :, 1] >= 245)
            & (pixels[:, :, 2] >= 245)
        )[1]
        left = int(bar_columns.min())

        self.assertFalse(_is_white_pixel(pixels[1, left]))
        self.assertTrue(_is_white_pixel(pixels[21, left]))

    def test_waveform_bars_are_centered_in_container(self) -> None:
        instance = _overlay_instance()
        instance._audio_levels = [0.08] * 64

        rendered = instance._render_waveform_rgba(120, 42)
        pixels = np.frombuffer(rendered, dtype=np.uint8).reshape((42, 120, 4))
        white_columns = np.nonzero(
            (pixels[:, :, 0] >= 245)
            & (pixels[:, :, 1] >= 245)
            & (pixels[:, :, 2] >= 245)
        )[1]

        left_margin = int(white_columns.min())
        right_margin = 119 - int(white_columns.max())

        self.assertLessEqual(abs(left_margin - right_margin), 1)

    def test_animation_tick_reasserts_topmost_without_activating(self) -> None:
        instance = _overlay_instance()
        calls = []

        with (
            patch.object(RecordingOverlay, "_redraw", lambda self: calls.append(("redraw", self._tick))),
            patch.object(
                overlay.win32gui,
                "SetWindowPos",
                lambda hwnd, insert_after, x, y, cx, cy, flags: calls.append(
                    ("setpos", hwnd, insert_after, x, y, cx, cy, flags)
                ),
            ),
        ):
            instance._animate()

        self.assertIn(("redraw", 1), calls)
        self.assertIn(_expected_setpos_call(), calls)


def _expected_setpos_call() -> tuple[int | str, ...]:
    return (
        "setpos",
        123,
        overlay.win32con.HWND_TOPMOST,
        0,
        0,
        0,
        0,
        overlay.win32con.SWP_NOMOVE
        | overlay.win32con.SWP_NOSIZE
        | overlay.win32con.SWP_NOACTIVATE
        | overlay.win32con.SWP_SHOWWINDOW,
    )


def _white_pixel_count(data: bytes) -> int:
    pixels = np.frombuffer(data, dtype=np.uint8).reshape((-1, 4))
    return int(np.count_nonzero((pixels[:, 0] >= 245) & (pixels[:, 1] >= 245) & (pixels[:, 2] >= 245)))


def _is_white_pixel(pixel: np.ndarray) -> bool:
    return bool((pixel[0] >= 245) and (pixel[1] >= 245) and (pixel[2] >= 245))


def _waveform_height_variance(data: bytes, width: int, height: int) -> int:
    pixels = np.frombuffer(data, dtype=np.uint8).reshape((height, width, 4))
    heights = []
    for x in range(width):
        white_rows = np.nonzero(
            (pixels[:, x, 0] >= 245)
            & (pixels[:, x, 1] >= 245)
            & (pixels[:, x, 2] >= 245)
        )[0]
        if white_rows.size:
            heights.append(int(white_rows[-1] - white_rows[0] + 1))
    return (max(heights) - min(heights)) if heights else 0


def _max_waveform_height(data: bytes, width: int, height: int) -> int:
    pixels = np.frombuffer(data, dtype=np.uint8).reshape((height, width, 4))
    max_height = 0
    for x in range(width):
        white_rows = np.nonzero(
            (pixels[:, x, 0] >= 245)
            & (pixels[:, x, 1] >= 245)
            & (pixels[:, x, 2] >= 245)
        )[0]
        if white_rows.size:
            max_height = max(max_height, int(white_rows[-1] - white_rows[0] + 1))
    return max_height


def _visible_bar_count(data: bytes, width: int, height: int) -> int:
    pixels = np.frombuffer(data, dtype=np.uint8).reshape((height, width, 4))
    columns = []
    for x in range(width):
        white_rows = np.nonzero(
            (pixels[:, x, 0] == 245)
            & (pixels[:, x, 1] == 245)
            & (pixels[:, x, 2] == 245)
        )[0]
        columns.append(bool(white_rows.size))

    bars = 0
    previous = False
    for visible in columns:
        if visible and not previous:
            bars += 1
        previous = visible
    return bars
