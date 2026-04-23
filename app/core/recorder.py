from __future__ import annotations

from threading import Lock
from time import perf_counter
from typing import Any

import numpy as np
import sounddevice as sd
from loguru import logger

from app.config import AudioSettings
from app.events import EventBus
from app.utils.audio_devices import input_device_candidates


class AudioRecorder:
    """Capture microphone audio and publish start/stop events."""

    def __init__(self, event_bus: EventBus, settings: AudioSettings) -> None:
        self._event_bus = event_bus
        self._settings = settings
        self._lock = Lock()
        self._frames: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._is_recording = False
        self._started_at = 0.0

    def attach(self) -> None:
        self._event_bus.subscribe("START_RECORDING", self._handle_start)
        self._event_bus.subscribe("STOP_RECORDING", self._handle_stop)

    def shutdown(self) -> None:
        with self._lock:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
                self._stream = None
            self._is_recording = False
            self._frames.clear()

    def update_settings(self, settings: AudioSettings) -> None:
        with self._lock:
            self._settings = settings

    def _handle_start(self, _: dict[str, Any]) -> None:
        with self._lock:
            if not self._is_recording:
                try:
                    self._start_locked()
                except Exception as exc:
                    logger.error("Unable to start audio recording: {}", exc)

    def _handle_stop(self, _: dict[str, Any]) -> None:
        with self._lock:
            if self._is_recording:
                self._stop_locked()

    def _start_locked(self) -> None:
        logger.info("Starting audio recording")
        self._frames = []
        resolved_device = None
        resolved_reason = "system default"
        last_error: Exception | None = None
        for reason, candidate in input_device_candidates(self._settings.device):
            try:
                logger.info("Opening audio input via {}", reason)
                stream = sd.InputStream(
                    samplerate=self._settings.sample_rate,
                    channels=self._settings.channels,
                    dtype="float32",
                    blocksize=self._settings.blocksize,
                    callback=self._audio_callback,
                    device=candidate,
                )
                stream.start()
                self._stream = stream
                resolved_device = candidate
                resolved_reason = reason
                break
            except Exception as exc:
                last_error = exc
                logger.warning("Unable to open audio input via {}: {}", reason, exc)

        if self._stream is None:
            raise RuntimeError("No usable audio input device was available") from last_error

        self._is_recording = True
        self._started_at = perf_counter()
        self._event_bus.publish(
            "RECORDING_STARTED",
            {
                "sample_rate": self._settings.sample_rate,
                "device": resolved_reason,
                "device_id": resolved_device if resolved_device is not None else "default",
            },
        )

    def _stop_locked(self) -> None:
        logger.info("Stopping audio recording")
        assert self._stream is not None
        self._stream.stop()
        self._stream.close()
        self._stream = None
        self._is_recording = False

        if self._frames:
            audio = np.concatenate(self._frames, axis=0)
        else:
            audio = np.empty((0,), dtype=np.float32)

        if audio.ndim > 1:
            audio = np.squeeze(audio, axis=1)

        duration = max(perf_counter() - self._started_at, 0.0)
        self._event_bus.publish(
            "RECORDING_STOPPED",
            {
                "audio": audio,
                "sample_rate": self._settings.sample_rate,
                "duration": duration,
            },
        )

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info: Any, status: sd.CallbackFlags) -> None:
        if status:
            logger.warning("Audio callback status: {}", status)
        del frames, time_info
        self._frames.append(indata.copy())
