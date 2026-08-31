from __future__ import annotations

import base64
import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

_SECRET_KEYS = re.compile(r"secret|token|password|api[-_]?key|authorization", re.IGNORECASE)


def _redact(value: Any) -> Any:
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, dict):
        return {key: "[REDACTED]" if _SECRET_KEYS.search(str(key)) else _redact(item) for key, item in value.items()}
    return value


class PostgresStore:
    """Durable tenant-scoped operating store for controlled production deployments."""

    mode = "postgres-durable"
    tenant_scoped = True
    object_store_durable = True
    queue_durable = True
    audit_durable = True

    def __init__(self, database_url: str):
        if not database_url:
            raise ValueError("database_url is required")
        try:
            import psycopg  # type: ignore
        except ImportError as exc:
            raise RuntimeError("Install the postgres extra: pip install -e '.[postgres]'") from exc
        self._psycopg = psycopg
        self.database_url = database_url
        self._init_schema()

    def _connect(self):
        return self._psycopg.connect(self.database_url)

    def _init_schema(self) -> None:
        ddl = """
        CREATE TABLE IF NOT EXISTS uploads (
          tenant_id TEXT NOT NULL, document_id TEXT NOT NULL, case_id TEXT NOT NULL,
          filename TEXT NOT NULL, sha256 TEXT NOT NULL, document_type TEXT NOT NULL, status TEXT NOT NULL,
          payload_json JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY (tenant_id, document_id)
        );
        CREATE INDEX IF NOT EXISTS idx_uploads_tenant_case ON uploads (tenant_id, case_id);

        CREATE TABLE IF NOT EXISTS document_blobs (
          tenant_id TEXT NOT NULL, document_id TEXT NOT NULL, sha256 TEXT NOT NULL, content BYTEA NOT NULL,
          content_type TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY (tenant_id, document_id),
          FOREIGN KEY (tenant_id, document_id) REFERENCES uploads (tenant_id, document_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS reviewer_feedback (
          tenant_id TEXT NOT NULL, feedback_id TEXT NOT NULL, case_id TEXT NOT NULL, document_id TEXT NOT NULL,
          field_name TEXT NOT NULL, previous_value TEXT NOT NULL, corrected_value TEXT NOT NULL, note TEXT NOT NULL,
          eval_case_json JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY (tenant_id, feedback_id)
        );
        CREATE INDEX IF NOT EXISTS idx_feedback_tenant_case ON reviewer_feedback (tenant_id, case_id);

        CREATE TABLE IF NOT EXISTS benchmark_runs (
          tenant_id TEXT NOT NULL, run_id TEXT NOT NULL, payload_json JSONB NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), PRIMARY KEY (tenant_id, run_id)
        );

        CREATE TABLE IF NOT EXISTS idempotency_keys (
          tenant_id TEXT NOT NULL, operation TEXT NOT NULL, idempotency_key TEXT NOT NULL,
          response_json JSONB, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), completed_at TIMESTAMPTZ,
          PRIMARY KEY (tenant_id, operation, idempotency_key)
        );

        CREATE TABLE IF NOT EXISTS audit_events (
          tenant_id TEXT NOT NULL, event_id TEXT NOT NULL, actor_id TEXT NOT NULL, role TEXT NOT NULL,
          request_id TEXT, event_type TEXT NOT NULL, payload_json JSONB NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), PRIMARY KEY (tenant_id, event_id)
        );
        CREATE INDEX IF NOT EXISTS idx_audit_tenant_created ON audit_events (tenant_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS jobs (
          tenant_id TEXT NOT NULL, job_id TEXT NOT NULL, kind TEXT NOT NULL, payload_json JSONB NOT NULL,
          idempotency_key TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued', attempts INTEGER NOT NULL DEFAULT 0,
          max_attempts INTEGER NOT NULL DEFAULT 3, available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          leased_at TIMESTAMPTZ, worker_id TEXT, last_error TEXT, result_json JSONB,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY (tenant_id, job_id), UNIQUE (tenant_id, idempotency_key)
        );
        CREATE INDEX IF NOT EXISTS idx_jobs_claim ON jobs (status, available_at, created_at);
        """
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(ddl)

    def health(self) -> dict[str, Any]:
        try:
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute("SELECT 1")
                ok = cur.fetchone() == (1,)
            return {
                "ok": ok, "mode": self.mode, "tenant_scoped": True,
                "object_store_durable": True, "queue_durable": True, "audit_durable": True,
            }
        except Exception as exc:
            return {"ok": False, "mode": self.mode, "error": type(exc).__name__}

    def save_upload(self, case_id: str, payload: dict[str, Any], *, tenant_id: str = "demo", content: bytes | None = None) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO uploads
                (tenant_id, document_id, case_id, filename, sha256, document_type, status, payload_json)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                ON CONFLICT (tenant_id, document_id) DO UPDATE SET
                  case_id=EXCLUDED.case_id, filename=EXCLUDED.filename, sha256=EXCLUDED.sha256,
                  document_type=EXCLUDED.document_type, status=EXCLUDED.status, payload_json=EXCLUDED.payload_json""",
                (tenant_id, payload["document_id"], case_id, payload["filename"], payload["sha256"],
                 payload["document_type"], payload["status"], json.dumps(payload, ensure_ascii=False)),
            )
            if content is not None:
                digest = hashlib.sha256(content).hexdigest()
                if digest != payload["sha256"]:
                    raise ValueError("blob_sha256_mismatch")
                cur.execute(
                    """INSERT INTO document_blobs (tenant_id, document_id, sha256, content, content_type)
                    VALUES (%s,%s,%s,%s,%s)
                    ON CONFLICT (tenant_id, document_id) DO UPDATE SET
                      sha256=EXCLUDED.sha256, content=EXCLUDED.content, content_type=EXCLUDED.content_type""",
                    (tenant_id, payload["document_id"], digest, content, "application/pdf"),
                )

    def get_blob(self, document_id: str, *, tenant_id: str = "demo") -> bytes | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT content FROM document_blobs WHERE tenant_id=%s AND document_id=%s", (tenant_id, document_id))
            row = cur.fetchone()
        return bytes(row[0]) if row else None

    def save_feedback(self, payload: dict[str, Any], *, tenant_id: str = "demo") -> tuple[str, dict[str, Any]]:
        feedback_id = f"fb_{uuid.uuid4().hex[:12]}"
        eval_case = {
            "id": feedback_id,
            "input": {"document_id": payload["document_id"], "field_name": payload["field_name"], "previous_value": payload["previous_value"]},
            "expected": payload["corrected_value"], "reviewer_note": payload.get("note", ""), "source": "reviewer_correction",
        }
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO reviewer_feedback
                (tenant_id, feedback_id, case_id, document_id, field_name, previous_value, corrected_value, note, eval_case_json)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)""",
                (tenant_id, feedback_id, payload["case_id"], payload["document_id"], payload["field_name"],
                 payload["previous_value"], payload["corrected_value"], payload.get("note", ""), json.dumps(eval_case, ensure_ascii=False)),
            )
        return feedback_id, eval_case

    def list_feedback(self, *, tenant_id: str = "demo") -> list[dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT feedback_id, case_id, document_id, field_name, previous_value, corrected_value, note, created_at
                FROM reviewer_feedback WHERE tenant_id=%s ORDER BY created_at DESC""", (tenant_id,)
            )
            columns = [d.name for d in cur.description]
            rows = cur.fetchall()
        return [dict(zip(columns, row, strict=True)) for row in rows]

    def save_benchmark(self, run_id: str, payload: dict[str, Any], *, tenant_id: str = "demo") -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO benchmark_runs (tenant_id, run_id, payload_json) VALUES (%s,%s,%s::jsonb)
                ON CONFLICT (tenant_id, run_id) DO UPDATE SET payload_json=EXCLUDED.payload_json""",
                (tenant_id, run_id, json.dumps(payload, ensure_ascii=False)),
            )

    def reserve_idempotency(self, *, tenant_id: str, operation: str, key: str) -> dict[str, Any]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO idempotency_keys (tenant_id, operation, idempotency_key)
                VALUES (%s,%s,%s) ON CONFLICT DO NOTHING RETURNING idempotency_key""", (tenant_id, operation, key)
            )
            if cur.fetchone() is not None:
                return {"created": True, "response": None}
            cur.execute(
                "SELECT response_json FROM idempotency_keys WHERE tenant_id=%s AND operation=%s AND idempotency_key=%s",
                (tenant_id, operation, key),
            )
            row = cur.fetchone()
            return {"created": False, "response": row[0] if row else None}

    def complete_idempotency(self, *, tenant_id: str, operation: str, key: str, response: dict[str, Any]) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """UPDATE idempotency_keys SET response_json=%s::jsonb, completed_at=NOW()
                WHERE tenant_id=%s AND operation=%s AND idempotency_key=%s""",
                (json.dumps(response, ensure_ascii=False), tenant_id, operation, key),
            )

    def append_audit(self, *, tenant_id: str, actor_id: str, role: str, event_type: str, payload: dict[str, Any] | None = None, request_id: str | None = None) -> str:
        event_id = f"evt_{uuid.uuid4().hex[:16]}"
        safe_payload = _redact(payload or {})
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO audit_events
                (tenant_id, event_id, actor_id, role, request_id, event_type, payload_json)
                VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)""",
                (tenant_id, event_id, actor_id, role, request_id, event_type, json.dumps(safe_payload, ensure_ascii=False)),
            )
        return event_id

    def list_audit(self, *, tenant_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT event_id, actor_id, role, request_id, event_type, payload_json, created_at
                FROM audit_events WHERE tenant_id=%s ORDER BY created_at DESC LIMIT %s""", (tenant_id, min(max(limit, 1), 500)),
            )
            columns = [d.name for d in cur.description]
            rows = cur.fetchall()
        return [dict(zip(columns, row, strict=True)) for row in rows]

    def enqueue_job(self, *, tenant_id: str, kind: str, payload: dict[str, Any], idempotency_key: str, max_attempts: int = 3) -> dict[str, Any]:
        job_id = f"job_{uuid.uuid4().hex[:16]}"
        safe_payload = _redact(payload)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO jobs (tenant_id, job_id, kind, payload_json, idempotency_key, max_attempts)
                VALUES (%s,%s,%s,%s::jsonb,%s,%s) ON CONFLICT (tenant_id, idempotency_key) DO NOTHING RETURNING job_id""",
                (tenant_id, job_id, kind, json.dumps(safe_payload, ensure_ascii=False), idempotency_key, max(max_attempts, 1)),
            )
            created = cur.fetchone()
            if created:
                return {"created": True, "job_id": job_id, "status": "queued"}
            cur.execute(
                "SELECT job_id, status FROM jobs WHERE tenant_id=%s AND idempotency_key=%s", (tenant_id, idempotency_key)
            )
            row = cur.fetchone()
            return {"created": False, "job_id": row[0], "status": row[1]}

    def claim_job(self, *, worker_id: str) -> dict[str, Any] | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT tenant_id, job_id FROM jobs
                WHERE status='queued' AND available_at<=NOW() ORDER BY created_at
                FOR UPDATE SKIP LOCKED LIMIT 1"""
            )
            row = cur.fetchone()
            if not row:
                return None
            tenant_id, job_id = row
            cur.execute(
                """UPDATE jobs SET status='running', attempts=attempts+1, leased_at=NOW(), worker_id=%s, updated_at=NOW()
                WHERE tenant_id=%s AND job_id=%s
                RETURNING tenant_id, job_id, kind, payload_json, status, attempts, max_attempts, worker_id""",
                (worker_id, tenant_id, job_id),
            )
            result = cur.fetchone()
            columns = [d.name for d in cur.description]
            return dict(zip(columns, result, strict=True))

    def complete_job(self, *, tenant_id: str, job_id: str, result: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """UPDATE jobs SET status='done', result_json=%s::jsonb, updated_at=NOW()
                WHERE tenant_id=%s AND job_id=%s AND status='running' RETURNING status, attempts""",
                (json.dumps(_redact(result or {}), ensure_ascii=False), tenant_id, job_id),
            )
            row = cur.fetchone()
            if not row:
                raise KeyError("running_job_not_found")
            return {"status": row[0], "attempts": row[1], "dead_lettered": False}

    def fail_job(self, *, tenant_id: str, job_id: str, error: str, retry_delay_seconds: int = 0) -> dict[str, Any]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT attempts, max_attempts FROM jobs WHERE tenant_id=%s AND job_id=%s FOR UPDATE", (tenant_id, job_id))
            row = cur.fetchone()
            if not row:
                raise KeyError("job_not_found")
            attempts, max_attempts = row
            dead = attempts >= max_attempts
            status = "dead-letter" if dead else "queued"
            cur.execute(
                """UPDATE jobs SET status=%s, last_error=%s,
                available_at=CASE WHEN %s THEN available_at ELSE NOW() + (%s * INTERVAL '1 second') END,
                worker_id=NULL, leased_at=NULL, updated_at=NOW()
                WHERE tenant_id=%s AND job_id=%s""",
                (status, str(error)[:2000], dead, max(retry_delay_seconds, 0), tenant_id, job_id),
            )
            return {"status": status, "attempts": attempts, "dead_lettered": dead}

    def retention_sweep(self, *, tenant_id: str, retention_days: int, now: datetime | None = None) -> dict[str, int]:
        if retention_days < 1:
            raise ValueError("retention_days must be >= 1")
        cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=retention_days)
        deleted: dict[str, int] = {}
        with self._connect() as conn, conn.cursor() as cur:
            for table in ("reviewer_feedback", "benchmark_runs", "idempotency_keys", "audit_events", "jobs"):
                cur.execute(f"DELETE FROM {table} WHERE tenant_id=%s AND created_at < %s", (tenant_id, cutoff))
                deleted[table] = cur.rowcount
            cur.execute("DELETE FROM uploads WHERE tenant_id=%s AND created_at < %s", (tenant_id, cutoff))
            deleted["uploads"] = cur.rowcount
        return deleted

    def export_tenant(self, tenant_id: str) -> dict[str, Any]:
        snapshot: dict[str, Any] = {"schema": "pruefpilot-tenant-backup/1.0", "tenant_id": tenant_id, "tables": {}}
        table_columns = {
            "uploads": ["document_id", "case_id", "filename", "sha256", "document_type", "status", "payload_json", "created_at"],
            "reviewer_feedback": ["feedback_id", "case_id", "document_id", "field_name", "previous_value", "corrected_value", "note", "eval_case_json", "created_at"],
            "benchmark_runs": ["run_id", "payload_json", "created_at"],
            "idempotency_keys": ["operation", "idempotency_key", "response_json", "created_at", "completed_at"],
            "audit_events": ["event_id", "actor_id", "role", "request_id", "event_type", "payload_json", "created_at"],
            "jobs": ["job_id", "kind", "payload_json", "idempotency_key", "status", "attempts", "max_attempts", "available_at", "leased_at", "worker_id", "last_error", "result_json", "created_at", "updated_at"],
        }
        with self._connect() as conn, conn.cursor() as cur:
            for table, columns in table_columns.items():
                cur.execute(f"SELECT {', '.join(columns)} FROM {table} WHERE tenant_id=%s ORDER BY created_at", (tenant_id,))
                rows = []
                for row in cur.fetchall():
                    item: dict[str, Any] = {}
                    for key, value in zip(columns, row, strict=True):
                        item[key] = value.isoformat() if isinstance(value, datetime) else value
                    rows.append(item)
                snapshot["tables"][table] = rows
            cur.execute("SELECT document_id, sha256, content, content_type, created_at FROM document_blobs WHERE tenant_id=%s ORDER BY created_at", (tenant_id,))
            snapshot["tables"]["document_blobs"] = [
                {"document_id": row[0], "sha256": row[1], "content_b64": base64.b64encode(bytes(row[2])).decode("ascii"), "content_type": row[3], "created_at": row[4].isoformat()}
                for row in cur.fetchall()
            ]
        return snapshot

    def restore_tenant(self, snapshot: dict[str, Any], *, expected_tenant_id: str) -> dict[str, int]:
        if snapshot.get("schema") != "pruefpilot-tenant-backup/1.0" or snapshot.get("tenant_id") != expected_tenant_id:
            raise ValueError("backup_tenant_or_schema_mismatch")
        tenant_id = expected_tenant_id
        self.delete_tenant(tenant_id)
        restored: dict[str, int] = {}
        tables = snapshot.get("tables", {})
        with self._connect() as conn, conn.cursor() as cur:
            for item in tables.get("uploads", []):
                cur.execute(
                    """INSERT INTO uploads (tenant_id, document_id, case_id, filename, sha256, document_type, status, payload_json, created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)""",
                    (tenant_id, item["document_id"], item["case_id"], item["filename"], item["sha256"], item["document_type"], item["status"], json.dumps(item["payload_json"]), item["created_at"]),
                )
            restored["uploads"] = len(tables.get("uploads", []))
            for item in tables.get("document_blobs", []):
                cur.execute(
                    """INSERT INTO document_blobs (tenant_id, document_id, sha256, content, content_type, created_at)
                    VALUES (%s,%s,%s,%s,%s,%s)""",
                    (tenant_id, item["document_id"], item["sha256"], base64.b64decode(item["content_b64"]), item["content_type"], item["created_at"]),
                )
            restored["document_blobs"] = len(tables.get("document_blobs", []))
            for item in tables.get("reviewer_feedback", []):
                cur.execute(
                    """INSERT INTO reviewer_feedback (tenant_id, feedback_id, case_id, document_id, field_name, previous_value, corrected_value, note, eval_case_json, created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)""",
                    (tenant_id, item["feedback_id"], item["case_id"], item["document_id"], item["field_name"], item["previous_value"], item["corrected_value"], item["note"], json.dumps(item["eval_case_json"]), item["created_at"]),
                )
            restored["reviewer_feedback"] = len(tables.get("reviewer_feedback", []))
            for item in tables.get("benchmark_runs", []):
                cur.execute("INSERT INTO benchmark_runs (tenant_id, run_id, payload_json, created_at) VALUES (%s,%s,%s::jsonb,%s)", (tenant_id, item["run_id"], json.dumps(item["payload_json"]), item["created_at"]))
            restored["benchmark_runs"] = len(tables.get("benchmark_runs", []))
            for item in tables.get("idempotency_keys", []):
                cur.execute("INSERT INTO idempotency_keys (tenant_id, operation, idempotency_key, response_json, created_at, completed_at) VALUES (%s,%s,%s,%s::jsonb,%s,%s)", (tenant_id, item["operation"], item["idempotency_key"], json.dumps(item["response_json"]) if item["response_json"] is not None else None, item["created_at"], item["completed_at"]))
            restored["idempotency_keys"] = len(tables.get("idempotency_keys", []))
            for item in tables.get("audit_events", []):
                cur.execute("INSERT INTO audit_events (tenant_id, event_id, actor_id, role, request_id, event_type, payload_json, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s)", (tenant_id, item["event_id"], item["actor_id"], item["role"], item["request_id"], item["event_type"], json.dumps(item["payload_json"]), item["created_at"]))
            restored["audit_events"] = len(tables.get("audit_events", []))
            for item in tables.get("jobs", []):
                cur.execute(
                    """INSERT INTO jobs (tenant_id, job_id, kind, payload_json, idempotency_key, status, attempts, max_attempts, available_at, leased_at, worker_id, last_error, result_json, created_at, updated_at)
                    VALUES (%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)""",
                    (tenant_id, item["job_id"], item["kind"], json.dumps(item["payload_json"]), item["idempotency_key"], item["status"], item["attempts"], item["max_attempts"], item["available_at"], item["leased_at"], item["worker_id"], item["last_error"], json.dumps(item["result_json"]) if item["result_json"] is not None else None, item["created_at"], item["updated_at"]),
                )
            restored["jobs"] = len(tables.get("jobs", []))
        return restored

    def delete_tenant(self, tenant_id: str) -> dict[str, int]:
        deleted: dict[str, int] = {}
        with self._connect() as conn, conn.cursor() as cur:
            for table in ("document_blobs", "reviewer_feedback", "benchmark_runs", "idempotency_keys", "audit_events", "jobs", "uploads"):
                cur.execute(f"DELETE FROM {table} WHERE tenant_id=%s", (tenant_id,))
                deleted[table] = cur.rowcount
        return deleted
