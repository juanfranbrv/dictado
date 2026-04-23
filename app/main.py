from __future__ import annotations

import argparse
import threading
from datetime import datetime

import numpy as np
from loguru import logger
from PyQt6.QtCore import QFileSystemWatcher, QTimer, Qt
from PyQt6.QtWidgets import QApplication, QMessageBox, QProgressDialog
from scipy.io import wavfile

from app import __version__
from app.config import Config, ROOT_DIR, load_config, save_config
from app.core.hotkey import GlobalHotkey, TriggerHotkey
from app.core.injector import TextInjector
from app.core.language import LanguageHysteresis
from app.core.pipeline import Pipeline
from app.core.recorder import AudioRecorder
from app.events import EventBus
from app.models import Transcript
from app.ui.config_window import ConfigWindow
from app.ui.overlay import RecordingOverlay
from app.ui.qt_bridge import QtEventBridge
from app.ui.tray import TrayController
from app.utils.audio_devices import list_input_devices
from app.utils.hardware import (
    capture_hardware_snapshot,
    ensure_builtin_profiles,
    recommend_profile,
    summarize_snapshot,
)
from app.utils.logging import setup_logging
from app.utils.paths import recordings_dir
from app.utils.timing import TimingCollector
from app.utils.runtime import configure_runtime_paths
from app.utils.whisper_models import download_whisper_model, is_whisper_model_available


