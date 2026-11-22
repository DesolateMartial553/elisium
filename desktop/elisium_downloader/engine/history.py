"""Download history in SQLite (stdlib only).

One row per download: the URL, its dedupe ``video_key``, the title yt-dlp
reported, the queue state from ``core-spec/SPEC.md``, an error code plus
plain-language message, the finished file path, and timestamps.

Every value goes through a bound parameter; no SQL is ever built from user
text. ``LIKE`` searches escape ``%``, ``_`` and ``\\`` so a title containing
wildcards matches literally.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

__all__ = ["History", "STATES", "TERMINAL_STATES"]

# Queue states from the spec. Anything else is a typo, so it is rejected.
STATES: frozenset[str] = frozenset(
    {
        "queued",
        "probing",
        "downloading",
        "merging",
        "converting",
        "paused",
        "done",
        "failed",
        "skipped",
        "cancelled",
    }
)
TERMINAL_STATES: frozenset[str] = frozenset({"done", "failed", "skipped", "cancelled"})

_SCHEMA = """
CREATE TABLE IF NOT EXISTS downloads (
    id INTEGER PRIMARY KEY,
    url TEXT NOT NULL,
    video_key TEXT,
    title TEXT,
    state TEXT NOT NULL,
    error_code TEXT,
    error_message TEXT,
    file_path TEXT,
    created_at TEXT NOT NULL,
    finished_at TEXT,
    note TEXT,
    files_total INTEGER
)
"""
# Columns added after the first release: an older file gets them on open.
_ADDED_COLUMNS = (("note", "TEXT"), ("files_total", "INTEGER"))

_COLUMNS = (
    "id",
    "url",
    "video_key",
    "title",
    "state",
    "error_code",
    "error_message",
    "file_path",
    "created_at",
    "finished_at",
    "note",
    "files_total",
)


def _now() -> str:
    """Current UTC time as an ISO 8601 string (seconds resolution)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _check_state(state: str) -> str:
    if not isinstance(state, str) or state not in STATES:
        raise ValueError(f"unknown state: {state!r}")
    return state


def _like(text: str) -> str:
    """Wrap *text* in wildcards, escaping LIKE's own metacharacters."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return None if row is None else {column: row[column] for column in _COLUMNS}


class History:
    """The ``downloads`` table in *db_path* (created if missing)."""

    def __init__(self, db_path: str | os.PathLike[str]) -> None:
        self.path = Path(db_path).expanduser()
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            str(self.path), check_same_thread=False, isolation_level=None
        )
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute(_SCHEMA)
            have = {r["name"] for r in self._conn.execute("PRAGMA table_info(downloads)")}
            for name, kind in _ADDED_COLUMNS:
                if name not in have:
                    self._conn.execute(f"ALTER TABLE downloads ADD COLUMN {name} {kind}")

    # -- plumbing --------------------------------------------------------
    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> History:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _write(self, sql: str, params: Sequence[Any]) -> tuple[int, int]:
        """Run one statement in a transaction; returns ``(lastrowid, rowcount)``."""
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                cursor = self._conn.execute(sql, params)
                result = (int(cursor.lastrowid or 0), cursor.rowcount)
                self._conn.execute("COMMIT")
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            return result

    def _query(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    # -- public API ------------------------------------------------------
    def add(
        self,
        url: str,
        *,
        video_key: str | None = None,
        title: str | None = None,
        state: str = "queued",
        error_code: str | None = None,
        error_message: str | None = None,
        file_path: str | None = None,
        created_at: str | None = None,
        note: str | None = None,
        files_total: int | None = None,
    ) -> int:
        """Insert one download and return its row id."""
        if not isinstance(url, str) or not url.strip():
            raise ValueError("url must be a non-empty string")
        _check_state(state)
        cursor_id, _ = self._write(
            "INSERT INTO downloads"
            " (url, video_key, title, state, error_code, error_message,"
            "  file_path, created_at, finished_at, note, files_total)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                url.strip(),
                video_key,
                title,
                state,
                error_code,
                error_message,
                file_path,
                created_at or _now(),
                _now() if state in TERMINAL_STATES else None,
                note,
                files_total,
            ),
        )
        return cursor_id

    def update_state(
        self,
        record_id: int,
        state: str,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
        file_path: str | None = None,
        clear_error: bool = False,
        note: str | None = None,
        clear_note: bool = False,
        files_total: int | None = None,
    ) -> bool:
        """Move one download to *state*. Returns ``False`` for an unknown id.

        ``error_code``, ``error_message`` and ``file_path`` are only written
        when not ``None``; pass ``clear_error=True`` to reset the two error
        columns (a retry or a success after a failure). ``note`` (a short remark on a
        finished item, brief 10C) works like ``file_path``; ``clear_note`` resets it.
        ``finished_at`` is
        stamped for a terminal state and cleared when the item becomes active
        again.
        """
        _check_state(state)
        assignments = ["state = ?"]
        params: list[Any] = [state]
        if error_code is not None:
            assignments.append("error_code = ?")
            params.append(error_code)
        if error_message is not None:
            assignments.append("error_message = ?")
            params.append(error_message)
        if clear_error:
            assignments.append("error_code = NULL")
            assignments.append("error_message = NULL")
        if file_path is not None:
            assignments.append("file_path = ?")
            params.append(file_path)
        if note is not None:
            assignments.append("note = ?")
            params.append(note)
        elif clear_note:
            assignments.append("note = NULL")
        if files_total is not None:
            assignments.append("files_total = ?")
            params.append(int(files_total))
        if state in TERMINAL_STATES:
            assignments.append("finished_at = COALESCE(finished_at, ?)")
            params.append(_now())
        else:
            assignments.append("finished_at = NULL")
        params.append(record_id)
        # The SET list is assembled from fixed column names, never from values;
        # every value below is a bound parameter.
        _, changed = self._write(
            f"UPDATE downloads SET {', '.join(assignments)} WHERE id = ?",
            params,
        )
        return changed > 0

    def get(self, record_id: int) -> dict[str, Any] | None:
        """Return one download as a dict, or ``None``."""
        rows = self._query("SELECT * FROM downloads WHERE id = ?", (record_id,))
        return _row(rows[0]) if rows else None

    def search(self, text: str, limit: int | None = 200) -> list[dict[str, Any]]:
        """Rows whose URL, video key or title contains *text* (literal).

        Blank text searches nothing and returns ``[]``. Newest first.
        """
        needle = (text or "").strip()
        if not needle:
            return []
        if limit is not None and limit <= 0:
            return []
        pattern = _like(needle)
        sql = (
            "SELECT * FROM downloads"
            " WHERE url LIKE ? ESCAPE '\\'"
            "    OR video_key LIKE ? ESCAPE '\\'"
            "    OR title LIKE ? ESCAPE '\\'"
            " ORDER BY id DESC"
        )
        params: list[Any] = [pattern, pattern, pattern]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        return [
            {column: row[column] for column in _COLUMNS}
            for row in self._query(sql, params)
        ]

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        """The *limit* newest rows, newest first."""
        if limit <= 0:
            return []
        rows = self._query(
            "SELECT * FROM downloads ORDER BY id DESC LIMIT ?", (int(limit),)
        )
        return [{column: row[column] for column in _COLUMNS} for row in rows]

    def delete(self, record_id: int) -> bool:
        """Remove one row. Returns ``False`` if the id was not there."""
        _, changed = self._write("DELETE FROM downloads WHERE id = ?", (record_id,))
        return changed > 0
