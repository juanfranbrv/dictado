from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.providers.llm.base import LLMProvider

LLMFactory = Callable[..., LLMProvider]
_LLM_REGISTRY: dict[str, LLMFactory] = {}


def register_llm(name: str) -> Callable[[LLMFactory], LLMFactory]:
    def decorator(factory: LLMFactory) -> LLMFactory:
        _LLM_REGISTRY[name] = factory
        return factory

    return decorator


def create_llm(name: str, **kwargs: Any) -> LLMProvider:
    if name not in _LLM_REGISTRY:
        available = ", ".join(sorted(_LLM_REGISTRY))
        raise ValueError(f"LLM provider '{name}' no registrado. Disponibles: {available}")
    return _LLM_REGISTRY[name](**kwargs)
