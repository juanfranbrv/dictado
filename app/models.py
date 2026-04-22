from __future__ import annotations

from dataclasses import dataclass, field


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
