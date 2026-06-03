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

_REMOTE_LLM_PROVIDERS_REQUIRING_API_KEY = {"fireworks", "google", "gemini", "groq"}


class Pipeline:
    """Handle audio -> STT -> transcript events."""

    _MIN_RECORD_SECONDS = 0.12
    _MIN_RECORD_SAMPLES = 1200
    _SHORT_SILENCE_WINDOW_SECONDS = 0.45
    _SILENCE_RMS_THRESHOLD = 0.0015
    _SILENCE_PEAK_THRESHOLD = 0.008
    _QUIET_RMS_THRESHOLD = 0.0025
    _QUIET_PEAK_THRESHOLD = 0.015
    _HARD_SILENCE_RMS_THRESHOLD = 0.00005
    _HARD_SILENCE_PEAK_THRESHOLD = 0.0005
    _TRAILING_SILENCE_SECONDS = 0.45

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
        self._llm_status = "not-configured"
        self._provider = self._create_provider(self._profile)
        self._llm_chain = self._create_llm_chain(self._profile)
        self._warmup_submitted = False
        self._session_seq = 0

    def attach(self) -> None:
        self._event_bus.subscribe("RECORDING_STOPPED", self._handle_recording_stopped)
        self._event_bus.subscribe("FORCE_LANGUAGE_ES", lambda payload: self._force_language("es"))
        self._event_bus.subscribe("FORCE_LANGUAGE_EN", lambda payload: self._force_language("en"))
        self._event_bus.subscribe("SWITCH_PROFILE", lambda payload: self.switch_profile(payload["profile"]))

    def shutdown(self) -> None:
        self._provider.unload()
        for _, _, provider in self._llm_chain:
            provider.unload()
        self._executor.shutdown(wait=False, cancel_futures=False)

    def warmup_async(self) -> None:
        if self._warmup_submitted or not self._profile.stt_config.get("warmup_on_startup", self._stt_settings.warmup_on_startup):
            return
        self._warmup_submitted = True
        logger.info("Scheduling STT warmup in background")
        self._executor.submit(self._warmup)
        if self._llm_chain:
            logger.info("Scheduling LLM warmup in background")
            self._executor.submit(self._warmup_llm)

    def switch_profile(self, profile_name: str) -> None:
        if profile_name == self._active_profile_name:
            return
        if profile_name not in self._profiles:
            raise ValueError(f"Profile '{profile_name}' no existe")

        logger.info("Switching profile from {} to {}", self._active_profile_name, profile_name)
        self._provider.unload()
        for _, _, provider in self._llm_chain:
            provider.unload()
        self._active_profile_name = profile_name
        self._profile = self._profiles[profile_name]
        self._provider = self._create_provider(self._profile)
        self._llm_chain = self._create_llm_chain(self._profile)
        self._warmup_submitted = False
        self.warmup_async()
        self._publish_llm_status()
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
        for _, _, provider in self._llm_chain:
            provider.unload()
        self._profile = profiles[active_profile]
        self._provider = self._create_provider(self._profile)
        self._llm_chain = self._create_llm_chain(self._profile)
        self._warmup_submitted = False
        self.warmup_async()
        self._publish_llm_status()

    @property
    def llm_status(self) -> str:
        return self._llm_status

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

    def _create_llm_chain(self, profile: Profile) -> list[tuple[str, str, LLMProvider]]:
        llm_profile = self._llm_profile_for(profile)
        if not profile.polish_enabled:
            self._llm_status = "not-configured"
            return []

        chain: list[tuple[str, str, LLMProvider]] = []
        for item in _llm_chain_for(llm_profile):
            provider_name = str(item.get("provider", "")).strip()
            if not provider_name or item.get("enabled") is False:
                continue
            llm_config = dict(item)
            llm_config.pop("provider", None)
            llm_config.pop("enabled", None)
            if _missing_required_llm_config(provider_name, llm_config):
                logger.warning("Skipping LLM provider {} for profile {} because api_key is not configured", provider_name, profile.name)
                continue
            model_name = str(llm_config.get("model", "")).strip()
            provider = create_llm(provider_name, **llm_config)
            chain.append((provider_name, model_name, provider))
            logger.info("Initialized LLM provider {} model {} for profile {}", provider_name, model_name or "default", profile.name)

        self._llm_status = "configured" if chain else "not-configured"
        return chain

    def _llm_profile_for(self, profile: Profile) -> Profile:
        if profile.llm_chain or profile.llm_provider or profile.llm_fallback_provider:
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
        is_quiet = rms < self._QUIET_RMS_THRESHOLD and peak < self._QUIET_PEAK_THRESHOLD
        is_effectively_zero = (
            rms < self._HARD_SILENCE_RMS_THRESHOLD
            and peak < self._HARD_SILENCE_PEAK_THRESHOLD
        )

        if is_short_and_quiet or is_quiet or is_effectively_zero:
            logger.info(
                "Ignoring near-silent recording: duration={:.3f}s rms={:.5f} peak={:.5f}",
                duration,
                rms,
                peak,
            )
            return

        audio = _append_trailing_silence(audio, sample_rate, self._TRAILING_SILENCE_SECONDS)
        padded_duration = duration + self._TRAILING_SILENCE_SECONDS

        logger.info("Queueing transcription for {:.2f}s of audio", padded_duration)
        self._session_seq += 1
        session_id = self._session_seq
        self._event_bus.publish("TIMING", {"session_id": session_id, "stage": "record", "seconds": padded_duration})
        self._executor.submit(self._transcribe_and_publish, audio, padded_duration, session_id)

    def _warmup(self) -> None:
        try:
            self._provider.warmup()
        except Exception as exc:
            logger.warning("STT warmup failed: {}", exc)

    def _warmup_llm(self) -> None:
        for provider_name, model_name, provider in self._llm_chain:
            started = perf_counter()
            try:
                provider.warmup()
                duration = perf_counter() - started
                logger.info(
                    "[llm] warmup provider={} model={} status=ok duration={:.2f}s",
                    provider_name,
                    model_name or "default",
                    duration,
                )
                self._publish_llm_debug(
                    "warmup",
                    provider_name,
                    model_name,
                    "ok",
                    duration,
                )
                return
            except Exception as exc:
                duration = perf_counter() - started
                logger.warning(
                    "[llm] warmup provider={} model={} status=failed duration={:.2f}s error={}",
                    provider_name,
                    model_name or "default",
                    duration,
                    exc,
                )
                self._publish_llm_debug("warmup", provider_name, model_name, "failed", duration, str(exc))
        self._llm_status = "unavailable"
        self._publish_llm_status()

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
        started = perf_counter()

        for provider_name, model_name, provider in self._llm_chain:
            attempt_started = perf_counter()
            try:
                polished = provider.polish(transcript.text, language, context)
                attempt_seconds = perf_counter() - attempt_started
                logger.info(
                    "[llm] session={} provider={} model={} status=ok duration={:.2f}s",
                    session_id,
                    provider_name,
                    model_name or "default",
                    attempt_seconds,
                )
                self._publish_llm_debug(session_id, provider_name, model_name, "ok", attempt_seconds)
                if polished and polished.strip() and polished.strip() != transcript.text.strip():
                    self._event_bus.publish(
                        "TIMING",
                        {"session_id": session_id, "stage": "polish", "seconds": perf_counter() - started},
                    )
                    self._publish_injection(
                        polished,
                        source=f"polished:{provider_name}:{model_name or 'default'}",
                        session_id=session_id,
                        transcript=transcript,
                        polished=polished,
                        audio_duration=audio_duration,
                    )
                    return True
            except Exception as exc:
                attempt_seconds = perf_counter() - attempt_started
                logger.warning(
                    "[llm] session={} provider={} model={} status=failed duration={:.2f}s error={}",
                    session_id,
                    provider_name,
                    model_name or "default",
                    attempt_seconds,
                    exc,
                )
                self._publish_llm_debug(session_id, provider_name, model_name, "failed", attempt_seconds, str(exc))

        self._event_bus.publish("TIMING", {"session_id": session_id, "stage": "polish", "seconds": perf_counter() - started})
        if self._llm_chain:
            self._llm_status = "unavailable"
            self._publish_llm_status()
            duration = perf_counter() - started
            logger.warning("[llm] session={} status=none duration={:.2f}s", session_id, duration)
            self._publish_llm_debug(session_id, "-", "-", "none", duration)
        else:
            logger.warning("[llm] session={} status=not-configured duration=0.00s", session_id)
            self._publish_llm_debug(session_id, "-", "-", "not-configured", 0.0)
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

    def _publish_llm_status(self) -> None:
        self._event_bus.publish("LLM_STATUS_CHANGED", {"status": self._llm_status})

    def _publish_llm_debug(
        self,
        session_id: int | str,
        provider: str,
        model: str,
        status: str,
        duration: float,
        error: str = "",
    ) -> None:
        self._event_bus.publish(
            "LLM_DEBUG",
            {
                "session_id": session_id,
                "provider": provider,
                "model": model or "default",
                "status": status,
                "duration": duration,
                "error": error,
            },
        )


def _missing_required_llm_config(provider_name: str, config: dict[str, Any]) -> bool:
    if provider_name not in _REMOTE_LLM_PROVIDERS_REQUIRING_API_KEY:
        return False
    return not str(config.get("api_key", "")).strip()


def _llm_chain_for(profile: Profile) -> list[dict[str, Any]]:
    if profile.llm_chain:
        return [dict(item) for item in profile.llm_chain]

    chain: list[dict[str, Any]] = []
    if profile.llm_provider:
        config = dict(profile.llm_config or {})
        config["provider"] = profile.llm_provider
        config.setdefault("enabled", True)
        chain.append(config)
    if profile.llm_fallback_provider:
        config = dict(profile.llm_fallback_config or {})
        config["provider"] = profile.llm_fallback_provider
        config.setdefault("enabled", True)
        chain.append(config)
    return chain


def _append_trailing_silence(audio: np.ndarray, sample_rate: int, seconds: float) -> np.ndarray:
    sample_count = int(sample_rate * seconds)
    if sample_count <= 0:
        return audio
    silence = np.zeros(sample_count, dtype=np.float32)
    return np.concatenate([audio.astype(np.float32, copy=False), silence])
