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
    _class_registered = False

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

    def __init__(self, settings: OverlaySettings) -> None:
        super().__init__()
        self._settings = settings
        self._tick = 0
        self._hwnd: int | None = None
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

    def _animate(self) -> None:
        self._tick += 1
        self._redraw()

    def _redraw(self) -> None:
        if self._hwnd is None:
            return

        size = self._current_size()
        x, y = self._target_position(size)
        pixel_data = self._render_circle_rgba(size)

        screen_dc = self._user32.GetDC(0)
        mem_dc = self._gdi32.CreateCompatibleDC(screen_dc)
        bits = ctypes.c_void_p()

        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = size
        bmi.bmiHeader.biHeight = -size
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = 0

        hbitmap = self._gdi32.CreateDIBSection(mem_dc, ctypes.byref(bmi), 0, ctypes.byref(bits), 0, 0)
        old_bitmap = self._gdi32.SelectObject(mem_dc, hbitmap)

        ctypes.memmove(bits, pixel_data, len(pixel_data))

        src_pt = POINT(0, 0)
        dst_pt = POINT(x, y)
        win_size = SIZE(size, size)
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

    def _target_position(self, size: int) -> tuple[int, int]:
        screen = QApplication.primaryScreen()
        if screen is None:
            return (0, 0)
        available = screen.availableGeometry()
        x = available.x() + (available.width() - size) // 2
        y = available.y() + available.height() - size - 48
        return (x, y)


def _filled_circle_alpha(distance: float, radius: float, feather: float, peak_alpha: int) -> int:
    if distance <= radius - feather:
        return peak_alpha
    if distance >= radius + feather:
        return 0

    t = (distance - (radius - feather)) / (2 * feather)
    alpha = 1.0 - t
    return max(0, min(peak_alpha, int(alpha * peak_alpha)))
