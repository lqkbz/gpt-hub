"""SQLite 持久化：群策略、计数、语音开关、研究任务。"""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass, field
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS group_policy (
    group_id TEXT PRIMARY KEY,
    model TEXT,
    effort TEXT,
    features TEXT NOT NULL DEFAULT '{}',
    chat_enabled INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS counter (
    key TEXT NOT NULL,
    day TEXT NOT NULL,
    value INTEGER NOT NULL,
    PRIMARY KEY (key, day)
);
CREATE TABLE IF NOT EXISTS voice_session (
    umo TEXT PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS research_job (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    umo TEXT NOT NULL,
    requester TEXT NOT NULL,
    topic TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at REAL NOT NULL,
    finished_at REAL,
    report_path TEXT,
    error TEXT
);
"""

_UNFINISHED = ("queued", "running")


@dataclass
class GroupPolicy:
    group_id: str
    model: str | None = None
    effort: str | None = None
    features: dict[str, int] = field(default_factory=dict)
    chat_enabled: bool = True


@dataclass
class ResearchJob:
    id: int
    umo: str
    requester: str
    topic: str
    status: str
    created_at: float
    finished_at: float | None
    report_path: str | None
    error: str | None


_JOB_COLS = "id, umo, requester, topic, status, created_at, finished_at, report_path, error"


class Store:
    def __init__(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(_SCHEMA)
            self._db.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def _query(self, sql: str, args: tuple = ()) -> list[tuple]:
        with self._lock:
            return self._db.execute(sql, args).fetchall()

    def _write(self, sql: str, args: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._db.execute(sql, args)
            self._db.commit()
            return cur

    # 群策略

    def get_policy(self, group_id: str) -> GroupPolicy:
        rows = self._query(
            "SELECT model, effort, features, chat_enabled FROM group_policy WHERE group_id = ?",
            (group_id,),
        )
        if not rows:
            return GroupPolicy(group_id=group_id)
        model, effort, features, chat_enabled = rows[0]
        return GroupPolicy(group_id, model, effort, json.loads(features), bool(chat_enabled))

    def save_policy(self, p: GroupPolicy) -> None:
        self._write(
            "INSERT OR REPLACE INTO group_policy (group_id, model, effort, features, chat_enabled)"
            " VALUES (?, ?, ?, ?, ?)",
            (p.group_id, p.model, p.effort, json.dumps(p.features), int(p.chat_enabled)),
        )

    # 计数

    def incr_counter(self, key: str, day: str, amount: int = 1) -> int:
        with self._lock:
            self._db.execute(
                "INSERT INTO counter (key, day, value) VALUES (?, ?, ?)"
                " ON CONFLICT (key, day) DO UPDATE SET value = value + excluded.value",
                (key, day, amount),
            )
            self._db.commit()
            return self._db.execute(
                "SELECT value FROM counter WHERE key = ? AND day = ?", (key, day)
            ).fetchone()[0]

    def get_counter(self, key: str, day: str) -> int:
        rows = self._query("SELECT value FROM counter WHERE key = ? AND day = ?", (key, day))
        return rows[0][0] if rows else 0

    # 语音开关

    def set_voice(self, umo: str, on: bool) -> None:
        if on:
            self._write("INSERT OR IGNORE INTO voice_session (umo) VALUES (?)", (umo,))
        else:
            self._write("DELETE FROM voice_session WHERE umo = ?", (umo,))

    def is_voice(self, umo: str) -> bool:
        return bool(self._query("SELECT 1 FROM voice_session WHERE umo = ?", (umo,)))

    # 研究任务

    def create_job(self, umo: str, requester: str, topic: str, now: float) -> ResearchJob:
        cur = self._write(
            "INSERT INTO research_job (umo, requester, topic, status, created_at)"
            " VALUES (?, ?, ?, 'queued', ?)",
            (umo, requester, topic, now),
        )
        return self.get_job(cur.lastrowid)

    def update_job(
        self,
        job_id: int,
        *,
        status: str | None = None,
        finished_at: float | None = None,
        report_path: str | None = None,
        error: str | None = None,
    ) -> None:
        fields = {
            k: v
            for k, v in (
                ("status", status),
                ("finished_at", finished_at),
                ("report_path", report_path),
                ("error", error),
            )
            if v is not None
        }
        if not fields:
            return
        sets = ", ".join(f"{k} = ?" for k in fields)
        self._write(f"UPDATE research_job SET {sets} WHERE id = ?", (*fields.values(), job_id))

    def get_job(self, job_id: int) -> ResearchJob | None:
        rows = self._query(f"SELECT {_JOB_COLS} FROM research_job WHERE id = ?", (job_id,))
        return ResearchJob(*rows[0]) if rows else None

    def list_jobs(self, umo: str, limit: int = 5) -> list[ResearchJob]:
        rows = self._query(
            f"SELECT {_JOB_COLS} FROM research_job WHERE umo = ? ORDER BY id DESC LIMIT ?",
            (umo, limit),
        )
        return [ResearchJob(*r) for r in rows]

    def mark_unfinished_interrupted(self, now: float) -> list[ResearchJob]:
        rows = self._query(
            f"SELECT {_JOB_COLS} FROM research_job WHERE status IN (?, ?)", _UNFINISHED
        )
        jobs = [ResearchJob(*r) for r in rows]
        for j in jobs:
            self.update_job(j.id, status="interrupted", finished_at=now)
        return jobs
