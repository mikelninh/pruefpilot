from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import settings


class SQLiteStore:
    """Tenant-scoped demo/pilot persistence. Never counts as production-durable."""

    tenant_scoped = True
    object_store_durable = False

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
                  document_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL DEFAULT 'demo', case_id TEXT NOT NULL,
                  filename TEXT NOT NULL, sha256 TEXT NOT NULL, document_type TEXT NOT NULL, status TEXT NOT NULL,
                  payload_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS document_blobs (
                  document_id TEXT NOT NULL, tenant_id TEXT NOT NULL DEFAULT 'demo', sha256 TEXT NOT NULL,
                  content BLOB NOT NULL, content_type TEXT NOT NULL, created_at TEXT NOT NULL,
                  PRIMARY KEY (tenant_id, document_id)
                );
                CREATE TABLE IF NOT EXISTS reviewer_feedback (
                  feedback_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL DEFAULT 'demo', case_id TEXT NOT NULL,
                  document_id TEXT NOT NULL, field_name TEXT NOT NULL, previous_value TEXT NOT NULL,
                  corrected_value TEXT NOT NULL, note TEXT NOT NULL, eval_case_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS benchmark_runs (
                  run_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL DEFAULT 'demo', payload_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS idempotency_keys (
                  tenant_id TEXT NOT NULL, operation TEXT NOT NULL, idempotency_key TEXT NOT NULL,
                  response_json TEXT, created_at TEXT NOT NULL, completed_at TEXT,
                  PRIMARY KEY (tenant_id, operation, idempotency_key)
                );
                """
            )
            self._ensure_column(conn, "uploads", "tenant_id", "tenant_id TEXT NOT NULL DEFAULT 'demo'")
            self._ensure_column(conn, "reviewer_feedback", "tenant_id", "tenant_id TEXT NOT NULL DEFAULT 'demo'")
            self._ensure_column(conn, "benchmark_runs", "tenant_id", "tenant_id TEXT NOT NULL DEFAULT 'demo'")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_uploads_tenant_case ON uploads (tenant_id, case_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_feedback_tenant_case ON reviewer_feedback (tenant_id, case_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_benchmark_tenant ON benchmark_runs (tenant_id)")

    def health(self) -> dict[str, Any]:
        try:
            with self._connect() as conn:
                ok = conn.execute("SELECT 1").fetchone()[0] == 1
            return {"ok": ok, "mode": self.mode, "tenant_scoped": True, "object_store_durable": False}
        except Exception as exc:
            return {"ok": False, "mode": self.mode, "error": type(exc).__name__}

    def save_upload(self, case_id: str, payload: dict[str, Any], *, tenant_id: str = "demo", content: bytes | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO uploads
                (document_id, tenant_id, case_id, filename, sha256, document_type, status, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (payload["document_id"], tenant_id, case_id, payload["filename"], payload["sha256"],
                 payload["document_type"], payload["status"], json.dumps(payload, ensure_ascii=False), now),
            )
            if content is not None:
                digest = hashlib.sha256(content).hexdigest()
                if digest != payload["sha256"]:
                    raise ValueError("blob_sha256_mismatch")
                conn.execute(
                    """INSERT OR REPLACE INTO document_blobs
                    (tenant_id, document_id, sha256, content, content_type, created_at) VALUES (?, ?, ?, ?, ?, ?)""",
                    (tenant_id, payload["document_id"], digest, content, "application/pdf", now),
                )

    def get_blob(self, document_id: str, *, tenant_id: str = "demo") -> bytes | None:
        with self._connect() as conn:
            row = conn.execute("SELECT content FROM document_blobs WHERE tenant_id=? AND document_id=?", (tenant_id, document_id)).fetchone()
        return bytes(row[0]) if row else None

    def save_feedback(self, payload: dict[str, Any], *, tenant_id: str = "demo") -> tuple[str, dict[str, Any]]:
        feedback_id = f"fb_{uuid.uuid4().hex[:12]}"
        eval_case = {
            "id": feedback_id,
            "input": {"document_id": payload["document_id"], "field_name": payload["field_name"], "previous_value": payload["previous_value"]},
            "expected": payload["corrected_value"], "reviewer_note": payload.get("note", ""), "source": "reviewer_correction",
        }
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                """INSERT INTO reviewer_feedback
                (feedback_id, tenant_id, case_id, document_id, field_name, previous_value, corrected_value, note, eval_case_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (feedback_id, tenant_id, payload["case_id"], payload["document_id"], payload["field_name"],
                 payload["previous_value"], payload["corrected_value"], payload.get("note", ""), json.dumps(eval_case, ensure_ascii=False), now),
            )
        return feedback_id, eval_case

    def list_feedback(self, *, tenant_id: str = "demo") -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT feedback_id, case_id, document_id, field_name, previous_value, corrected_value, note, created_at
                FROM reviewer_feedback WHERE tenant_id = ? ORDER BY created_at DESC""", (tenant_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_benchmark(self, run_id: str, payload: dict[str, Any], *, tenant_id: str = "demo") -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO benchmark_runs (run_id, tenant_id, payload_json, created_at) VALUES (?, ?, ?, ?)",
                (run_id, tenant_id, json.dumps(payload, ensure_ascii=False), now),
            )

    def reserve_idempotency(self, *, tenant_id: str, operation: str, key: str) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            try:
                conn.execute(
                    "INSERT INTO idempotency_keys (tenant_id, operation, idempotency_key, created_at) VALUES (?, ?, ?, ?)",
                    (tenant_id, operation, key, now),
                )
                return {"created": True, "response": None}
            except sqlite3.IntegrityError:
                row = conn.execute(
                    "SELECT response_json FROM idempotency_keys WHERE tenant_id=? AND operation=? AND idempotency_key=?",
                    (tenant_id, operation, key),
                ).fetchone()
                return {"created": False, "response": json.loads(row[0]) if row and row[0] else None}

    def complete_idempotency(self, *, tenant_id: str, operation: str, key: str, response: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                """UPDATE idempotency_keys SET response_json=?, completed_at=?
                WHERE tenant_id=? AND operation=? AND idempotency_key=?""",
                (json.dumps(response, ensure_ascii=False), now, tenant_id, operation, key),
            )

    def delete_tenant(self, tenant_id: str) -> dict[str, int]:
        deleted: dict[str, int] = {}
        with self._lock, self._connect() as conn:
            for table in ("document_blobs", "reviewer_feedback", "benchmark_runs", "idempotency_keys", "uploads"):
                cur = conn.execute(f"DELETE FROM {table} WHERE tenant_id=?", (tenant_id,))
                deleted[table] = cur.rowcount
        return deleted


def build_store():
    database_url = os.getenv("PRUEFPILOT_DATABASE_URL", "").strip()
    if database_url:
        from .postgres_store import PostgresStore
        return PostgresStore(database_url)
    return SQLiteStore()


store = build_store()
