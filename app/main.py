from __future__ import annotations

from datetime import datetime

import numpy as np
from loguru import logger
from PyQt6.QtWidgets import QApplication
from scipy.io import wavfile

from app import __version__
from app.config import ROOT_DIR, load_config
from app.core.hotkey import GlobalHotkey
from app.core.injector import TextInjector
from app.core.pipeline import Pipeline
from app.core.recorder import AudioRecorder
from app.events import EventBus
from app.models import Transcript
from app.ui.config_window import ConfigWindow
from app.ui.overlay import RecordingOverlay
from app.ui.qt_bridge import QtEventBridge
from app.ui.tray import TrayController
from app.utils.logging import setup_logging
from app.utils.runtime import configure_runtime_paths


def save_recording(payload: dict) -> None:
    audio = payload["audio"]
    sample_rate = payload["sample_rate"]
    duration = payload["duration"]
    recordings_dir = ROOT_DIR / "recordings"
    recordings_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = recordings_dir / f"{timestamp}.wav"
    wav_audio = np.clip(audio, -1.0, 1.0)
    wavfile.write(path, sample_rate, (wav_audio * 32767).astype(np.int16))
    logger.info("Saved recording to {} ({:.2f}s)", path, duration)


def print_transcript(payload: dict) -> None:
    transcript: Transcript = payload["transcript"]
    language = transcript.language or "unknown"
    confidence = transcript.language_confidence
    confidence_text = f"{confidence:.2f}" if confidence is not None else "n/a"

    logger.info(
        "Transcript ready: language={} confidence={} duration={:.2f}s",
        language,
        confidence_text,
        transcript.duration,
    )
    print(f"[{language} {confidence_text}] {transcript.text}", flush=True)


class ApplicationController:
    def __init__(self, app: QApplication) -> None:
        self._app = app
        self._config = load_config()
        setup_logging(self._config.logging)
        configure_runtime_paths(self._config.runtime)

        self._event_bus = EventBus()
        self._bridge = QtEventBridge()
        self._recorder = AudioRecorder(self._event_bus, self._config.audio)
        self._pipeline = Pipeline(self._event_bus, self._config.stt)
        self._injector = TextInjector(self._event_bus, self._config.injection)
        self._hotkey = GlobalHotkey(self._event_bus, self._config.hotkey.combo)
        self._overlay = RecordingOverlay(self._config.overlay)
        self._config_window = ConfigWindow()
        self._tray = TrayController(ROOT_DIR / "assets" / "icon.png")
        self._paused = False

        self._wire_events()

    def start(self) -> None:
        print(f"{self._config.app.name} v{__version__} - config cargada desde {self._config._config_path}", flush=True)
        self._tray.show()
        self._hotkey.start()
        self._pipeline.warmup_async()
        logger.info("Application ready. Hold {} to record", self._config.hotkey.combo)

    def shutdown(self) -> None:
        self._tray.hide()
        self._overlay.hide_overlay()
        self._hotkey.stop()
        self._recorder.shutdown()
        self._pipeline.shutdown()

    def _wire_events(self) -> None:
        self._recorder.attach()
        self._pipeline.attach()
        self._injector.attach()

        self._event_bus.subscribe("RECORDING_STARTED", lambda payload: logger.info("Recording started at {} Hz", payload["sample_rate"]))
        self._event_bus.subscribe("RECORDING_STARTED", lambda payload: self._bridge.recording_started.emit())
        self._event_bus.subscribe("RECORDING_STOPPED", save_recording)
        self._event_bus.subscribe("RECORDING_STOPPED", lambda payload: self._bridge.transcript_ready.emit())
        self._event_bus.subscribe("TRANSCRIPT_READY", print_transcript)
        self._event_bus.subscribe("TRANSCRIPT_READY", lambda payload: self._bridge.transcript_ready.emit())

        self._bridge.recording_started.connect(self._overlay.show_recording)
        self._bridge.transcript_ready.connect(self._overlay.hide_overlay)

        self._tray.pause_toggled.connect(self._set_paused)
        self._tray.open_config_requested.connect(self._show_config_window)
        self._tray.exit_requested.connect(self._app.quit)
        self._app.aboutToQuit.connect(self.shutdown)

    def _set_paused(self, paused: bool) -> None:
        self._paused = paused
        self._tray.set_paused(paused)
        self._hotkey.set_enabled(not paused)
        logger.info("Application paused={}", paused)
        if paused:
            self._overlay.hide_overlay()

    def _show_config_window(self) -> None:
        self._config_window.show()
        self._config_window.raise_()
        self._config_window.activateWindow()


def main() -> None:
    qt_app = QApplication([])
    qt_app.setQuitOnLastWindowClosed(False)
    controller = ApplicationController(qt_app)
    controller.start()
    qt_app.exec()


if __name__ == "__main__":
    main()
