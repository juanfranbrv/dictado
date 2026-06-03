from __future__ import annotations

import ctypes
from math import sin, sqrt

import win32api
import win32con
import win32gui
from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtWidgets import QApplication

from app.config import OverlaySettings


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class SIZE(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", ctypes.c_byte),
        ("BlendFlags", ctypes.c_byte),
        ("SourceConstantAlpha", ctypes.c_byte),
        ("AlphaFormat", ctypes.c_byte),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.c_uint32),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", ctypes.c_ushort),
        ("biBitCount", ctypes.c_ushort),
        ("biCompression", ctypes.c_uint32),
        ("biSizeImage", ctypes.c_uint32),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", ctypes.c_uint32),
        ("biClrImportant", ctypes.c_uint32),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", ctypes.c_uint32 * 3)]


class RecordingOverlay(QObject):
    _CLASS_NAME = "DictadoRecordingOverlayLayered"
    _BASE_SIZE = 72
    _PULSE_RANGE = 10
    _WAVEFORM_WIDTH = 120
    _WAVEFORM_HEIGHT = 42
    _WAVEFORM_SAMPLES = 64
    _WAVEFORM_RADIUS = 11
    _WAVEFORM_BARS = 13
    _WAVEFORM_BAR_WIDTH = 4
    _TOPMOST_FLAGS = (
        win32con.SWP_NOMOVE
        | win32con.SWP_NOSIZE
        | win32con.SWP_NOACTIVATE
        | win32con.SWP_SHOWWINDOW
    )
    _class_registered = False

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

    def __init__(self, settings: OverlaySettings) -> None:
        super().__init__()
        self._settings = settings
        self._tick = 0
        self._hwnd: int | None = None
        self._audio_levels = [0.0] * self._WAVEFORM_SAMPLES
        self._timer = QTimer(self)
        self._timer.setInterval(32)
        self._timer.timeout.connect(self._animate)
        self._register_class()
        self._create_window()

    def show_recording(self) -> None:
        if not self._settings.enabled:
            return
        self._tick = 0
        self._timer.start()
        self._redraw()
        if self._hwnd is not None:
            win32gui.ShowWindow(self._hwnd, win32con.SW_SHOWNOACTIVATE)
            self._ensure_topmost()

    def hide_overlay(self) -> None:
        self._timer.stop()
        if self._hwnd is not None:
            win32gui.ShowWindow(self._hwnd, win32con.SW_HIDE)

    def update_settings(self, settings: OverlaySettings) -> None:
        self._settings = settings
        if not settings.enabled:
            self.hide_overlay()

    def set_language(self, language: str) -> None:
        del language

    def set_audio_level(self, level: float) -> None:
        bounded = max(0.0, min(float(level), 1.0))
        self._audio_levels.append(bounded)
        if len(self._audio_levels) > self._WAVEFORM_SAMPLES:
            self._audio_levels = self._audio_levels[-self._WAVEFORM_SAMPLES :]

    def _animate(self) -> None:
        self._tick += 1
        self._redraw()
        self._ensure_topmost()

    def _redraw(self) -> None:
        if self._hwnd is None:
            return

        width, height = self._current_dimensions()
        x, y = self._target_position(width, height)
        if self._settings.style == "waveform":
            pixel_data = self._render_waveform_rgba(width, height)
        else:
            pixel_data = self._render_circle_rgba(width)

        screen_dc = self._user32.GetDC(0)
        mem_dc = self._gdi32.CreateCompatibleDC(screen_dc)
        bits = ctypes.c_void_p()

        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = width
        bmi.bmiHeader.biHeight = -height
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = 0

        hbitmap = self._gdi32.CreateDIBSection(mem_dc, ctypes.byref(bmi), 0, ctypes.byref(bits), 0, 0)
        old_bitmap = self._gdi32.SelectObject(mem_dc, hbitmap)

        ctypes.memmove(bits, pixel_data, len(pixel_data))

        src_pt = POINT(0, 0)
        dst_pt = POINT(x, y)
        win_size = SIZE(width, height)
        blend = BLENDFUNCTION(0, 0, 255, win32con.AC_SRC_ALPHA)

        self._user32.UpdateLayeredWindow(
            self._hwnd,
            screen_dc,
            ctypes.byref(dst_pt),
            ctypes.byref(win_size),
            mem_dc,
            ctypes.byref(src_pt),
            0,
            ctypes.byref(blend),
            win32con.ULW_ALPHA,
        )

        self._gdi32.SelectObject(mem_dc, old_bitmap)
        self._gdi32.DeleteObject(hbitmap)
        self._gdi32.DeleteDC(mem_dc)
        self._user32.ReleaseDC(0, screen_dc)

    def _current_dimensions(self) -> tuple[int, int]:
        if self._settings.style == "waveform":
            return self._WAVEFORM_WIDTH, self._WAVEFORM_HEIGHT
        size = self._current_size()
        return size, size

    def _current_size(self) -> int:
        pulse = (sin(self._tick / 5) + 1.0) / 2.0
        return self._BASE_SIZE + int(self._PULSE_RANGE * pulse)

    def _render_circle_rgba(self, size: int) -> bytes:
        pulse = (sin(self._tick / 5) + 1.0) / 2.0
        core_radius = (size * 0.23) + (size * 0.03 * pulse)
        ring_1 = size * 0.34
        ring_2 = size * 0.43
        ring_3 = size * 0.50
        cx = (size - 1) / 2.0
        cy = (size - 1) / 2.0
        red, green, blue = 228, 52, 47

        data = bytearray(size * size * 4)
        offset = 0
        for y in range(size):
            for x in range(size):
                dx = x - cx
                dy = y - cy
                distance = sqrt((dx * dx) + (dy * dy))
                alpha = 0

                alpha = max(alpha, _filled_circle_alpha(distance, core_radius, 1.6, 255))
                alpha = max(alpha, _filled_circle_alpha(distance, ring_1, 2.2, int(80 + 30 * pulse)))
                alpha = max(alpha, _filled_circle_alpha(distance, ring_2, 2.8, int(44 + 18 * pulse)))
                alpha = max(alpha, _filled_circle_alpha(distance, ring_3, 3.4, int(20 + 10 * pulse)))

                if alpha <= 0:
                    data[offset + 0] = 0
                    data[offset + 1] = 0
                    data[offset + 2] = 0
                    data[offset + 3] = 0
                else:
                    data[offset + 0] = (blue * alpha) // 255
                    data[offset + 1] = (green * alpha) // 255
                    data[offset + 2] = (red * alpha) // 255
                    data[offset + 3] = alpha
                offset += 4
        return bytes(data)

    def _render_waveform_rgba(self, width: int, height: int) -> bytes:
        data = bytearray(width * height * 4)
        self._paint_rounded_background(data, width, height)

        center_y = height // 2
        usable_half_height = max(1, (height // 2) - 3)
        levels = self._audio_levels or [0.0]

        bar_width = self._WAVEFORM_BAR_WIDTH
        gap = max(2, (width - (self._WAVEFORM_BARS * bar_width)) // (self._WAVEFORM_BARS + 1))
        bars_width = (self._WAVEFORM_BARS * bar_width) + ((self._WAVEFORM_BARS - 1) * gap)
        start_x = max(0, (width - bars_width) // 2)
        for bar_index in range(self._WAVEFORM_BARS):
            level = _bucket_level(levels, bar_index, self._WAVEFORM_BARS)
            amplitude = _level_to_waveform_amplitude(level, usable_half_height)
            top = max(0, center_y - amplitude)
            bottom = min(height - 1, center_y + amplitude)
            x0 = start_x + (bar_index * (bar_width + gap))
            x1 = min(width - 1, x0 + bar_width - 1)
            _paint_bar(data, width, height, x0, x1, top, bottom)

        return bytes(data)

    def _paint_rounded_background(self, data: bytearray, width: int, height: int) -> None:
        radius = min(self._WAVEFORM_RADIUS, width // 2, height // 2)
        for y in range(height):
            for x in range(width):
                alpha = _rounded_rect_alpha(x, y, width, height, radius)
                if alpha > 0:
                    _write_premultiplied_pixel(data, width, x, y, 0, 0, 0, alpha)

    def _create_window(self) -> None:
        instance = win32api.GetModuleHandle(None)
        self._hwnd = win32gui.CreateWindowEx(
            win32con.WS_EX_LAYERED | win32con.WS_EX_TOPMOST | win32con.WS_EX_TOOLWINDOW | win32con.WS_EX_NOACTIVATE,
            self._CLASS_NAME,
            "",
            win32con.WS_POPUP,
            0,
            0,
            self._BASE_SIZE,
            self._BASE_SIZE,
            0,
            0,
            instance,
            None,
        )
        win32gui.ShowWindow(self._hwnd, win32con.SW_HIDE)

    def _ensure_topmost(self) -> None:
        if self._hwnd is None:
            return
        win32gui.SetWindowPos(self._hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, self._TOPMOST_FLAGS)

    @classmethod
    def _register_class(cls) -> None:
        if cls._class_registered:
            return

        instance = win32api.GetModuleHandle(None)
        wnd_class = win32gui.WNDCLASS()
        wnd_class.hInstance = instance
        wnd_class.lpszClassName = cls._CLASS_NAME
        wnd_class.lpfnWndProc = win32gui.DefWindowProc
        try:
            win32gui.RegisterClass(wnd_class)
        except win32gui.error:
            pass
        cls._class_registered = True

    def _target_position(self, width: int, height: int) -> tuple[int, int]:
        screen = QApplication.primaryScreen()
        if screen is None:
            return (0, 0)
        available = screen.availableGeometry()
        x = available.x() + (available.width() - width) // 2
        y = available.y() + available.height() - height - 48
        return (x, y)


def _filled_circle_alpha(distance: float, radius: float, feather: float, peak_alpha: int) -> int:
    if distance <= radius - feather:
        return peak_alpha
    if distance >= radius + feather:
        return 0

    t = (distance - (radius - feather)) / (2 * feather)
    alpha = 1.0 - t
    return max(0, min(peak_alpha, int(alpha * peak_alpha)))


def _write_premultiplied_pixel(
    data: bytearray,
    width: int,
    x: int,
    y: int,
    red: int,
    green: int,
    blue: int,
    alpha: int,
) -> None:
    offset = ((y * width) + x) * 4
    data[offset + 0] = (blue * alpha) // 255
    data[offset + 1] = (green * alpha) // 255
    data[offset + 2] = (red * alpha) // 255
    data[offset + 3] = alpha


def _level_to_waveform_amplitude(level: float, usable_half_height: int) -> int:
    noise_floor = 0.0018
    if level <= noise_floor:
        return 1
    normalized = min((level - noise_floor) * 32.0, 1.0)
    return max(2, int(sqrt(normalized) * usable_half_height))


def _rounded_rect_alpha(x: int, y: int, width: int, height: int, radius: int) -> int:
    background_alpha = 238
    feather = 1.2
    cx = min(max(x, radius), width - radius - 1)
    cy = min(max(y, radius), height - radius - 1)
    distance = sqrt(((x - cx) * (x - cx)) + ((y - cy) * (y - cy)))
    if distance <= radius - feather:
        return background_alpha
    if distance >= radius:
        return 0
    return int(background_alpha * (radius - distance) / feather)


def _write_waveform_pixel(data: bytearray, width: int, height: int, x: int, y: int, alpha: int) -> None:
    if x < 0 or x >= width or y < 0 or y >= height:
        return
    if _rounded_rect_alpha(x, y, width, height, RecordingOverlay._WAVEFORM_RADIUS) <= 0:
        return
    _write_premultiplied_pixel(data, width, x, y, 255, 255, 255, alpha)


def _bucket_level(levels: list[float], index: int, bucket_count: int) -> float:
    start = int((index / bucket_count) * len(levels))
    end = int(((index + 1) / bucket_count) * len(levels))
    bucket = levels[start : max(start + 1, end)]
    return max(bucket) if bucket else 0.0


def _paint_bar(data: bytearray, width: int, height: int, x0: int, x1: int, top: int, bottom: int) -> None:
    for x in range(x0, x1 + 1):
        for y in range(top, bottom + 1):
            alpha = _bar_capsule_alpha(x, y, x0, x1, top, bottom)
            if alpha <= 0:
                continue
            _write_waveform_pixel(data, width, height, x, y, alpha)


def _bar_capsule_alpha(x: int, y: int, x0: int, x1: int, top: int, bottom: int) -> int:
    left = float(x0)
    right = float(x1 + 1)
    top_edge = float(top)
    bottom_edge = float(bottom + 1)
    half_width = (right - left) / 2.0
    half_height = (bottom_edge - top_edge) / 2.0
    radius = max(1.0, min(half_width, half_height))
    center_x = left + half_width
    center_y = top_edge + half_height

    px = x + 0.5
    py = y + 0.5
    qx = abs(px - center_x) - half_width + radius
    qy = abs(py - center_y) - half_height + radius
    outside_x = max(qx, 0.0)
    outside_y = max(qy, 0.0)
    distance = sqrt((outside_x * outside_x) + (outside_y * outside_y)) + min(max(qx, qy), 0.0) - radius
    if distance <= -0.6:
        return 245
    if distance >= 0.0:
        return 0
    return max(0, min(245, int(245 * (-distance) / 0.6)))
