from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from .postgres_store import PostgresStore


class ProductionPostgresStore(PostgresStore):
    """Postgres store with fail-closed tenant-scoped worker claiming and finding ledger."""

    def __init__(self, database_url: str):
        super().__init__(database_url)
        self._init_finding_schema()

    def _init_finding_schema(self) -> None:
        ddl = """
        CREATE TABLE IF NOT EXISTS findings (
          tenant_id TEXT NOT NULL, finding_id TEXT NOT NULL, case_id TEXT NOT NULL,
          document_id TEXT NOT NULL, field_name TEXT NOT NULL, authority_id TEXT NOT NULL,
          payload_json JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY (tenant_id, finding_id)
        );
        CREATE INDEX IF NOT EXISTS idx_findings_tenant_case
          ON findings (tenant_id, case_id, created_at);

        CREATE TABLE IF NOT EXISTS finding_decisions (
          tenant_id TEXT NOT NULL, decision_id TEXT NOT NULL, finding_id TEXT NOT NULL,
          status TEXT NOT NULL, actor_id TEXT NOT NULL, note TEXT NOT NULL,
          chain_sha256 TEXT NOT NULL, payload_json JSONB NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY (tenant_id, decision_id)
        );
        CREATE INDEX IF NOT EXISTS idx_finding_decisions_tenant_finding
          ON finding_decisions (tenant_id, finding_id, created_at);
        """
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(ddl)

    def get_upload(self, document_id: str, *, tenant_id: str = "demo") -> dict[str, Any] | None:
        record = self.get_upload_record(document_id, tenant_id=tenant_id)
        return record["payload"] if record else None

    def get_upload_record(self, document_id: str, *, tenant_id: str = "demo") -> dict[str, Any] | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT case_id, payload_json FROM uploads WHERE tenant_id=%s AND document_id=%s",
                (tenant_id, document_id),
            )
            row = cur.fetchone()
        return {"case_id": row[0], "payload": row[1]} if row else None

    def save_finding(self, payload: dict[str, Any], *, tenant_id: str = "demo") -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO findings
                (tenant_id, finding_id, case_id, document_id, field_name, authority_id, payload_json, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s)""",
                (
                    tenant_id, payload["finding_id"], payload["case_id"], payload["document_id"],
                    payload["field_name"], payload["authority_id"], json.dumps(payload, ensure_ascii=False),
                    payload["created_at"],
                ),
            )

    def get_finding(self, finding_id: str, *, tenant_id: str = "demo") -> dict[str, Any] | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT payload_json FROM findings WHERE tenant_id=%s AND finding_id=%s",
                (tenant_id, finding_id),
            )
            row = cur.fetchone()
        return row[0] if row else None

    def append_finding_decision(self, payload: dict[str, Any], *, tenant_id: str = "demo") -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO finding_decisions
                (tenant_id, decision_id, finding_id, status, actor_id, note, chain_sha256, payload_json, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)""",
                (
                    tenant_id, payload["decision_id"], payload["finding_id"], payload["status"],
                    payload["actor_id"], payload.get("note", ""), payload["chain_sha256"],
                    json.dumps(payload, ensure_ascii=False), payload["created_at"],
                ),
            )

    def list_finding_decisions(self, finding_id: str, *, tenant_id: str = "demo") -> list[dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT payload_json FROM finding_decisions
                WHERE tenant_id=%s AND finding_id=%s ORDER BY created_at ASC, decision_id ASC""",
                (tenant_id, finding_id),
            )
            rows = cur.fetchall()
        return [row[0] for row in rows]

    def claim_job(self, *, tenant_id: str, worker_id: str) -> dict[str, Any] | None:
        if not tenant_id:
            raise ValueError("tenant_id is required")
        if not worker_id:
            raise ValueError("worker_id is required")
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT job_id FROM jobs
                WHERE tenant_id=%s AND status='queued' AND available_at<=NOW()
                ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1""",
                (tenant_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            job_id = row[0]
            cur.execute(
                """UPDATE jobs SET status='running', attempts=attempts+1, leased_at=NOW(), worker_id=%s, updated_at=NOW()
                WHERE tenant_id=%s AND job_id=%s
                RETURNING tenant_id, job_id, kind, payload_json, status, attempts, max_attempts, worker_id""",
                (worker_id, tenant_id, job_id),
            )
            result = cur.fetchone()
            columns = [d.name for d in cur.description]
            return dict(zip(columns, result, strict=True))

    def retention_sweep(self, *, tenant_id: str, retention_days: int, now: datetime | None = None) -> dict[str, int]:
        if retention_days < 1:
            raise ValueError("retention_days must be >= 1")
        cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=retention_days)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """DELETE FROM finding_decisions
                WHERE tenant_id=%s AND (
                  created_at < %s OR finding_id IN (
                    SELECT finding_id FROM findings WHERE tenant_id=%s AND created_at < %s
                  )
                )""",
                (tenant_id, cutoff, tenant_id, cutoff),
            )
            decisions_deleted = cur.rowcount
            cur.execute("DELETE FROM findings WHERE tenant_id=%s AND created_at < %s", (tenant_id, cutoff))
            findings_deleted = cur.rowcount
        deleted = super().retention_sweep(tenant_id=tenant_id, retention_days=retention_days, now=now)
        deleted["finding_decisions"] = decisions_deleted
        deleted["findings"] = findings_deleted
        return deleted

    def export_tenant(self, tenant_id: str) -> dict[str, Any]:
        snapshot = super().export_tenant(tenant_id)
        table_columns = {
            "findings": [
                "finding_id", "case_id", "document_id", "field_name", "authority_id", "payload_json", "created_at",
            ],
            "finding_decisions": [
                "decision_id", "finding_id", "status", "actor_id", "note", "chain_sha256", "payload_json", "created_at",
            ],
        }
        with self._connect() as conn, conn.cursor() as cur:
            for table, columns in table_columns.items():
                cur.execute(
                    f"SELECT {', '.join(columns)} FROM {table} WHERE tenant_id=%s ORDER BY created_at",
                    (tenant_id,),
                )
                rows: list[dict[str, Any]] = []
                for row in cur.fetchall():
                    item: dict[str, Any] = {}
                    for key, value in zip(columns, row, strict=True):
                        item[key] = value.isoformat() if isinstance(value, datetime) else value
                    rows.append(item)
                snapshot["tables"][table] = rows
        return snapshot

    def restore_tenant(self, snapshot: dict[str, Any], *, expected_tenant_id: str) -> dict[str, int]:
        restored = super().restore_tenant(snapshot, expected_tenant_id=expected_tenant_id)
        tenant_id = expected_tenant_id
        tables = snapshot.get("tables", {})
        with self._connect() as conn, conn.cursor() as cur:
            for item in tables.get("findings", []):
                cur.execute(
                    """INSERT INTO findings
                    (tenant_id, finding_id, case_id, document_id, field_name, authority_id, payload_json, created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s)""",
                    (
                        tenant_id, item["finding_id"], item["case_id"], item["document_id"],
                        item["field_name"], item["authority_id"], json.dumps(item["payload_json"], ensure_ascii=False),
                        item["created_at"],
                    ),
                )
            restored["findings"] = len(tables.get("findings", []))
            for item in tables.get("finding_decisions", []):
                cur.execute(
                    """INSERT INTO finding_decisions
                    (tenant_id, decision_id, finding_id, status, actor_id, note, chain_sha256, payload_json, created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)""",
                    (
                        tenant_id, item["decision_id"], item["finding_id"], item["status"], item["actor_id"],
                        item["note"], item["chain_sha256"], json.dumps(item["payload_json"], ensure_ascii=False),
                        item["created_at"],
                    ),
                )
            restored["finding_decisions"] = len(tables.get("finding_decisions", []))
        return restored

    def delete_tenant(self, tenant_id: str) -> dict[str, int]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM finding_decisions WHERE tenant_id=%s", (tenant_id,))
            decisions_deleted = cur.rowcount
            cur.execute("DELETE FROM findings WHERE tenant_id=%s", (tenant_id,))
            findings_deleted = cur.rowcount
        deleted = super().delete_tenant(tenant_id)
        deleted["finding_decisions"] = decisions_deleted
        deleted["findings"] = findings_deleted
        return deleted
