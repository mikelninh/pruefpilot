from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import settings


class SQLiteStore:
    """Small persistence boundary for the demo and controlled pilot.

    Tenant IDs are persisted on every mutable record. Locally this is durable SQLite. On serverless
    Vercel `/tmp` is instance-local, so production readiness remains blocked until an external durable
    store (for example Postgres) implements the same tenant-scoped contract.
    """

    tenant_scoped = True

    def __init__(self, path: str | None = None):
        self.path = path or settings.db_path
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_schema()

    @property
    def mode(self) -> str:
        return "serverless-ephemeral+browser" if str(self.path).startswith("/tmp") else "sqlite-durable"

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS uploads (
                  document_id TEXT PRIMARY KEY,
                  tenant_id TEXT NOT NULL DEFAULT 'demo',
                  case_id TEXT NOT NULL,
                  filename TEXT NOT NULL,
                  sha256 TEXT NOT NULL,
                  document_type TEXT NOT NULL,
                  status TEXT NOT NULL,
                  payload_json TEXT NOT NULL,
                  created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reviewer_feedback (
                  feedback_id TEXT PRIMARY KEY,
                  tenant_id TEXT NOT NULL DEFAULT 'demo',
                  case_id TEXT NOT NULL,
                  document_id TEXT NOT NULL,
                  field_name TEXT NOT NULL,
                  previous_value TEXT NOT NULL,
                  corrected_value TEXT NOT NULL,
                  note TEXT NOT NULL,
                  eval_case_json TEXT NOT NULL,
                  created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS benchmark_runs (
                  run_id TEXT PRIMARY KEY,
                  tenant_id TEXT NOT NULL DEFAULT 'demo',
                  payload_json TEXT NOT NULL,
                  created_at TEXT NOT NULL
                );
                """
            )
            self._ensure_column(conn, "uploads", "tenant_id", "tenant_id TEXT NOT NULL DEFAULT 'demo'")
            self._ensure_column(conn, "reviewer_feedback", "tenant_id", "tenant_id TEXT NOT NULL DEFAULT 'demo'")
            self._ensure_column(conn, "benchmark_runs", "tenant_id", "tenant_id TEXT NOT NULL DEFAULT 'demo'")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_uploads_tenant_case ON uploads (tenant_id, case_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_feedback_tenant_case ON reviewer_feedback (tenant_id, case_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_benchmark_tenant ON benchmark_runs (tenant_id)")

    def save_upload(self, case_id: str, payload: dict[str, Any], *, tenant_id: str = "demo") -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO uploads
                (document_id, tenant_id, case_id, filename, sha256, document_type, status, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    payload["document_id"], tenant_id, case_id, payload["filename"], payload["sha256"],
                    payload["document_type"], payload["status"], json.dumps(payload, ensure_ascii=False), now,
                ),
            )

    def save_feedback(self, payload: dict[str, Any], *, tenant_id: str = "demo") -> tuple[str, dict[str, Any]]:
        feedback_id = f"fb_{uuid.uuid4().hex[:12]}"
        eval_case = {
            "id": feedback_id,
            "input": {
                "document_id": payload["document_id"],
                "field_name": payload["field_name"],
                "previous_value": payload["previous_value"],
            },
            "expected": payload["corrected_value"],
            "reviewer_note": payload.get("note", ""),
            "source": "reviewer_correction",
        }
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                """INSERT INTO reviewer_feedback
                (feedback_id, tenant_id, case_id, document_id, field_name, previous_value, corrected_value, note, eval_case_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    feedback_id, tenant_id, payload["case_id"], payload["document_id"], payload["field_name"],
                    payload["previous_value"], payload["corrected_value"], payload.get("note", ""),
                    json.dumps(eval_case, ensure_ascii=False), now,
                ),
            )
        return feedback_id, eval_case

    def list_feedback(self, *, tenant_id: str = "demo") -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT feedback_id, case_id, document_id, field_name, previous_value, corrected_value, note, created_at
                FROM reviewer_feedback WHERE tenant_id = ? ORDER BY created_at DESC""",
                (tenant_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_benchmark(self, run_id: str, payload: dict[str, Any], *, tenant_id: str = "demo") -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO benchmark_runs (run_id, tenant_id, payload_json, created_at) VALUES (?, ?, ?, ?)",
                (run_id, tenant_id, json.dumps(payload, ensure_ascii=False), now),
            )


store = SQLiteStore()
