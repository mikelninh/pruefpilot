from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any


class PostgresStore:
    """Durable tenant-scoped storage for controlled production deployments.

    The connection driver is imported lazily so demo/local SQLite installs keep working without the
    optional postgres dependency. Original PDF bytes are stored in Postgres BYTEA in v1; a dedicated
    object-store adapter can replace that boundary later without changing API semantics.
    """

    mode = "postgres-durable"
    tenant_scoped = True
    object_store_durable = True

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
          tenant_id TEXT NOT NULL,
          document_id TEXT NOT NULL,
          case_id TEXT NOT NULL,
          filename TEXT NOT NULL,
          sha256 TEXT NOT NULL,
          document_type TEXT NOT NULL,
          status TEXT NOT NULL,
          payload_json JSONB NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY (tenant_id, document_id)
        );
        CREATE INDEX IF NOT EXISTS idx_uploads_tenant_case ON uploads (tenant_id, case_id);

        CREATE TABLE IF NOT EXISTS document_blobs (
          tenant_id TEXT NOT NULL,
          document_id TEXT NOT NULL,
          sha256 TEXT NOT NULL,
          content BYTEA NOT NULL,
          content_type TEXT NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY (tenant_id, document_id),
          FOREIGN KEY (tenant_id, document_id) REFERENCES uploads (tenant_id, document_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS reviewer_feedback (
          tenant_id TEXT NOT NULL,
          feedback_id TEXT NOT NULL,
          case_id TEXT NOT NULL,
          document_id TEXT NOT NULL,
          field_name TEXT NOT NULL,
          previous_value TEXT NOT NULL,
          corrected_value TEXT NOT NULL,
          note TEXT NOT NULL,
          eval_case_json JSONB NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY (tenant_id, feedback_id)
        );
        CREATE INDEX IF NOT EXISTS idx_feedback_tenant_case ON reviewer_feedback (tenant_id, case_id);

        CREATE TABLE IF NOT EXISTS benchmark_runs (
          tenant_id TEXT NOT NULL,
          run_id TEXT NOT NULL,
          payload_json JSONB NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY (tenant_id, run_id)
        );

        CREATE TABLE IF NOT EXISTS idempotency_keys (
          tenant_id TEXT NOT NULL,
          operation TEXT NOT NULL,
          idempotency_key TEXT NOT NULL,
          response_json JSONB,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          completed_at TIMESTAMPTZ,
          PRIMARY KEY (tenant_id, operation, idempotency_key)
        );
        """
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(ddl)

    def health(self) -> dict[str, Any]:
        try:
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute("SELECT 1")
                ok = cur.fetchone() == (1,)
            return {"ok": ok, "mode": self.mode, "tenant_scoped": True, "object_store_durable": True}
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
                VALUES (%s,%s,%s) ON CONFLICT DO NOTHING RETURNING idempotency_key""",
                (tenant_id, operation, key),
            )
            created = cur.fetchone() is not None
            if created:
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

    def delete_tenant(self, tenant_id: str) -> dict[str, int]:
        deleted: dict[str, int] = {}
        with self._connect() as conn, conn.cursor() as cur:
            for table in ("document_blobs", "reviewer_feedback", "benchmark_runs", "idempotency_keys", "uploads"):
                cur.execute(f"DELETE FROM {table} WHERE tenant_id=%s", (tenant_id,))
                deleted[table] = cur.rowcount
        return deleted
