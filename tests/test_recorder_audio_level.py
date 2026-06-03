from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np
import sounddevice as sd

from app.config import AudioSettings
from app.core.recorder import AudioRecorder
from app.events import EventBus


class AudioRecorderLevelTests(unittest.TestCase):
    def test_audio_callback_publishes_microphone_level_while_recording(self) -> None:
        event_bus = EventBus()
        levels = []
        event_bus.subscribe("AUDIO_LEVEL", lambda payload: levels.append(payload["level"]))
        recorder = AudioRecorder(event_bus, AudioSettings())
        recorder._is_recording = True

        recorder._audio_callback(np.full((32, 1), 0.5, dtype=np.float32), 32, None, sd.CallbackFlags())

        self.assertEqual(len(levels), 1)
        self.assertAlmostEqual(levels[0], 0.5, places=2)

    def test_stop_keeps_stream_open_for_postroll_audio(self) -> None:
        event_bus = EventBus()
        stopped_payloads = []
        event_bus.subscribe("RECORDING_STOPPED", stopped_payloads.append)
        recorder = AudioRecorder(event_bus, AudioSettings())
        recorder._stream = _FakeStream()
        recorder._is_recording = True
        recorder._started_at = 0.0
        recorder._frames = [np.ones((4, 1), dtype=np.float32)]

        def append_tail(seconds: float) -> None:
            self.assertEqual(seconds, recorder._STOP_POSTROLL_SECONDS)
            recorder._audio_callback(np.full((4, 1), 0.5, dtype=np.float32), 4, None, sd.CallbackFlags())

        with patch("app.core.recorder.sleep", append_tail), patch("app.core.recorder.perf_counter", return_value=1.0):
            recorder._stop_locked()

        self.assertEqual(len(stopped_payloads), 1)
        np.testing.assert_array_equal(
            stopped_payloads[0]["audio"],
            np.array([1.0, 1.0, 1.0, 1.0, 0.5, 0.5, 0.5, 0.5], dtype=np.float32),
        )


class _FakeStream:
    def __init__(self) -> None:
        self.stopped = False
        self.closed = False

    def stop(self) -> None:
        self.stopped = True

    def close(self) -> None:
        self.closed = True
