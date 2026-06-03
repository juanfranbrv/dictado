from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QPlainTextEdit, QVBoxLayout, QWidget

from app.config import DebugOverlaySettings


class DebugOverlay(QWidget):
    _MAX_LINES = 80
    _SEPARATOR = "-" * 72

    def __init__(self, settings: DebugOverlaySettings) -> None:
        super().__init__()
        self._settings = settings
        self._lines: list[str] = []

        self.setWindowTitle("dictado debug")
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.resize(860, 360)

        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setStyleSheet(
            """
            QPlainTextEdit {
                background: rgba(8, 8, 8, 235);
                color: #f2f2f2;
                border: 1px solid #444;
                font-family: Consolas, monospace;
                font-size: 18px;
                padding: 12px;
            }
            """
        )

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._text)
        self.setLayout(layout)

        self.update_settings(settings)

    def update_settings(self, settings: DebugOverlaySettings) -> None:
        self._settings = settings
        if settings.enabled:
            if not self.isVisible():
                self._ensure_initial_position()
            self.show()
            self.raise_()
        else:
            self.hide()

    def append_event(self, payload: dict) -> None:
        if not self._settings.enabled:
            return

        line = self._format_event(payload)
        self._lines.append(line)
        self._lines = self._lines[-self._MAX_LINES :]
        self._text.setPlainText(f"\n{self._SEPARATOR}\n".join(self._lines))
        scrollbar = self._text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        self.raise_()

    def _format_event(self, payload: dict) -> str:
        now = datetime.now().strftime("%H:%M:%S")
        session = payload.get("session_id", "-")
        provider = payload.get("provider", "-")
        model = payload.get("model", "-")
        status = payload.get("status", "-")
        duration = float(payload.get("duration", 0.0))
        error = str(payload.get("error", "")).strip()

        line = f"{now} s={session} {provider} | {model} | {status} | {duration:.2f}s"
        if error:
            line = f"{line} | {error}"
        return line

    def _ensure_initial_position(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        margin = 18
        x = available.x() + available.width() - self.width() - margin
        y = available.y() + margin
        self.move(x, y)
