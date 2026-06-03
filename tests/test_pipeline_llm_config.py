from __future__ import annotations

import unittest
from unittest.mock import call, patch

from app.core.pipeline import Pipeline
from app.models import Profile, Transcript


class PipelineLLMConfigTests(unittest.TestCase):
    def test_skips_remote_llm_entries_without_api_key(self) -> None:
        pipeline = _pipeline_with_profiles()
        profile = Profile(
            name="default",
            stt_provider="faster-whisper",
            stt_config={},
            llm_chain=[
                {"provider": "fireworks", "model": "accounts/fireworks/models/minimax-m2p7", "enabled": True},
                {"provider": "google", "model": "gemini-flash-lite-latest", "enabled": True},
            ],
            polish_enabled=True,
        )

        with patch("app.core.pipeline.create_llm") as create_llm:
            chain = pipeline._create_llm_chain(profile)

        self.assertEqual(chain, [])
        self.assertEqual(pipeline._llm_status, "not-configured")
        create_llm.assert_not_called()

    def test_creates_llm_chain_in_configured_order(self) -> None:
        pipeline = _pipeline_with_profiles()
        profile = Profile(
            name="default",
            stt_provider="faster-whisper",
            stt_config={},
            llm_chain=[
                {"provider": "google", "api_key": "google", "model": "gemini-flash-lite-latest", "enabled": True},
                {"provider": "google", "api_key": "google", "model": "gemini-flash-latest", "enabled": True},
                {"provider": "groq", "api_key": "groq", "model": "qwen/qwen3-32b", "enabled": True},
                {"provider": "fireworks", "api_key": "fw", "model": "accounts/fireworks/models/minimax-m2p7", "enabled": True},
            ],
            polish_enabled=True,
        )

        with patch("app.core.pipeline.create_llm") as create_llm:
            chain = pipeline._create_llm_chain(profile)

        self.assertEqual([(name, model) for name, model, _ in chain], [
            ("google", "gemini-flash-lite-latest"),
            ("google", "gemini-flash-latest"),
            ("groq", "qwen/qwen3-32b"),
            ("fireworks", "accounts/fireworks/models/minimax-m2p7"),
        ])
        self.assertEqual(pipeline._llm_status, "configured")
        self.assertEqual(
            create_llm.call_args_list,
            [
                call("google", api_key="google", model="gemini-flash-lite-latest"),
                call("google", api_key="google", model="gemini-flash-latest"),
                call("groq", api_key="groq", model="qwen/qwen3-32b"),
                call("fireworks", api_key="fw", model="accounts/fireworks/models/minimax-m2p7"),
            ],
        )

    def test_uses_next_llm_when_previous_provider_fails(self) -> None:
        pipeline = _pipeline_with_profiles()
        pipeline._llm_chain = [
            ("fireworks", "accounts/fireworks/models/minimax-m2p7", _FailingLLM()),
            ("google", "gemini-flash-lite-latest", _FakeLLM("hola pulido")),
        ]

        emitted = pipeline._publish_polish_suggestion(_transcript("hola bruto"), "es", 1, 0.5)

        self.assertTrue(emitted)
        self.assertEqual(pipeline.injected_texts, ["hola pulido"])

    def test_source_includes_provider_and_model(self) -> None:
        pipeline = _pipeline_with_profiles()
        pipeline._llm_chain = [("google", "gemini-flash-lite-latest", _FakeLLM("hola pulido"))]

        pipeline._publish_polish_suggestion(_transcript("hola bruto"), "es", 1, 0.5)

        self.assertEqual(pipeline.injected_sources, ["polished:google:gemini-flash-lite-latest"])
        self.assertEqual(pipeline.debug_events[-1]["provider"], "google")
        self.assertEqual(pipeline.debug_events[-1]["model"], "gemini-flash-lite-latest")
        self.assertEqual(pipeline.debug_events[-1]["status"], "ok")
        self.assertGreaterEqual(pipeline.debug_events[-1]["duration"], 0.0)


def _pipeline_with_profiles() -> Pipeline:
    pipeline = Pipeline.__new__(Pipeline)
    pipeline._profiles = {}
    pipeline._profile = Profile(name="default", stt_provider="faster-whisper", stt_config={}, polish_enabled=True)
    pipeline._event_bus = _FakeEventBus(pipeline)
    pipeline._active_profile_name = "default"
    pipeline._llm_status = "not-configured"
    pipeline.debug_events = []
    pipeline.injected_texts = []
    pipeline.injected_sources = []

    def publish_injection(text, source, **kwargs):
        pipeline.injected_texts.append(text)
        pipeline.injected_sources.append(source)

    pipeline._publish_injection = publish_injection
    return pipeline


class _FakeEventBus:
    def __init__(self, pipeline=None) -> None:
        self._pipeline = pipeline

    def publish(self, event_name, payload=None) -> None:
        if event_name == "LLM_DEBUG" and self._pipeline is not None:
            self._pipeline.debug_events.append(payload or {})


class _FakeLLM:
    def __init__(self, text: str) -> None:
        self._text = text

    def polish(self, text: str, language: str, context=None) -> str:
        return self._text


class _FailingLLM:
    def polish(self, text: str, language: str, context=None) -> str:
        raise RuntimeError("failed")


def _transcript(text: str) -> Transcript:
    return Transcript(text=text, language="es", language_confidence=1.0, duration=0.1)
