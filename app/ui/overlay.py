from __future__ import annotations

from math import sin

from PyQt6.QtCore import QPoint, QRect, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QWidget

from app.config import OverlaySettings


class RecordingOverlay(QWidget):
    def __init__(self, settings: OverlaySettings) -> None:
        super().__init__()
        self._settings = settings
        self._tick = 0
        self._timer = QTimer(self)
        self._timer.setInterval(32)
        self._timer.timeout.connect(self._animate)

        self.setFixedSize(112, 112)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.hide()

    def show_recording(self) -> None:
        if not self._settings.enabled:
            return
        self._reposition()
        self._tick = 0
        self._timer.start()
        self.show()
        self.raise_()

    def hide_overlay(self) -> None:
        self._timer.stop()
        self.hide()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pulse = 1.0 + 0.08 * sin(self._tick / 4)
        outer_radius = int(24 * pulse)
        center = self.rect().center()

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(200, 32, 32, 70))
        painter.drawEllipse(center, outer_radius + 12, outer_radius + 12)

        painter.setBrush(QColor(225, 48, 48))
        painter.drawEllipse(center, outer_radius, outer_radius)

        painter.setPen(QPen(QColor(255, 255, 255), 2))
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        text_rect = QRect(0, center.y() + outer_radius + 8, self.width(), 22)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, "REC")

    def _animate(self) -> None:
        self._tick += 1
        self.update()

    def _reposition(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        if self._settings.position == "bottom-center":
            x = available.x() + (available.width() - self.width()) // 2
            y = available.y() + available.height() - self.height() - 48
        else:
            x = available.x() + (available.width() - self.width()) // 2
            y = available.y() + available.height() - self.height() - 48
        self.move(QPoint(x, y))
