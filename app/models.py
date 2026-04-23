from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class Transcript:
    text: str
    language: str | None
    language_confidence: float | None
    duration: float
    segments: list[Segment] = field(default_factory=list)


@dataclass(frozen=True)
class Profile:
    name: str
    stt_provider: str
    stt_config: dict[str, Any]
    llm_provider: str | None = None
    llm_config: dict[str, Any] | None = None
    llm_fallback_provider: str | None = None
    llm_fallback_config: dict[str, Any] | None = None
    polish_enabled: bool = False
    inject_raw_first: bool = True
    style: str = "default"
