from __future__ import annotations

import httpx
from loguru import logger

from app.learning.prompts import SYSTEM_PROMPTS
from app.providers.llm.registry import register_llm
from app.providers.llm.utils import build_polish_input, sanitize_polish_output


@register_llm("ollama")
class OllamaLLM:
    name = "ollama"

    def __init__(self, endpoint: str = "http://localhost:11434", model: str = "qwen2.5:7b", timeout: float = 30.0) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._model = model
        self._timeout = timeout

    def polish(self, text: str, language: str, context: dict | None = None) -> str:
        context = context or {}
        style = context.get("style", "default")
        system_prompt = SYSTEM_PROMPTS.get(style, SYSTEM_PROMPTS["default"])
        user_prompt = build_polish_input(text, language)

        logger.info("Sending polish request to Ollama model {} with style {}", self._model, style)
        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(
                f"{self._endpoint}/api/chat",
                json={
                    "model": self._model,
                    "stream": False,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                },
            )
            response.raise_for_status()
            payload = response.json()

        polished = payload.get("message", {}).get("content", "")
        return sanitize_polish_output(polished, text, language)

    def warmup(self) -> None:
        logger.info("Ollama warmup for {}", self._model)
        try:
            self.polish("hola", "es", {"style": "default", "app_name": "warmup"})
        except Exception as exc:
            logger.warning("Ollama warmup failed: {}", exc)

    def unload(self) -> None:
        logger.info("Ollama unload for {}", self._model)
