from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from loguru import logger

from app.config import STTSettings
from app.events import EventBus
from app.models import Transcript
from app.providers.stt import __all__ as _stt_import_guard  # noqa: F401
from app.providers.stt.base import STTProvider
from app.providers.stt.registry import create_stt


class Pipeline:
    """Handle audio -> STT -> transcript events."""

    def __init__(self, event_bus: EventBus, stt_settings: STTSettings) -> None:
        self._event_bus = event_bus
        self._stt_settings = stt_settings
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="stt")
        self._provider = self._create_provider()
        self._warmup_submitted = False

    def attach(self) -> None:
        self._event_bus.subscribe("RECORDING_STOPPED", self._handle_recording_stopped)

    def shutdown(self) -> None:
        self._provider.unload()
        self._executor.shutdown(wait=False, cancel_futures=False)

    def warmup_async(self) -> None:
        if self._warmup_submitted or not self._stt_settings.warmup_on_startup:
            return
        self._warmup_submitted = True
        logger.info("Scheduling STT warmup in background")
        self._executor.submit(self._warmup)

    def _create_provider(self) -> STTProvider:
        provider = create_stt(
            self._stt_settings.provider,
            model=self._stt_settings.model,
            device=self._stt_settings.device,
            compute_type=self._stt_settings.compute_type,
            local_files_only=self._stt_settings.local_files_only,
        )
        logger.info(
            "Initialized STT provider {} with model {}",
            self._stt_settings.provider,
            self._stt_settings.model,
        )
        return provider

    def _handle_recording_stopped(self, payload: dict[str, Any]) -> None:
        audio = payload["audio"]
        sample_rate = payload["sample_rate"]
        duration = payload["duration"]
        if sample_rate != 16000:
            logger.warning("Expected 16000 Hz audio but received {}", sample_rate)

        if audio.size == 0:
            logger.warning("Skipping transcription for empty audio buffer")
            return

        logger.info("Queueing transcription for {:.2f}s of audio", duration)
        self._executor.submit(self._transcribe_and_publish, audio, duration)

    def _warmup(self) -> None:
        try:
            self._provider.warmup()
        except Exception as exc:
            logger.warning("STT warmup failed: {}", exc)

    def _transcribe_and_publish(self, audio, duration: float) -> None:
        try:
            transcript = self._provider.transcribe(audio, language="es")
            self._publish_transcript(transcript, duration)
        except Exception as exc:
            logger.exception("Transcription failed: {}", exc)

    def _publish_transcript(self, transcript: Transcript, audio_duration: float) -> None:
        self._event_bus.publish(
            "TRANSCRIPT_READY",
            {
                "transcript": transcript,
                "audio_duration": audio_duration,
            },
        )
