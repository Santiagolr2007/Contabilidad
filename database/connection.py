from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence


class Database:
    """Pequeño adaptador para trabajar con SQLite de forma segura."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        with self.connection() as connection:
            cursor = connection.execute(sql, params)
            return int(cursor.lastrowid or 0)

    def executemany(self, sql: str, rows: Sequence[Sequence[Any]]) -> None:
        with self.connection() as connection:
            connection.executemany(sql, rows)

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        with self.connection() as connection:
            return list(connection.execute(sql, params).fetchall())

    def query_one(
        self, sql: str, params: Sequence[Any] = ()
    ) -> sqlite3.Row | None:
        with self.connection() as connection:
            return connection.execute(sql, params).fetchone()
