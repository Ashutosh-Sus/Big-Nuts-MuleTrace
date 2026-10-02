"""SQLite persistence: uploaded datasets (raw CSV), dispositions, append-only audit log.

Analysis results are derived data and are recomputed deterministically from the stored CSV.
"""
from __future__ import annotations

import hashlib
import sqlite3
import threading
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS datasets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    uploaded_at INTEGER NOT NULL,
    csv BLOB NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS dispositions (
    dataset_sha TEXT NOT NULL,
    account_id TEXT NOT NULL,
    status TEXT NOT NULL,
    note TEXT,
    analyst TEXT,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (dataset_sha, account_id)
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_sha TEXT NOT NULL,
    account_id TEXT NOT NULL,
    action TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT,
    note TEXT,
    analyst TEXT,
    at INTEGER NOT NULL
);
"""
STATUSES = ("OPEN", "CONFIRMED", "CLEARED")


class Store:
    def __init__(self, path: Path | str):
        self.path = str(path)
        self.lock = threading.Lock()
        with self._conn() as c:
            c.executescript(SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    # datasets -------------------------------------------------------------
    def add_dataset(self, name: str, data: bytes) -> dict:
        sha = hashlib.sha256(data).hexdigest()
        with self.lock, self._conn() as c:
            c.execute("UPDATE datasets SET is_active = 0")
            cur = c.execute("INSERT INTO datasets (name, sha256, uploaded_at, csv, is_active) VALUES (?, ?, ?, ?, 1)",
                            (name, sha, int(time.time()), data))
            return {"id": cur.lastrowid, "name": name, "sha256": sha}

    def active_dataset(self) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT id, name, sha256, uploaded_at, csv FROM datasets WHERE is_active = 1 "
                            "ORDER BY id DESC LIMIT 1").fetchone()
        return dict(row) if row else None

    # dispositions ---------------------------------------------------------
    def dispositions(self, sha: str) -> dict[str, dict]:
        with self._conn() as c:
            rows = c.execute("SELECT account_id, status, note, analyst, updated_at FROM dispositions "
                             "WHERE dataset_sha = ?", (sha,)).fetchall()
        return {r["account_id"]: dict(r) for r in rows}

    def set_disposition(self, sha: str, account: str, status: str, note: str, analyst: str) -> dict:
        if status not in STATUSES:
            raise ValueError(f"status must be one of {', '.join(STATUSES)}")
        now = int(time.time())
        with self.lock, self._conn() as c:
            prev = c.execute("SELECT status FROM dispositions WHERE dataset_sha = ? AND account_id = ?",
                             (sha, account)).fetchone()
            from_status = prev["status"] if prev else "OPEN"
            c.execute("INSERT INTO dispositions (dataset_sha, account_id, status, note, analyst, updated_at) "
                      "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(dataset_sha, account_id) DO UPDATE SET "
                      "status = excluded.status, note = excluded.note, analyst = excluded.analyst, "
                      "updated_at = excluded.updated_at", (sha, account, status, note, analyst, now))
            c.execute("INSERT INTO audit_log (dataset_sha, account_id, action, from_status, to_status, note, analyst, at) "
                      "VALUES (?, ?, 'DISPOSITION', ?, ?, ?, ?, ?)", (sha, account, from_status, status, note, analyst, now))
        return {"account_id": account, "status": status, "note": note, "analyst": analyst, "updated_at": now}

    def audit(self, sha: str, account: str | None = None, limit: int = 200) -> list[dict]:
        q = "SELECT * FROM audit_log WHERE dataset_sha = ?"
        args: list = [sha]
        if account:
            q += " AND account_id = ?"
            args.append(account)
        q += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        with self._conn() as c:
            return [dict(r) for r in c.execute(q, args).fetchall()]

    def clear_dispositions(self, sha: str, analyst: str) -> None:
        """Every decision returns to OPEN. The audit log stays append-only: each account whose decision is
        cleared gets its own RESET entry, so its history ends in the state the account is actually in."""
        now = int(time.time())
        with self.lock, self._conn() as c:
            rows = c.execute("SELECT account_id, status FROM dispositions WHERE dataset_sha = ? AND status != 'OPEN' "
                             "ORDER BY account_id", (sha,)).fetchall()
            for r in rows:
                c.execute("INSERT INTO audit_log (dataset_sha, account_id, action, from_status, to_status, note, "
                          "analyst, at) VALUES (?, ?, 'RESET', ?, 'OPEN', 'demo reset', ?, ?)",
                          (sha, r["account_id"], r["status"], analyst, now))
            c.execute("DELETE FROM dispositions WHERE dataset_sha = ?", (sha,))
            c.execute("INSERT INTO audit_log (dataset_sha, account_id, action, from_status, to_status, note, analyst, at) "
                      "VALUES (?, '*', 'RESET', NULL, 'OPEN', 'demo reset', ?, ?)", (sha, analyst, now))
