from __future__ import annotations

from dataclasses import dataclass

from app.storage.db import connect


@dataclass(frozen=True)
class CorrectionEntry:
    id: int
    history_id: int
    created_at: str
    raw_text: str
    polished_text: str | None
    final_edit: str


class CorrectionsStore:
    def add_correction(self, history_id: int, raw_text: str, polished_text: str | None, final_edit: str) -> int:
        with connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO corrections(history_id, raw_text, polished_text, final_edit)
                VALUES (?, ?, ?, ?)
                """,
                (history_id, raw_text, polished_text, final_edit),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def list_for_history(self, history_id: int) -> list[CorrectionEntry]:
        with connect() as connection:
            rows = connection.execute(
                """
                SELECT id, history_id, created_at, raw_text, polished_text, final_edit
                FROM corrections
                WHERE history_id = ?
                ORDER BY id DESC
                """,
                (history_id,),
            ).fetchall()
        return [_row_to_entry(row) for row in rows]


def _row_to_entry(row) -> CorrectionEntry:  # noqa: ANN001
    return CorrectionEntry(
        id=int(row["id"]),
        history_id=int(row["history_id"]),
        created_at=str(row["created_at"]),
        raw_text=str(row["raw_text"]),
        polished_text=str(row["polished_text"]) if row["polished_text"] is not None else None,
        final_edit=str(row["final_edit"]),
    )
