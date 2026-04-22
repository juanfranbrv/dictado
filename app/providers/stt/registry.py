from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.providers.stt.base import STTProvider

STTFactory = Callable[..., STTProvider]
_STT_REGISTRY: dict[str, STTFactory] = {}


def register_stt(name: str) -> Callable[[STTFactory], STTFactory]:
    def decorator(factory: STTFactory) -> STTFactory:
        _STT_REGISTRY[name] = factory
        return factory

    return decorator


def create_stt(name: str, **kwargs: Any) -> STTProvider:
    if name not in _STT_REGISTRY:
        available = ", ".join(sorted(_STT_REGISTRY))
        raise ValueError(f"STT provider '{name}' no registrado. Disponibles: {available}")
    return _STT_REGISTRY[name](**kwargs)


def list_stt_providers() -> list[str]:
    return sorted(_STT_REGISTRY)
