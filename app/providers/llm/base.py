from __future__ import annotations

from typing import Protocol


class LLMProvider(Protocol):
    name: str

    def polish(self, text: str, language: str, context: dict | None = None) -> str:
        """Polish transcript text."""

    def warmup(self) -> None:
        """Optionally warm up the model."""

    def unload(self) -> None:
        """Release provider resources."""
