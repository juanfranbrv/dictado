from __future__ import annotations

from typing import Protocol

import numpy as np

from app.models import Transcript


class STTProvider(Protocol):
    name: str

    def transcribe(
        self,
        audio: np.ndarray,
        language: str | None,
        hints: list[str] | None = None,
    ) -> Transcript:
        """Transcribe mono float32 16kHz audio to text."""

    def warmup(self) -> None:
        """Optionally warm up the model."""

    def unload(self) -> None:
        """Release provider resources."""
