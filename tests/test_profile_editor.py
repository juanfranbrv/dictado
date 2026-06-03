from __future__ import annotations

import unittest

from PyQt6.QtWidgets import QApplication

from app.models import Profile
from app.ui.widgets.profile_editor import LLM_CHAIN_ROWS, ProfileEditor


class ProfileEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_preserves_four_llm_chain_entries(self) -> None:
        editor = ProfileEditor()
        profile = Profile(
            name="default",
            stt_provider="faster-whisper",
            stt_config={},
            polish_enabled=True,
            llm_chain=[
                {"provider": "google", "api_key": "google-key", "model": "gemini-flash-lite-latest", "enabled": True},
                {"provider": "google", "api_key": "google-key", "model": "gemini-flash-latest", "enabled": True},
                {"provider": "groq", "api_key": "groq-key", "model": "qwen/qwen3-32b", "enabled": True},
                {
                    "provider": "fireworks",
                    "api_key": "fireworks-key",
                    "model": "accounts/fireworks/models/minimax-m2p7",
                    "enabled": True,
                },
            ],
        )

        editor.set_profile(profile)
        saved = editor.profile()

        self.assertIsNotNone(saved)
        self.assertEqual(len(saved.llm_chain), LLM_CHAIN_ROWS)
        self.assertEqual(
            [(item["provider"], item["model"]) for item in saved.llm_chain],
            [
                ("google", "gemini-flash-lite-latest"),
                ("google", "gemini-flash-latest"),
                ("groq", "qwen/qwen3-32b"),
                ("fireworks", "accounts/fireworks/models/minimax-m2p7"),
            ],
        )
