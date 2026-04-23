from __future__ import annotations

from dataclasses import dataclass

from app.storage.db import connect


@dataclass(frozen=True)
class HistoryEntry:
    id: int
    created_at: str
    raw_text: str
    polished_text: str | None
    final_text: str
    language: str | None
    language_confidence: float | None
    audio_duration: float
    profile: str
    source: str


class HistoryStore:
    def add_entry(
        self,
        *,
        raw_text: str,
        polished_text: str | None,
        final_text: str,
        language: str | None,
        language_confidence: float | None,
        audio_duration: float,
        profile: str,
        source: str,
    ) -> int:
        with connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO history_entries(
                    raw_text, polished_text, final_text, language, language_confidence, audio_duration, profile, source
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    raw_text,
                    polished_text,
                    final_text,
                    language,
                    language_confidence,
                    float(audio_duration),
                    profile,
                    source,
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def list_entries(self, limit: int = 200) -> list[HistoryEntry]:
        with connect() as connection:
            rows = connection.execute(
                """
                SELECT id, created_at, raw_text, polished_text, final_text, language,
                       language_confidence, audio_duration, profile, source
                FROM history_entries
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_row_to_entry(row) for row in rows]

    def get_entry(self, entry_id: int) -> HistoryEntry | None:
        with connect() as connection:
            row = connection.execute(
                """
                SELECT id, created_at, raw_text, polished_text, final_text, language,
                       language_confidence, audio_duration, profile, source
                FROM history_entries
                WHERE id = ?
                """,
                (entry_id,),
            ).fetchone()
        return _row_to_entry(row) if row is not None else None


def _row_to_entry(row) -> HistoryEntry:  # noqa: ANN001
    return HistoryEntry(
        id=int(row["id"]),
        created_at=str(row["created_at"]),
        raw_text=str(row["raw_text"]),
        polished_text=str(row["polished_text"]) if row["polished_text"] is not None else None,
        final_text=str(row["final_text"]),
        language=str(row["language"]) if row["language"] is not None else None,
        language_confidence=float(row["language_confidence"]) if row["language_confidence"] is not None else None,
        audio_duration=float(row["audio_duration"]),
        profile=str(row["profile"]),
        source=str(row["source"]),
    )