def save_recording(payload: dict) -> None:
    audio = payload["audio"]
    sample_rate = payload["sample_rate"]
    duration = payload["duration"]
    target_dir = recordings_dir()

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = target_dir / f"{timestamp}.wav"
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
        self._config = self._apply_initial_hardware_profile(self._config)
        setup_logging(self._config.logging)
        configure_runtime_paths(self._config.runtime)

        self._event_bus = EventBus()
        self._bridge = QtEventBridge()
        self._language = LanguageHysteresis(self._config.language)
        self._recorder = AudioRecorder(self._event_bus, self._config.audio)
        self._pipeline = Pipeline(
            self._event_bus,
            self._config.stt,
            self._language,
            self._config.profiles,
            self._config.app.active_profile,
        )
        self._injector = TextInjector(self._event_bus, self._config.injection)
        self._hotkey = GlobalHotkey(self._event_bus, self._config.hotkey.combo)
        self._force_es_hotkey = TriggerHotkey(self._event_bus, self._config.hotkey.force_language_es, "FORCE_LANGUAGE_ES")
        self._force_en_hotkey = TriggerHotkey(self._event_bus, self._config.hotkey.force_language_en, "FORCE_LANGUAGE_EN")
        self._overlay = RecordingOverlay(self._config.overlay)
        self._config_window = ConfigWindow(self._config)
        self._tray = TrayController(ROOT_DIR / "assets" / "mic-vocal.png")
        self._timings = TimingCollector()
        self._config_watcher = QFileSystemWatcher()
        if self._config._config_path is not None:
            self._config_watcher.addPath(str(self._config._config_path))
        self._paused = False

        self._wire_events()

    def _apply_initial_hardware_profile(self, config: Config) -> Config:
        profiles = ensure_builtin_profiles(config.profiles)
        config_with_profiles = config.model_copy(update={"profiles": profiles})

        if config.app.hardware_profile_initialized:
            return config_with_profiles

        snapshot = capture_hardware_snapshot()
        recommendation = recommend_profile(snapshot)
        selected_profile = recommendation.profile_name if recommendation.profile_name in profiles else "default"
        logger.info(
            "Initial hardware tuning selected profile {} ({}) from {}",
            selected_profile,
            recommendation.reason,
            summarize_snapshot(snapshot),
        )
        app_settings = config_with_profiles.app.model_copy(
            update={
                "active_profile": selected_profile,
                "hardware_profile_initialized": True,
            }
        )
        tuned = config_with_profiles.model_copy(update={"app": app_settings, "profiles": profiles})
        tuned._config_path = config._config_path
        save_config(tuned)
        return tuned

    def start(self) -> None:
        print(f"{self._config.app.name} v{__version__} - config cargada desde {self._config._config_path}", flush=True)
        self._ensure_active_profile_model_ready()
        self._tray.show()
        self._tray.set_profiles(self._pipeline.list_profiles(), self._pipeline.active_profile)
        self._hotkey.start()
        self._force_es_hotkey.start()
        self._force_en_hotkey.start()
        self._pipeline.warmup_async()
        logger.info("Application ready. Hold {} to record", self._config.hotkey.combo)
        self._bridge.language_changed.emit(self._language.active_language)

    def shutdown(self) -> None:
        self._tray.hide()
        self._overlay.hide_overlay()
        self._hotkey.stop()
        self._force_es_hotkey.stop()
        self._force_en_hotkey.stop()
        self._recorder.shutdown()
        self._pipeline.shutdown()

    def _wire_events(self) -> None:
        self._recorder.attach()
        self._pipeline.attach()
        self._injector.attach()

        self._event_bus.subscribe(
            "RECORDING_STARTED",
            lambda payload: logger.info(
                "Recording started at {} Hz using {}",
                payload["sample_rate"],
                payload.get("device", "default"),
            ),
        )
        self._event_bus.subscribe("RECORDING_STARTED", lambda payload: self._bridge.recording_started.emit())
        self._event_bus.subscribe("RECORDING_STOPPED", save_recording)
        self._event_bus.subscribe("RECORDING_STOPPED", lambda payload: self._bridge.transcript_ready.emit())
        self._event_bus.subscribe("TRANSCRIPT_READY", print_transcript)
        self._event_bus.subscribe("TRANSCRIPT_READY", lambda payload: self._bridge.transcript_ready.emit())
        self._event_bus.subscribe("LANGUAGE_CHANGED", lambda payload: self._bridge.language_changed.emit(payload["language"]))
        self._event_bus.subscribe("PROFILE_CHANGED", lambda payload: self._tray.set_active_profile(payload["profile"]))
        self._event_bus.subscribe("TIMING", self._handle_timing_event)
        self._bridge.recording_started.connect(self._overlay.show_recording)
        self._bridge.transcript_ready.connect(self._overlay.hide_overlay)
        self._bridge.language_changed.connect(self._overlay.set_language)

        self._tray.pause_toggled.connect(self._set_paused)
        self._tray.profile_selected.connect(self._select_profile)
        self._tray.open_config_requested.connect(self._show_config_window)
        self._tray.exit_requested.connect(self._app.quit)
        self._config_window.config_saved.connect(self._apply_config)
        self._config_watcher.fileChanged.connect(lambda path: QTimer.singleShot(150, self._reload_config_from_disk))
        self._app.aboutToQuit.connect(self.shutdown)

    def _set_paused(self, paused: bool) -> None:
        self._paused = paused
        self._tray.set_paused(paused)
        self._hotkey.set_enabled(not paused)
        self._force_es_hotkey.set_enabled(not paused)
        self._force_en_hotkey.set_enabled(not paused)
        logger.info("Application paused={}", paused)
        if paused:
            self._overlay.hide_overlay()

    def _show_config_window(self) -> None:
        self._config_window.show()
        self._config_window.raise_()
        self._config_window.activateWindow()

    def _select_profile(self, profile_name: str) -> None:
        logger.info("Profile selected from tray: {}", profile_name)
        app_settings = self._config.app.model_copy(update={"active_profile": profile_name})
        self._config = self._config.model_copy(update={"app": app_settings})
        save_config(self._config)
        self._config_window.load_config(self._config)
        self._ensure_profile_model_ready(profile_name)
        self._event_bus.publish("SWITCH_PROFILE", {"profile": profile_name})

    def _apply_config(self, config: Config) -> None:
        self._config = config
        self._ensure_active_profile_model_ready()
        self._recorder.update_settings(config.audio)
        self._pipeline.reconfigure(config.profiles, config.app.active_profile)
        self._injector.update_settings(config.injection)
        self._overlay.update_settings(config.overlay)
        self._tray.set_profiles(self._pipeline.list_profiles(), self._pipeline.active_profile)

    def _reload_config_from_disk(self) -> None:
        try:
            config = load_config()
        except Exception as exc:
            logger.warning("Ignoring invalid config reload: {}", exc)
            return

        logger.info("Reloaded config from disk")
        self._config_window.load_config(config)
        self._apply_config(config)
        if config._config_path is not None and not self._config_watcher.files():
            self._config_watcher.addPath(str(config._config_path))

    def _handle_timing_event(self, payload: dict) -> None:
        session_id = int(payload.get("session_id", 0))
        if session_id <= 0:
            return
        self._timings.set_stage(session_id, str(payload["stage"]), float(payload["seconds"]))
        if payload.get("stage") == "inject":
            self._timings.log_summary(
                session_id,
                str(payload.get("profile", self._pipeline.active_profile)),
                str(payload.get("source", "")),
            )

    def _ensure_active_profile_model_ready(self) -> None:
        self._ensure_profile_model_ready(self._config.app.active_profile)

    def _ensure_profile_model_ready(self, profile_name: str) -> None:
        profile = self._config.profiles.get(profile_name)
        if profile is None:
            return
        if profile.stt_provider != "faster-whisper":
            return

        model_name = str(profile.stt_config.get("model", self._config.stt.model)).strip()
        local_only = bool(profile.stt_config.get("local_files_only", self._config.stt.local_files_only))
        if not model_name or not local_only:
            return
        if is_whisper_model_available(model_name):
            return

        title = "Modelo Whisper no disponible"
        message = (
            f"El perfil `{profile_name}` necesita el modelo Whisper `{model_name}`, pero ahora mismo no está disponible o está dañado.\n\n"
            "¿Quieres descargarlo o repararlo ahora?"
        )
        reply = QMessageBox.question(
            None,
            title,
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            logger.warning("Whisper model {} is missing and the user declined download", model_name)
            return

        try:
            target = self._download_model_with_dialog(profile_name, model_name)
        except Exception as exc:
            logger.warning("Unable to download Whisper model {}: {}", model_name, exc)
            QMessageBox.warning(
                None,
                "Descarga o reparación fallida",
                f"No se pudo descargar o reparar el modelo `{model_name}`.\n\n{exc}",
            )
        else:
            logger.info("Whisper model {} downloaded to {}", model_name, target)
            QMessageBox.information(
                None,
                "Modelo descargado",
                f"El modelo `{model_name}` ya está disponible.",
            )

    def _download_model_with_dialog(self, profile_name: str, model_name: str) -> str:
        dialog = QProgressDialog(
            (
                f"Preparando el perfil `{profile_name}`.\n\n"
                f"Se esta descargando o reparando el modelo Whisper `{model_name}`.\n\n"
                "El dictado quedara bloqueado hasta que termine este proceso."
            ),
            "",
            0,
            0,
            None,
        )
        dialog.setWindowTitle("Descargando modelo Whisper")
        dialog.setCancelButton(None)
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        dialog.setMinimumDuration(0)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)
        dialog.setMinimumWidth(420)
        dialog.setValue(0)
        dialog.show()
        self._app.processEvents()

        result: dict[str, object] = {}

        def _worker() -> None:
            try:
                result["target"] = download_whisper_model(model_name)
            except Exception as exc:  # pragma: no cover - UI error path
                result["error"] = exc

        thread = threading.Thread(target=_worker, name="whisper-model-download", daemon=True)
        thread.start()

        while thread.is_alive():
            self._app.processEvents()
            thread.join(0.05)

        dialog.close()
        self._app.processEvents()

        error = result.get("error")
        if error is not None:
            raise error  # type: ignore[misc]
        target = result.get("target")
        if not isinstance(target, str):
            raise RuntimeError(f"La descarga del modelo `{model_name}` no devolvio ninguna ruta valida.")
        return target

