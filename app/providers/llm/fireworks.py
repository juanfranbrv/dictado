from __future__ import annotations

import httpx
from loguru import logger

from app.learning.prompts import SYSTEM_PROMPTS
from app.providers.llm.registry import register_llm
from app.providers.llm.utils import build_polish_input, polish_output_is_usable, sanitize_polish_output


@register_llm("fireworks")
class FireworksLLM:
    name = "fireworks"

    def __init__(
        self,
        api_key: str,
        model: str = "accounts/fireworks/models/minimax-m2p7",
        endpoint: str = "https://api.fireworks.ai/inference/v1",
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

        logger.info("Sending polish request to Fireworks model {} with style {}", self._model, style)
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
                    "max_tokens": 220,
                },
            )
            response.raise_for_status()
            payload = response.json()

        polished = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
        sanitized = sanitize_polish_output(polished, text, language)
        if not polish_output_is_usable(polished, sanitized, text):
            raise ValueError("LLM returned reasoning or unusable polish output")
        return sanitized

    def warmup(self) -> None:
        logger.info("Fireworks warmup for {}", self._model)
        try:
            self.polish("hola", "es", {"style": "default", "app_name": "warmup"})
        except Exception as exc:
            logger.warning("Fireworks warmup failed: {}", exc)

    def unload(self) -> None:
        logger.info("Fireworks unload for {}", self._model)
