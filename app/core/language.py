from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from app.config import LanguageSettings
from app.utils.paths import language_state_path


@dataclass
class LanguageState:
    last_language: str
    last_confidence: float


class LanguageHysteresis:
    def __init__(self, settings: LanguageSettings, state_path: Path | None = None) -> None:
        self._settings = settings
        self._state_path = state_path or language_state_path()
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state = self._load_state()
        self._forced_once: str | None = None

    @property
    def active_language(self) -> str:
        return self._forced_once or self._state.last_language

    def choose_hint(self) -> str:
        return self.active_language

    def force_next(self, language: str) -> None:
        if language not in self._settings.preferred:
            raise ValueError(f"Unsupported language override '{language}'")
        self._forced_once = language
        logger.info("Forced next language to {}", language)

    def update(self, detected_language: str | None, confidence: float | None) -> str:
        forced = self._forced_once
        self._forced_once = None

        if forced is not None:
            self._state = LanguageState(last_language=forced, last_confidence=confidence or 1.0)
            self._save_state()
            return forced

        if not detected_language:
            return self._state.last_language

        detected_language = detected_language.lower()
        confidence = confidence or 0.0

        if detected_language == self._state.last_language:
            self._state = LanguageState(last_language=detected_language, last_confidence=confidence)
            self._save_state()
            return detected_language

        threshold = self._settings.confidence_threshold + self._settings.switch_penalty
        if confidence >= threshold:
            self._state = LanguageState(last_language=detected_language, last_confidence=confidence)
            self._save_state()
            logger.info("Language switched to {} with confidence {:.2f}", detected_language, confidence)
            return detected_language

        logger.info(
            "Keeping language {} despite detected {} ({:.2f} < {:.2f})",
            self._state.last_language,
            detected_language,
            confidence,
            threshold,
        )
        return self._state.last_language

    def _load_state(self) -> LanguageState:
        if not self._state_path.exists():
            return LanguageState(last_language=self._settings.default, last_confidence=1.0)

        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
            return LanguageState(
                last_language=data.get("last_language", self._settings.default),
                last_confidence=float(data.get("last_confidence", 1.0)),
            )
        except Exception as exc:
            logger.warning("Failed to load language state ({}). Using defaults.", exc)
            return LanguageState(last_language=self._settings.default, last_confidence=1.0)

    def _save_state(self) -> None:
        payload = {
            "last_language": self._state.last_language,
            "last_confidence": self._state.last_confidence,
        }
        self._state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
