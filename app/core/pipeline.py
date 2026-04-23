from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from time import perf_counter
from typing import Any

import numpy as np
from loguru import logger

from app.config import STTSettings
from app.core.language import LanguageHysteresis
from app.events import EventBus
from app.learning.hints import build_hints
from app.models import Profile, Transcript
from app.providers.llm import __all__ as _llm_import_guard  # noqa: F401
from app.providers.llm.base import LLMProvider
from app.providers.llm.registry import create_llm
from app.providers.stt import __all__ as _stt_import_guard  # noqa: F401
from app.providers.stt.base import STTProvider
from app.providers.stt.registry import create_stt


class Pipeline:
    """Handle audio -> STT -> transcript events."""

    _MIN_RECORD_SECONDS = 0.12
    _MIN_RECORD_SAMPLES = 1200
    _SHORT_SILENCE_WINDOW_SECONDS = 0.45
    _SILENCE_RMS_THRESHOLD = 0.0015
    _SILENCE_PEAK_THRESHOLD = 0.008
    _HARD_SILENCE_RMS_THRESHOLD = 0.00005
    _HARD_SILENCE_PEAK_THRESHOLD = 0.0005

    def __init__(
        self,
        event_bus: EventBus,
        stt_settings: STTSettings,
        language_hysteresis: LanguageHysteresis,
        profiles: dict[str, Profile],
        active_profile: str,
    ) -> None:
        self._event_bus = event_bus
        self._stt_settings = stt_settings
        self._language_hysteresis = language_hysteresis
        self._profiles = profiles
        self._active_profile_name = active_profile
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="pipeline")
        self._profile = self._profiles[self._active_profile_name]
        self._provider = self._create_provider(self._profile)
        self._llm_provider = self._create_llm_provider(self._profile)
        self._llm_fallback_provider = self._create_llm_fallback_provider(self._profile)
        self._warmup_submitted = False
        self._session_seq = 0

    def attach(self) -> None:
        self._event_bus.subscribe("RECORDING_STOPPED", self._handle_recording_stopped)
        self._event_bus.subscribe("FORCE_LANGUAGE_ES", lambda payload: self._force_language("es"))
        self._event_bus.subscribe("FORCE_LANGUAGE_EN", lambda payload: self._force_language("en"))
        self._event_bus.subscribe("SWITCH_PROFILE", lambda payload: self.switch_profile(payload["profile"]))

    def shutdown(self) -> None:
        self._provider.unload()
        if self._llm_provider is not None:
            self._llm_provider.unload()
        if self._llm_fallback_provider is not None:
            self._llm_fallback_provider.unload()
        self._executor.shutdown(wait=False, cancel_futures=False)

    def warmup_async(self) -> None:
        if self._warmup_submitted or not self._profile.stt_config.get("warmup_on_startup", self._stt_settings.warmup_on_startup):
            return
        self._warmup_submitted = True
        logger.info("Scheduling STT warmup in background")
        self._executor.submit(self._warmup)
        if self._llm_provider is not None:
            logger.info("Scheduling LLM warmup in background")
            self._executor.submit(self._warmup_llm)
        if self._llm_fallback_provider is not None:
            logger.info("Scheduling fallback LLM warmup in background")
            self._executor.submit(self._warmup_fallback_llm)

    def switch_profile(self, profile_name: str) -> None:
        if profile_name == self._active_profile_name:
            return
        if profile_name not in self._profiles:
            raise ValueError(f"Profile '{profile_name}' no existe")

        logger.info("Switching profile from {} to {}", self._active_profile_name, profile_name)
        self._provider.unload()
        if self._llm_provider is not None:
            self._llm_provider.unload()
        if self._llm_fallback_provider is not None:
            self._llm_fallback_provider.unload()
        self._active_profile_name = profile_name
        self._profile = self._profiles[profile_name]
        self._provider = self._create_provider(self._profile)
        self._llm_provider = self._create_llm_provider(self._profile)
        self._llm_fallback_provider = self._create_llm_fallback_provider(self._profile)
        self._warmup_submitted = False
        self.warmup_async()
        self._event_bus.publish("PROFILE_CHANGED", {"profile": profile_name})

    def list_profiles(self) -> list[str]:
        return sorted(self._profiles)

    @property
    def active_profile(self) -> str:
        return self._active_profile_name

    def reconfigure(self, profiles: dict[str, Profile], active_profile: str) -> None:
        if active_profile not in profiles:
            logger.warning("Ignoring config reload with unknown active profile {}", active_profile)
            return

        profile_changed = active_profile != self._active_profile_name
        self._profiles = profiles
        if profile_changed:
            self.switch_profile(active_profile)
            return

        logger.info("Reconfiguring active profile {}", active_profile)
        self._provider.unload()
        if self._llm_provider is not None:
            self._llm_provider.unload()
        if self._llm_fallback_provider is not None:
            self._llm_fallback_provider.unload()
        self._profile = profiles[active_profile]
        self._provider = self._create_provider(self._profile)
        self._llm_provider = self._create_llm_provider(self._profile)
        self._llm_fallback_provider = self._create_llm_fallback_provider(self._profile)
        self._warmup_submitted = False
        self.warmup_async()

    def _create_provider(self, profile: Profile) -> STTProvider:
        stt_config = dict(profile.stt_config)
        provider_kwargs = {
            "model": stt_config.get("model", self._stt_settings.model),
            "device": stt_config.get("device", self._stt_settings.device),
            "compute_type": stt_config.get("compute_type", self._stt_settings.compute_type),
            "local_files_only": stt_config.get("local_files_only", self._stt_settings.local_files_only),
        }
        if "beam_size" in stt_config:
            provider_kwargs["beam_size"] = stt_config["beam_size"]

        provider = create_stt(profile.stt_provider, **provider_kwargs)
        logger.info(
            "Initialized STT provider {} with model {} for profile {}",
            profile.stt_provider,
            provider_kwargs["model"],
            profile.name,
        )
        return provider

    def _create_llm_provider(self, profile: Profile) -> LLMProvider | None:
        llm_profile = self._llm_profile_for(profile)
        if not profile.polish_enabled or not llm_profile.llm_provider:
            return None

        llm_config = dict(llm_profile.llm_config or {})
        llm_config.pop("enabled", None)
        provider = create_llm(llm_profile.llm_provider, **llm_config)
        logger.info("Initialized LLM provider {} for profile {}", llm_profile.llm_provider, profile.name)
        return provider

    def _create_llm_fallback_provider(self, profile: Profile) -> LLMProvider | None:
        llm_profile = self._llm_profile_for(profile)
        if not profile.polish_enabled or not llm_profile.llm_fallback_provider:
            return None

        llm_config = dict(llm_profile.llm_fallback_config or {})
        llm_config.pop("enabled", None)
        provider = create_llm(llm_profile.llm_fallback_provider, **llm_config)
        logger.info("Initialized fallback LLM provider {} for profile {}", llm_profile.llm_fallback_provider, profile.name)
        return provider

    def _llm_profile_for(self, profile: Profile) -> Profile:
        if profile.llm_provider or profile.llm_fallback_provider:
            return profile
        default_profile = self._profiles.get("default")
        if default_profile is not None:
            return default_profile
        return profile

    def _handle_recording_stopped(self, payload: dict[str, Any]) -> None:
        audio = payload["audio"]
        sample_rate = payload["sample_rate"]
        duration = payload["duration"]
        if sample_rate != 16000:
            logger.warning("Expected 16000 Hz audio but received {}", sample_rate)

        if audio.size == 0:
            logger.warning("Skipping transcription for empty audio buffer")
            return

        if duration < self._MIN_RECORD_SECONDS or audio.size < self._MIN_RECORD_SAMPLES:
            logger.info(
                "Ignoring too-short recording: duration={:.3f}s samples={}",
                duration,
                audio.size,
            )
            return

        rms = float(np.sqrt(np.mean(np.square(audio, dtype=np.float32), dtype=np.float32)))
        peak = float(np.max(np.abs(audio)))
        is_short_and_quiet = (
            duration < self._SHORT_SILENCE_WINDOW_SECONDS
            and rms < self._SILENCE_RMS_THRESHOLD
            and peak < self._SILENCE_PEAK_THRESHOLD
        )
        is_effectively_zero = (
            rms < self._HARD_SILENCE_RMS_THRESHOLD
            and peak < self._HARD_SILENCE_PEAK_THRESHOLD
        )

        if is_short_and_quiet or is_effectively_zero:
            logger.info(
                "Ignoring near-silent recording: duration={:.3f}s rms={:.5f} peak={:.5f}",
                duration,
                rms,
                peak,
            )
            return

        logger.info("Queueing transcription for {:.2f}s of audio", duration)
        self._session_seq += 1
        session_id = self._session_seq
        self._event_bus.publish("TIMING", {"session_id": session_id, "stage": "record", "seconds": duration})
        self._executor.submit(self._transcribe_and_publish, audio, duration, session_id)

    def _warmup(self) -> None:
        try:
            self._provider.warmup()
        except Exception as exc:
            logger.warning("STT warmup failed: {}", exc)

    def _warmup_llm(self) -> None:
        if self._llm_provider is None:
            return
        try:
            self._llm_provider.warmup()
        except Exception as exc:
            logger.warning("LLM warmup failed: {}", exc)

    def _warmup_fallback_llm(self) -> None:
        if self._llm_fallback_provider is None:
            return
        try:
            self._llm_fallback_provider.warmup()
        except Exception as exc:
            logger.warning("Fallback LLM warmup failed: {}", exc)

    def _transcribe_and_publish(self, audio, duration: float, session_id: int) -> None:
        try:
            language_hint = self._language_hysteresis.choose_hint()
            logger.info("Transcribing with language hint {}", language_hint)
            vocabulary_hints = build_hints(language_hint)
            transcript = self._provider.transcribe(audio, language=language_hint, hints=vocabulary_hints)
            self._event_bus.publish("TIMING", {"session_id": session_id, "stage": "stt", "seconds": transcript.duration})
            active_language = self._language_hysteresis.update(transcript.language, transcript.language_confidence)
            self._publish_transcript(transcript, duration, session_id)
            self._event_bus.publish("LANGUAGE_CHANGED", {"language": active_language})
            if not self._profile.polish_enabled or not transcript.text.strip():
                self._publish_injection(
                    transcript.text,
                    source="raw",
                    session_id=session_id,
                    transcript=transcript,
                    audio_duration=duration,
                )
                return

            polished_emitted = self._publish_polish_suggestion(transcript, active_language, session_id, duration)
            if not polished_emitted:
                self._publish_injection(
                    transcript.text,
                    source="raw-fallback",
                    session_id=session_id,
                    transcript=transcript,
                    audio_duration=duration,
                )
        except Exception as exc:
            logger.exception("Transcription failed: {}", exc)

    def _force_language(self, language: str) -> None:
        self._language_hysteresis.force_next(language)
        self._event_bus.publish("LANGUAGE_CHANGED", {"language": self._language_hysteresis.active_language})

    def _publish_transcript(self, transcript: Transcript, audio_duration: float, session_id: int) -> None:
        self._event_bus.publish(
            "TRANSCRIPT_READY",
            {
                "transcript": transcript,
                "audio_duration": audio_duration,
                "session_id": session_id,
            },
        )

    def _publish_polish_suggestion(self, transcript: Transcript, language: str, session_id: int, audio_duration: float) -> bool:
        context = {
            "style": self._profile.style,
            "app_name": "unknown",
        }
        polished: str | None = None
        primary_failed = False
        started = perf_counter()

        if self._llm_provider is not None:
            try:
                polished = self._llm_provider.polish(transcript.text, language, context)
            except Exception as exc:
                primary_failed = True
                logger.warning("Primary polish generation failed: {}", exc)

        if primary_failed and self._llm_fallback_provider is not None:
            try:
                polished = self._llm_fallback_provider.polish(transcript.text, language, context)
            except Exception as exc:
                logger.warning("Fallback polish generation failed: {}", exc)
                return False

        self._event_bus.publish("TIMING", {"session_id": session_id, "stage": "polish", "seconds": perf_counter() - started})

        if polished and polished.strip() and polished.strip() != transcript.text.strip():
            self._publish_injection(
                polished,
                source="polished",
                session_id=session_id,
                transcript=transcript,
                polished=polished,
                audio_duration=audio_duration,
            )
            return True
        return False

    def _publish_injection(
        self,
        text: str,
        source: str,
        *,
        session_id: int,
        transcript: Transcript,
        polished: str | None = None,
        audio_duration: float = 0.0,
    ) -> None:
        self._event_bus.publish(
            "INJECT_TEXT",
            {
                "text": text,
                "source": source,
                "profile": self._active_profile_name,
                "session_id": session_id,
                "raw_text": transcript.text,
                "polished_text": polished,
                "language": transcript.language,
                "language_confidence": transcript.language_confidence,
                "audio_duration": audio_duration,
            },
        )
