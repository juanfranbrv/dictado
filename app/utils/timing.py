from __future__ import annotations

from dataclasses import dataclass

from loguru import logger


@dataclass
class SessionTiming:
    record: float = 0.0
    stt: float = 0.0
    polish: float = 0.0
    inject: float = 0.0

    @property
    def total(self) -> float:
        return self.record + self.stt + self.polish + self.inject


class TimingCollector:
    def __init__(self) -> None:
        self._sessions: dict[int, SessionTiming] = {}

    def set_stage(self, session_id: int, stage: str, seconds: float) -> None:
        session = self._sessions.setdefault(session_id, SessionTiming())
        if stage == "record":
            session.record = seconds
        elif stage == "stt":
            session.stt = seconds
        elif stage == "polish":
            session.polish = seconds
        elif stage == "inject":
            session.inject = seconds

    def log_summary(self, session_id: int, profile: str, source: str) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            return
        logger.info(
            "[timing] session={} profile={} source={} total={:.2f}s record={:.2f}s stt={:.2f}s polish={:.2f}s inject={:.2f}s",
            session_id,
            profile,
            source,
            session.total,
            session.record,
            session.stt,
            session.polish,
            session.inject,
        )
        self._sessions.pop(session_id, None)
