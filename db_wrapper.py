"""
Обёртка над SQLite для хранения интересов клиентов (интеграционные тесты и прод-расширение).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class SQLiteClientInterestsStore:
    """Хранилище интересов клиентов в SQLite."""

    def __init__(self, db_path: str | Path, *, check_same_thread: bool = True) -> None:
        self._path = str(db_path)
        self._conn = sqlite3.connect(self._path, check_same_thread=check_same_thread)
        self._conn.row_factory = sqlite3.Row

    def init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS client_interests (
                client_id INTEGER PRIMARY KEY,
                interests_json TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> SQLiteClientInterestsStore:
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()

    def set_interests(self, client_id: int, interests: list[str]) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO client_interests (client_id, interests_json)
            VALUES (?, ?)
            """,
            (client_id, json.dumps(interests)),
        )
        self._conn.commit()

    def get_interests(self, client_id: int) -> list[str] | None:
        row = self._conn.execute(
            "SELECT interests_json FROM client_interests WHERE client_id = ?",
            (client_id,),
        ).fetchone()
        if row is None:
            return None
        return json.loads(row["interests_json"])
