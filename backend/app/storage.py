"""报警事件持久化（SQLite）。"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .config import DB_PATH

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            REAL    NOT NULL,
    created_at    TEXT    NOT NULL,
    level         TEXT    NOT NULL,
    source        TEXT    NOT NULL,
    cls           TEXT,
    label         TEXT,
    conf          REAL    NOT NULL DEFAULT 0,
    fire_count    INTEGER NOT NULL DEFAULT 0,
    smoke_count   INTEGER NOT NULL DEFAULT 0,
    snapshot      TEXT,
    message       TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_ts     ON events(ts DESC);
CREATE INDEX IF NOT EXISTS idx_events_source ON events(source);
CREATE INDEX IF NOT EXISTS idx_events_level  ON events(level);
"""


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")


class EventStore:
    """线程安全的事件表。每次操作独立开连接，避免跨线程共享 sqlite 句柄。"""

    def __init__(self, path: Path = DB_PATH) -> None:
        self._path = path
        self._lock = threading.RLock()
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init(self) -> None:
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as conn:
                conn.executescript(_SCHEMA)

    # ------------------------------------------------------------ 写入
    def add(
        self,
        *,
        level: str,
        source: str,
        cls: str | None,
        label: str | None,
        conf: float,
        counts: dict[str, int] | None = None,
        snapshot: str | None = None,
        message: str | None = None,
        ts: float | None = None,
    ) -> dict[str, Any]:
        ts = float(ts or time.time())
        counts = counts or {}
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO events (ts, created_at, level, source, cls, label, conf,
                                    fire_count, smoke_count, snapshot, message)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    ts,
                    _iso(ts),
                    level,
                    source,
                    cls,
                    label,
                    float(conf),
                    int(counts.get("fire", 0)),
                    int(counts.get("smoke", 0)),
                    snapshot,
                    message,
                ),
            )
            event_id = int(cur.lastrowid)
        logger.info("新增报警事件 #%s：%s/%s conf=%.2f", event_id, source, cls, conf)
        return self.get(event_id)  # type: ignore[return-value]

    # ------------------------------------------------------------ 查询
    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "created_at": row["created_at"],
            "level": row["level"],
            "source": row["source"],
            "cls": row["cls"],
            "label": row["label"],
            "conf": round(float(row["conf"]), 4),
            "counts": {"fire": row["fire_count"], "smoke": row["smoke_count"]},
            "snapshot_url": f"/static/snapshots/{row['snapshot']}" if row["snapshot"] else None,
            "message": row["message"],
        }

    def get(self, event_id: int) -> dict[str, Any] | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        return self._row_to_dict(row) if row else None

    def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        level: str | None = None,
        source: str | None = None,
        cls: str | None = None,
    ) -> dict[str, Any]:
        where, params = [], []
        if level:
            where.append("level = ?")
            params.append(level)
        if source:
            where.append("source = ?")
            params.append(source)
        if cls:
            where.append("cls = ?")
            params.append(cls)
        clause = f"WHERE {' AND '.join(where)}" if where else ""

        with self._lock, self._connect() as conn:
            total = conn.execute(f"SELECT COUNT(*) AS c FROM events {clause}", params).fetchone()["c"]
            rows = conn.execute(
                f"SELECT * FROM events {clause} ORDER BY ts DESC LIMIT ? OFFSET ?",
                (*params, limit, offset),
            ).fetchall()
        return {
            "total": int(total),
            "limit": limit,
            "offset": offset,
            "items": [self._row_to_dict(r) for r in rows],
        }

    def stats(self, hours: int = 24) -> dict[str, Any]:
        since = time.time() - hours * 3600
        with self._lock, self._connect() as conn:
            overall = conn.execute(
                """
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN cls IN ('fire','flame') THEN 1 ELSE 0 END) AS fire,
                       SUM(CASE WHEN cls = 'smoke' THEN 1 ELSE 0 END)           AS smoke,
                       SUM(CASE WHEN level='critical' THEN 1 ELSE 0 END)        AS critical,
                       SUM(CASE WHEN level='warning'  THEN 1 ELSE 0 END)        AS warning
                FROM events
                """
            ).fetchone()
            recent = conn.execute(
                "SELECT COUNT(*) AS c FROM events WHERE ts >= ?", (since,)
            ).fetchone()["c"]
            by_source = conn.execute(
                "SELECT source, COUNT(*) AS c FROM events GROUP BY source ORDER BY c DESC"
            ).fetchall()
            by_hour_rows = conn.execute(
                "SELECT ts, cls FROM events WHERE ts >= ?", (since,)
            ).fetchall()
            latest_row = conn.execute("SELECT * FROM events ORDER BY ts DESC LIMIT 1").fetchone()

        # 按整点分桶，补齐没有数据的时段，前端画图不用再补
        buckets: dict[str, dict[str, int]] = {}
        now = datetime.now().astimezone()
        for i in range(hours - 1, -1, -1):
            slot = (now - timedelta(hours=i)).replace(minute=0, second=0, microsecond=0)
            buckets[slot.isoformat(timespec="seconds")] = {"fire": 0, "smoke": 0}
        for row in by_hour_rows:
            slot = (
                datetime.fromtimestamp(row["ts"])
                .astimezone()
                .replace(minute=0, second=0, microsecond=0)
                .isoformat(timespec="seconds")
            )
            if slot not in buckets:
                buckets[slot] = {"fire": 0, "smoke": 0}
            key = "fire" if row["cls"] in ("fire", "flame") else "smoke"
            buckets[slot][key] += 1

        by_hour = [{"t": t, "fire": v["fire"], "smoke": v["smoke"]} for t, v in sorted(buckets.items())]

        return {
            "total": int(overall["total"] or 0),
            "fire": int(overall["fire"] or 0),
            "smoke": int(overall["smoke"] or 0),
            "critical": int(overall["critical"] or 0),
            "warning": int(overall["warning"] or 0),
            "recent": int(recent or 0),
            "by_hour": by_hour,
            "by_source": [{"source": r["source"], "count": int(r["c"])} for r in by_source],
            "latest": self._row_to_dict(latest_row) if latest_row else None,
        }

    # ------------------------------------------------------------ 删除
    def delete(self, event_id: int) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM events WHERE id=?", (event_id,))
            return cur.rowcount > 0

    def clear(self) -> int:
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM events")
            conn.execute("DELETE FROM sqlite_sequence WHERE name='events'")
            return cur.rowcount


event_store = EventStore()
