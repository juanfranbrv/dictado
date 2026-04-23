from __future__ import annotations

from time import perf_counter

import numpy as np
from faster_whisper import WhisperModel
from loguru import logger

from app.models import Segment, Transcript
from app.providers.stt.registry import register_stt
from app.utils.whisper_models import whisper_model_load_target


@register_stt("faster-whisper")
class FasterWhisperSTT:
    name = "faster-whisper"

    def __init__(
        self,
        model: str,
        device: str,
        compute_type: str,
        local_files_only: bool = True,
        beam_size: int = 5,
    ) -> None:
        self._model_name = model
        self._requested_device = device
        self._requested_compute_type = compute_type
        self._local_files_only = local_files_only
        self._beam_size = beam_size
        self._active_device = device
        self._active_compute_type = compute_type
        self._model: WhisperModel | None = None

    def warmup(self) -> None:
        model = self._ensure_model()
        silence = np.zeros(16000, dtype=np.float32)
        segments, _ = model.transcribe(silence, language="es", beam_size=1)
        list(segments)
        logger.info(
            "STT warmup completed with {} on {} ({})",
            self._model_name,
            self._active_device,
            self._active_compute_type,
        )

    def transcribe(
        self,
        audio: np.ndarray,
        language: str | None,
        hints: list[str] | None = None,
    ) -> Transcript:
        model = self._ensure_model()
        start = perf_counter()
        initial_prompt = ", ".join(hints) if hints else None

        segments, info = model.transcribe(
            audio,
            language=language,
            initial_prompt=initial_prompt,
            beam_size=self._beam_size,
            condition_on_previous_text=False,
        )

        segment_list = [
            Segment(start=segment.start, end=segment.end, text=segment.text.strip())
            for segment in segments
        ]
        text = " ".join(segment.text for segment in segment_list).strip()
        duration = perf_counter() - start
        logger.info(
            "Transcription completed in {:.2f}s with {} on {} ({})",
            duration,
            self._model_name,
            self._active_device,
            self._active_compute_type,
        )
        return Transcript(
            text=text,
            language=getattr(info, "language", None),
            language_confidence=getattr(info, "language_probability", None),
            duration=duration,
            segments=segment_list,
        )

    def unload(self) -> None:
        if self._model is not None:
            logger.info("Unloading STT model {}", self._model_name)
        self._model = None

    def _ensure_model(self) -> WhisperModel:
        if self._model is not None:
            return self._model

        model_target = whisper_model_load_target(self._model_name)
        try:
            self._active_device = self._requested_device
            self._active_compute_type = self._requested_compute_type
            self._model = WhisperModel(
                model_target,
                device=self._active_device,
                compute_type=self._active_compute_type,
                local_files_only=self._local_files_only,
            )
            logger.info(
                "Loaded STT model {} from {} on {} ({}) local_only={}",
                self._model_name,
                model_target,
                self._active_device,
                self._active_compute_type,
                self._local_files_only,
            )
            return self._model
        except Exception as exc:
            if self._requested_device != "cuda":
                raise

            logger.warning(
                "Failed to load STT model on CUDA ({}). Falling back to CPU int8.",
                exc,
            )
            self._active_device = "cpu"
            self._active_compute_type = "int8"
            self._model = WhisperModel(
                model_target,
                device=self._active_device,
                compute_type=self._active_compute_type,
                local_files_only=self._local_files_only,
            )
            logger.info(
                "Loaded STT model {} from {} on {} ({}) local_only={}",
                self._model_name,
                model_target,
                self._active_device,
                self._active_compute_type,
                self._local_files_only,
            )
            return self._model
