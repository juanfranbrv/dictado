from __future__ import annotations

import unittest

import numpy as np

from app.core.pipeline import Pipeline


class PipelineSilenceTests(unittest.TestCase):
    def test_long_near_silent_recording_is_not_transcribed(self) -> None:
        pipeline = Pipeline.__new__(Pipeline)
        pipeline.submitted = False
        pipeline._executor = _FakeExecutor(pipeline)
        pipeline._event_bus = _FakeEventBus()
        pipeline._session_seq = 0

        audio = np.full((16000,), 0.0008, dtype=np.float32)

        pipeline._handle_recording_stopped({"audio": audio, "sample_rate": 16000, "duration": 1.0})

        self.assertFalse(pipeline.submitted)

    def test_low_but_clear_voice_is_transcribed(self) -> None:
        pipeline = Pipeline.__new__(Pipeline)
        pipeline.submitted = False
        pipeline.submitted_audio = None
        pipeline.submitted_duration = None
        pipeline._executor = _FakeExecutor(pipeline)
        pipeline._event_bus = _FakeEventBus()
        pipeline._session_seq = 0

        t = np.linspace(0, 1.0, 16000, endpoint=False)
        audio = (0.018 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)

        pipeline._handle_recording_stopped({"audio": audio, "sample_rate": 16000, "duration": 1.0})

        self.assertTrue(pipeline.submitted)
        self.assertEqual(pipeline.submitted_audio.size, 16000 + int(16000 * pipeline._TRAILING_SILENCE_SECONDS))
        self.assertAlmostEqual(pipeline.submitted_duration, 1.0 + pipeline._TRAILING_SILENCE_SECONDS)


class _FakeExecutor:
    def __init__(self, pipeline) -> None:
        self._pipeline = pipeline

    def submit(self, *args, **kwargs) -> None:
        self._pipeline.submitted = True
        self._pipeline.submitted_audio = args[1]
        self._pipeline.submitted_duration = args[2]


class _FakeEventBus:
    def publish(self, event_name, payload=None) -> None:
        pass
