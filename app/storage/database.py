from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from app.storage.models import Comment


SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._lock, self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_info (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS comments (
                    id INTEGER PRIMARY KEY,
                    feed_id TEXT NOT NULL,
                    comment_id TEXT NOT NULL,
                    parent_comment_id TEXT,
                    comment_type TEXT NOT NULL CHECK(comment_type IN ('comment', 'reply')),
                    content TEXT NOT NULL DEFAULT '',
                    note_url TEXT NOT NULL,
                    created_at TEXT,
                    author_id TEXT,
                    scan_status TEXT NOT NULL DEFAULT 'discovered',
                    delete_status TEXT NOT NULL DEFAULT 'pending'
                        CHECK(delete_status IN ('pending', 'deleted', 'failed', 'skipped')),
                    discovered_at TEXT NOT NULL,
                    deleted_at TEXT,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    UNIQUE(feed_id, comment_id)
                );
                CREATE TABLE IF NOT EXISTS app_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_comments_delete_status
                    ON comments(delete_status, id);
                """
            )
            db.execute(
                "INSERT INTO schema_info(key, value) VALUES('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(SCHEMA_VERSION),),
            )

    def upsert_comment(self, comment: Comment) -> bool:
        with self._lock, self.connect() as db:
            cursor = db.execute(
                """
                INSERT INTO comments(
                    feed_id, comment_id, parent_comment_id, comment_type, content,
                    note_url, created_at, author_id, scan_status, delete_status, discovered_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(feed_id, comment_id) DO UPDATE SET
                    parent_comment_id=excluded.parent_comment_id,
                    content=excluded.content,
                    note_url=excluded.note_url,
                    created_at=COALESCE(excluded.created_at, comments.created_at),
                    author_id=COALESCE(excluded.author_id, comments.author_id),
                    scan_status=excluded.scan_status
                """,
                (
                    comment.feed_id, comment.comment_id, comment.parent_comment_id,
                    comment.comment_type, comment.content[:4000], comment.note_url,
                    comment.created_at, comment.author_id, comment.scan_status,
                    comment.delete_status, comment.discovered_at or utc_now(),
                ),
            )
            return cursor.rowcount > 0

    def get_next_pending(self) -> Comment | None:
        with self._lock, self.connect() as db:
            row = db.execute(
                "SELECT * FROM comments WHERE delete_status='pending' ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return self._to_model(row) if row else None

    def list_comments(self, limit: int = 1000) -> list[Comment]:
        with self._lock, self.connect() as db:
            rows = db.execute("SELECT * FROM comments ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [self._to_model(row) for row in rows]

    def counts(self) -> dict[str, int]:
        result = {"discovered": 0, "pending": 0, "deleted": 0, "failed": 0, "skipped": 0}
        with self._lock, self.connect() as db:
            result["discovered"] = db.execute("SELECT COUNT(*) FROM comments").fetchone()[0]
            for row in db.execute("SELECT delete_status, COUNT(*) AS n FROM comments GROUP BY delete_status"):
                result[row["delete_status"]] = row["n"]
        return result

    def mark_deleted(self, row_id: int) -> None:
        self._update(row_id, "deleted", None, deleted_at=utc_now())

    def mark_skipped(self, row_id: int, error: str) -> None:
        self._update(row_id, "skipped", error)

    def mark_attempt_failed(self, row_id: int, error: str, max_retries: int = 3) -> str:
        with self._lock, self.connect() as db:
            row = db.execute("SELECT retry_count FROM comments WHERE id=?", (row_id,)).fetchone()
            if not row:
                return "failed"
            retries = row["retry_count"] + 1
            status = "failed" if retries >= max_retries else "pending"
            db.execute(
                "UPDATE comments SET retry_count=?, delete_status=?, last_error=? WHERE id=?",
                (retries, status, error[:1000], row_id),
            )
            return status

    def retry_failed(self) -> int:
        with self._lock, self.connect() as db:
            cursor = db.execute(
                "UPDATE comments SET delete_status='pending', retry_count=0, last_error=NULL "
                "WHERE delete_status='failed'"
            )
            return cursor.rowcount

    def set_state(self, key: str, value: str) -> None:
        with self._lock, self.connect() as db:
            db.execute(
                "INSERT INTO app_state(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value)
            )

    def get_state(self, key: str, default: str = "") -> str:
        with self._lock, self.connect() as db:
            row = db.execute("SELECT value FROM app_state WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def _update(self, row_id: int, status: str, error: str | None, deleted_at: str | None = None) -> None:
        with self._lock, self.connect() as db:
            db.execute(
                "UPDATE comments SET delete_status=?, last_error=?, deleted_at=? WHERE id=?",
                (status, error[:1000] if error else None, deleted_at, row_id),
            )

    @staticmethod
    def _to_model(row: sqlite3.Row) -> Comment:
        return Comment(**{key: row[key] for key in Comment.__dataclass_fields__})
