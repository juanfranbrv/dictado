from __future__ import annotations

import httpx
from loguru import logger

from app.learning.prompts import SYSTEM_PROMPTS
from app.providers.llm.registry import register_llm
from app.providers.llm.utils import build_polish_input, sanitize_polish_output


@register_llm("gemini")
class GeminiLLM:
    name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-3.1-flash-lite-preview",
        endpoint: str = "https://generativelanguage.googleapis.com/v1beta",
        timeout: float = 10.0,
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

        logger.info("Sending polish request to Gemini model {} with style {}", self._model, style)
        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(
                f"{self._endpoint}/models/{self._model}:generateContent",
                headers={"x-goog-api-key": self._api_key, "Content-Type": "application/json"},
                json={
                    "systemInstruction": {"parts": [{"text": system_prompt}]},
                    "contents": [{"parts": [{"text": user_prompt}]}],
                    "generationConfig": {"temperature": 0.0, "maxOutputTokens": 220},
                },
            )
            response.raise_for_status()
            payload = response.json()

        parts = payload.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        polished = "".join(part.get("text", "") for part in parts)
        return sanitize_polish_output(polished, text, language)

    def warmup(self) -> None:
        logger.info("Gemini warmup for {}", self._model)
        try:
            self.polish("hola", "es", {"style": "default", "app_name": "warmup"})
        except Exception as exc:
            logger.warning("Gemini warmup failed: {}", exc)

    def unload(self) -> None:
        logger.info("Gemini unload for {}", self._model)
