from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from .config import settings
from .models import assert_transition, dedupe_key


SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS hotspots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT,
    heat TEXT,
    tags TEXT NOT NULL DEFAULT '',
    dedupe_key TEXT NOT NULL UNIQUE,
    fetched_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    core_theme TEXT NOT NULL,
    content_format TEXT NOT NULL,
    selected_hotspot_ids TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    title_options TEXT NOT NULL,
    selected_title TEXT NOT NULL,
    body TEXT NOT NULL,
    tags TEXT NOT NULL,
    cover_text TEXT NOT NULL,
    video_script TEXT NOT NULL,
    risk_notes TEXT NOT NULL,
    cta TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(topic_id) REFERENCES topics(id)
);

CREATE TABLE IF NOT EXISTS assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    path TEXT NOT NULL,
    description TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(draft_id) REFERENCES drafts(id)
);

CREATE TABLE IF NOT EXISTS schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id INTEGER NOT NULL,
    scheduled_at TEXT NOT NULL,
    timezone TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(draft_id) REFERENCES drafts(id)
);

CREATE TABLE IF NOT EXISTS publish_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id INTEGER NOT NULL,
    schedule_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    notes TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(draft_id) REFERENCES drafts(id),
    FOREIGN KEY(schedule_id) REFERENCES schedules(id)
);
"""


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def loads(value: str, fallback: Any = None) -> Any:
    if value is None:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


@contextmanager
def connect(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    path = db_path or settings.db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: Path | None = None) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)


class Store:
    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or settings.db_path
        init_db(self.db_path)

    def add_hotspot(self, source: str, title: str, url: str = "", heat: str = "", tags: str = "") -> int:
        timestamp = now_iso()
        key = dedupe_key(source, title)
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO hotspots
                (source, title, url, heat, tags, dedupe_key, fetched_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (source, title, url, heat, tags, key, timestamp, timestamp),
            )
            row = conn.execute("SELECT id FROM hotspots WHERE dedupe_key = ?", (key,)).fetchone()
            return int(row["id"])

    def list_hotspots(self, limit: int = 20) -> list[dict[str, Any]]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM hotspots ORDER BY fetched_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [row_to_dict(row) for row in rows]

    def create_topic(self, core_theme: str, content_format: str, hotspot_ids: list[int]) -> int:
        with connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO topics (core_theme, content_format, selected_hotspot_ids, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (core_theme, content_format, dumps(hotspot_ids), now_iso()),
            )
            return int(cursor.lastrowid)

    def get_topic(self, topic_id: int) -> dict[str, Any]:
        with connect(self.db_path) as conn:
            row = conn.execute("SELECT * FROM topics WHERE id = ?", (topic_id,)).fetchone()
            if row is None:
                raise KeyError(f"Topic not found: {topic_id}")
            item = row_to_dict(row)
            item["selected_hotspot_ids"] = loads(item["selected_hotspot_ids"], [])
            return item

    def create_draft(self, topic_id: int, content: dict[str, Any]) -> int:
        timestamp = now_iso()
        with connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO drafts
                (topic_id, status, title_options, selected_title, body, tags, cover_text,
                 video_script, risk_notes, cta, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    topic_id,
                    "drafted",
                    dumps(content["title_options"]),
                    content["selected_title"],
                    content["body"],
                    dumps(content["tags"]),
                    content["cover_text"],
                    dumps(content["video_script"]),
                    dumps(content["risk_notes"]),
                    content["cta"],
                    timestamp,
                    timestamp,
                ),
            )
            return int(cursor.lastrowid)

    def list_drafts(self, limit: int = 20) -> list[dict[str, Any]]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT drafts.*, topics.core_theme, topics.content_format
                FROM drafts
                JOIN topics ON topics.id = drafts.topic_id
                ORDER BY drafts.updated_at DESC, drafts.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [self._expand_draft(row_to_dict(row)) for row in rows]

    def get_draft(self, draft_id: int) -> dict[str, Any]:
        with connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT drafts.*, topics.core_theme, topics.content_format
                FROM drafts
                JOIN topics ON topics.id = drafts.topic_id
                WHERE drafts.id = ?
                """,
                (draft_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Draft not found: {draft_id}")
            return self._expand_draft(row_to_dict(row))

    def update_draft_status(self, draft_id: int, target_status: str) -> None:
        draft = self.get_draft(draft_id)
        assert_transition(draft["status"], target_status)
        with connect(self.db_path) as conn:
            conn.execute(
                "UPDATE drafts SET status = ?, updated_at = ? WHERE id = ?",
                (target_status, now_iso(), draft_id),
            )

    def add_asset(self, draft_id: int, kind: str, path: str, description: str) -> int:
        with connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO assets (draft_id, kind, path, description, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (draft_id, kind, path, description, now_iso()),
            )
            return int(cursor.lastrowid)

    def list_assets(self, draft_id: int) -> list[dict[str, Any]]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM assets WHERE draft_id = ? ORDER BY id ASC",
                (draft_id,),
            ).fetchall()
            return [row_to_dict(row) for row in rows]

    def create_schedule(self, draft_id: int, scheduled_at: str, timezone: str) -> int:
        with connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO schedules (draft_id, scheduled_at, timezone, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (draft_id, scheduled_at, timezone, now_iso()),
            )
            return int(cursor.lastrowid)

    def list_schedules(self, limit: int = 20) -> list[dict[str, Any]]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT schedules.*, drafts.selected_title, drafts.status
                FROM schedules
                JOIN drafts ON drafts.id = schedules.draft_id
                ORDER BY schedules.scheduled_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [row_to_dict(row) for row in rows]

    def get_schedule(self, schedule_id: int) -> dict[str, Any]:
        with connect(self.db_path) as conn:
            row = conn.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,)).fetchone()
            if row is None:
                raise KeyError(f"Schedule not found: {schedule_id}")
            return row_to_dict(row)

    def create_publish_job(self, draft_id: int, schedule_id: int, status: str, notes: str) -> int:
        timestamp = now_iso()
        with connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO publish_jobs
                (draft_id, schedule_id, status, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (draft_id, schedule_id, status, notes, timestamp, timestamp),
            )
            return int(cursor.lastrowid)

    def _expand_draft(self, draft: dict[str, Any]) -> dict[str, Any]:
        draft["title_options"] = loads(draft["title_options"], [])
        draft["tags"] = loads(draft["tags"], [])
        draft["video_script"] = loads(draft["video_script"], [])
        draft["risk_notes"] = loads(draft["risk_notes"], [])
        return draft

