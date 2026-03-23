from __future__ import annotations
import sqlite3
import threading
from typing import Optional, Dict, Any
from datetime import datetime, timezone

import config


def utc_iso_ms() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class DBWriter:
    def __init__(self, path: str, max_events: int):
        self.path = path
        self.max_events = int(max_events)
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None
        self._inserts = 0

    def open(self) -> None:
        with self._lock:
            if self._conn:
                return
            self._conn = sqlite3.connect(self.path, check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  ts_utc TEXT NOT NULL,
                  severity TEXT NOT NULL,
                  type TEXT NOT NULL,
                  message TEXT NOT NULL,
                  suppressed INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            if self._conn:
                self._conn.commit()
                self._conn.close()
                self._conn = None

    def insert_event(self, ts_utc: str, severity: str, type_: str, message: str, suppressed: bool) -> None:
        if not self._conn:
            return
        with self._lock:
            assert self._conn is not None
            self._conn.execute(
                "INSERT INTO events(ts_utc,severity,type,message,suppressed) VALUES (?,?,?,?,?)",
                (ts_utc, severity, type_, message, 1 if suppressed else 0),
            )
            self._conn.commit()
            self._inserts += 1

            if self.max_events > 0 and (self._inserts % config.DB_TRIM_EVERY_N_INSERTS == 0):
                self.trim_events()

    def trim_events(self) -> None:
        if not self._conn or self.max_events <= 0:
            return
        with self._lock:
            assert self._conn is not None
            # keep newest max_events by id
            self._conn.execute(
                """
                DELETE FROM events
                WHERE id NOT IN (
                  SELECT id FROM events ORDER BY id DESC LIMIT ?
                )
                """,
                (self.max_events,),
            )
            self._conn.commit()

    def meta(self) -> Dict[str, Any]:
        return {
            "db_path": self.path,
            "db_max_events": self.max_events,
        }
