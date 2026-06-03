from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal


class QtEventBridge(QObject):
    recording_started = pyqtSignal()
    transcript_ready = pyqtSignal()
    pause_changed = pyqtSignal(bool)
    language_changed = pyqtSignal(str)
    audio_level_changed = pyqtSignal(float)
    llm_status_changed = pyqtSignal(str)
    llm_debug_event = pyqtSignal(object)
