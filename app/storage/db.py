from __future__ import annotations

import sqlite3
from pathlib import Path

from app.utils.paths import database_path


def connect(path: Path | None = None) -> sqlite3.Connection:
    db_path = path or database_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    _migrate(connection)
    return connection


def _migrate(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS vocabulary_terms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            term TEXT NOT NULL UNIQUE,
            language TEXT NOT NULL DEFAULT 'auto',
            weight INTEGER NOT NULL DEFAULT 10,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_vocabulary_terms_lookup
        ON vocabulary_terms(enabled, language, weight DESC, term)
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS history_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            raw_text TEXT NOT NULL,
            polished_text TEXT,
            final_text TEXT NOT NULL,
            language TEXT,
            language_confidence REAL,
            audio_duration REAL NOT NULL DEFAULT 0,
            profile TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT 'raw'
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS corrections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            history_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            raw_text TEXT NOT NULL,
            polished_text TEXT,
            final_edit TEXT NOT NULL,
            FOREIGN KEY(history_id) REFERENCES history_entries(id) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_history_created_at
        ON history_entries(created_at DESC)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_corrections_history_id
        ON corrections(history_id)
        """
    )
    connection.commit()
