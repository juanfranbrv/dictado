from __future__ import annotations

from dataclasses import dataclass

from app.storage.db import connect


@dataclass(frozen=True)
class VocabularyTerm:
    id: int
    term: str
    language: str
    weight: int
    enabled: bool


class VocabularyStore:
    def list_terms(self, include_disabled: bool = True) -> list[VocabularyTerm]:
        query = "SELECT id, term, language, weight, enabled FROM vocabulary_terms"
        params: tuple = ()
        if not include_disabled:
            query += " WHERE enabled = 1"
        query += " ORDER BY enabled DESC, weight DESC, term COLLATE NOCASE"
        with connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [_row_to_term(row) for row in rows]

    def terms_for_language(self, language: str | None, limit: int = 80) -> list[str]:
        language = (language or "auto").lower()
        with connect() as connection:
            rows = connection.execute(
                """
                SELECT term
                FROM vocabulary_terms
                WHERE enabled = 1
                  AND (language = 'auto' OR language = ?)
                ORDER BY weight DESC, term COLLATE NOCASE
                LIMIT ?
                """,
                (language, limit),
            ).fetchall()
        return [str(row["term"]) for row in rows]

    def add_term(self, term: str, language: str = "auto", weight: int = 10, enabled: bool = True) -> None:
        normalized = term.strip()
        if not normalized:
            return
        with connect() as connection:
            connection.execute(
                """
                INSERT INTO vocabulary_terms(term, language, weight, enabled)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(term) DO UPDATE SET
                    language = excluded.language,
                    weight = excluded.weight,
                    enabled = excluded.enabled,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (normalized, _normalize_language(language), int(weight), int(enabled)),
            )
            connection.commit()

    def update_term(self, term_id: int, term: str, language: str, weight: int, enabled: bool) -> None:
        normalized = term.strip()
        if not normalized:
            return
        with connect() as connection:
            connection.execute(
                """
                UPDATE vocabulary_terms
                SET term = ?, language = ?, weight = ?, enabled = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (normalized, _normalize_language(language), int(weight), int(enabled), term_id),
            )
            connection.commit()

    def delete_term(self, term_id: int) -> None:
        with connect() as connection:
            connection.execute("DELETE FROM vocabulary_terms WHERE id = ?", (term_id,))
            connection.commit()


def _row_to_term(row) -> VocabularyTerm:  # noqa: ANN001
    return VocabularyTerm(
        id=int(row["id"]),
        term=str(row["term"]),
        language=str(row["language"]),
        weight=int(row["weight"]),
        enabled=bool(row["enabled"]),
    )


def _normalize_language(language: str) -> str:
    normalized = language.strip().lower()
    if normalized not in {"auto", "es", "en"}:
        return "auto"
    return normalized
