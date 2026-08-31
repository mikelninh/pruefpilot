from __future__ import annotations

from typing import Any

from .postgres_store import PostgresStore


class ProductionPostgresStore(PostgresStore):
    """Postgres store with fail-closed tenant-scoped worker claiming."""

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
