from __future__ import annotations

import httpx
from loguru import logger

from app.learning.prompts import SYSTEM_PROMPTS
from app.providers.llm.registry import register_llm
from app.providers.llm.utils import build_polish_input, sanitize_polish_output


@register_llm("groq")
class GroqLLM:
    name = "groq"

    def __init__(
        self,
        api_key: str,
        model: str = "llama-3.1-8b-instant",
        endpoint: str = "https://api.groq.com/openai/v1",
        timeout: float = 6.0,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._endpoint = endpoint.rstrip("/")
        self._timeout = timeout

    def polish(self, text: str, language: str, context: dict | None = None) -> str:
        context = context or {}
        style = context.get("style", "default")
        system_prompt = SYSTEM_PROMPTS.get(style, SYSTEM_PROMPTS["default"])
        user_prompt = build_polish_input(text, language)

        logger.info("Sending polish request to Groq model {} with style {}", self._model, style)
        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(
                f"{self._endpoint}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.0,
                    "max_completion_tokens": 220,
                },
            )
            response.raise_for_status()
            payload = response.json()

        polished = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
        return sanitize_polish_output(polished, text, language)

    def warmup(self) -> None:
        logger.info("Groq warmup for {}", self._model)
        try:
            self.polish("hola", "es", {"style": "default", "app_name": "warmup"})
        except Exception as exc:
            logger.warning("Groq warmup failed: {}", exc)

    def unload(self) -> None:
        logger.info("Groq unload for {}", self._model)