def main() -> None:
    args = _parse_args()
    if args.version:
        print(__version__)
        return
    if args.print_config_path:
        config = load_config()
        print(config._config_path)
        return
    if args.list_audio_devices:
        _print_audio_devices()
        return

    qt_app = QApplication([])
    qt_app.setQuitOnLastWindowClosed(False)
    controller = ApplicationController(qt_app)
    controller.start()
    qt_app.exec()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="dictado")
    parser.add_argument("--version", action="store_true", help="Muestra la version y sale.")
    parser.add_argument(
        "--print-config-path",
        action="store_true",
        help="Muestra la ruta del config.toml activo y sale.",
    )
    parser.add_argument(
        "--list-audio-devices",
        action="store_true",
        help="Lista los dispositivos de entrada disponibles y sale.",
    )
    return parser.parse_args()


def _print_audio_devices() -> None:
    try:
        config = load_config()
    except Exception:
        config = None

    configured_device = ""
    if config is not None:
        configured_device = config.audio.device.strip()
        print(f"config_path={config._config_path}")
        print(f"configured_input={configured_device or 'system-default'}")

    devices = list_input_devices()
    if not devices:
        print("No input devices found.")
        return

    print("input_devices:")
    for device in devices:
        configured_marker = ""
        if configured_device and (configured_device == device.label or configured_device == device.name):
            configured_marker = " [configured]"
        print(f"- {device.index}: {device.label}{configured_marker}")


if __name__ == "__main__":
    main()
