from __future__ import annotations

import hashlib
import os
from datetime import datetime, timedelta, timezone

import pytest

from app.production_postgres_store import ProductionPostgresStore

DATABASE_URL = os.getenv("PRUEFPILOT_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="PRUEFPILOT_TEST_DATABASE_URL not configured")
CONTENT = b"%PDF-1.4\nproduction-platform-test\n"


def payload(document_id: str) -> dict:
    return {
        "document_id": document_id,
        "filename": f"{document_id}.pdf",
        "sha256": hashlib.sha256(CONTENT).hexdigest(),
        "document_type": "test",
        "status": "review_required",
    }


def store() -> ProductionPostgresStore:
    assert DATABASE_URL
    return ProductionPostgresStore(DATABASE_URL)


def test_postgres_store_tenant_blob_idempotency_and_delete():
    db = store()
    a, b = "tenant-a-test", "tenant-b-test"
    db.delete_tenant(a); db.delete_tenant(b)
    db.save_upload("CASE-A", payload("doc-shared"), tenant_id=a, content=CONTENT)
    db.save_upload("CASE-B", payload("doc-shared"), tenant_id=b, content=CONTENT)

    assert db.get_blob("doc-shared", tenant_id=a) == CONTENT
    assert db.get_blob("doc-shared", tenant_id=b) == CONTENT
    assert db.get_blob("missing", tenant_id=a) is None

    first = db.reserve_idempotency(tenant_id=a, operation="upload", key="same-key")
    assert first == {"created": True, "response": None}
    db.complete_idempotency(tenant_id=a, operation="upload", key="same-key", response=payload("doc-shared"))
    duplicate = db.reserve_idempotency(tenant_id=a, operation="upload", key="same-key")
    assert duplicate["created"] is False
    assert duplicate["response"]["document_id"] == "doc-shared"
    assert db.reserve_idempotency(tenant_id=b, operation="upload", key="same-key")["created"] is True

    health = db.health()
    assert health == {
        "ok": True, "mode": "postgres-durable", "tenant_scoped": True,
        "object_store_durable": True, "queue_durable": True, "audit_durable": True,
    }

    deleted = db.delete_tenant(a)
    assert deleted["uploads"] == 1
    assert db.get_blob("doc-shared", tenant_id=a) is None
    assert db.get_blob("doc-shared", tenant_id=b) == CONTENT
    db.delete_tenant(b)


def test_audit_redacts_secrets_and_never_crosses_tenants():
    db = store(); a, b = "audit-a", "audit-b"
    db.delete_tenant(a); db.delete_tenant(b)
    db.append_audit(tenant_id=a, actor_id="alice", role="admin", event_type="test", payload={"api_key": "do-not-leak", "nested": {"token": "hidden", "safe": "visible"}})
    db.append_audit(tenant_id=b, actor_id="bob", role="admin", event_type="other", payload={"safe": "b"})
    events = db.list_audit(tenant_id=a)
    assert len(events) == 1
    assert events[0]["payload_json"]["api_key"] == "[REDACTED]"
    assert events[0]["payload_json"]["nested"]["token"] == "[REDACTED]"
    assert events[0]["payload_json"]["nested"]["safe"] == "visible"
    assert "do-not-leak" not in str(events)
    db.delete_tenant(a); db.delete_tenant(b)


def test_queue_is_tenant_scoped_idempotent_retried_and_dead_lettered():
    db = store(); a, b = "queue-a", "queue-b"
    db.delete_tenant(a); db.delete_tenant(b)
    ja = db.enqueue_job(tenant_id=a, kind="review", payload={"api_key": "secret-a", "case": "A"}, idempotency_key="same", max_attempts=2)
    jb = db.enqueue_job(tenant_id=b, kind="review", payload={"case": "B"}, idempotency_key="same", max_attempts=2)
    assert ja["created"] is True and jb["created"] is True
    duplicate = db.enqueue_job(tenant_id=a, kind="review", payload={"case": "A2"}, idempotency_key="same", max_attempts=2)
    assert duplicate["created"] is False and duplicate["job_id"] == ja["job_id"]

    claimed_a = db.claim_job(tenant_id=a, worker_id="worker-a")
    assert claimed_a and claimed_a["tenant_id"] == a and claimed_a["payload_json"]["api_key"] == "[REDACTED]"
    state = db.fail_job(tenant_id=a, job_id=claimed_a["job_id"], error="temporary")
    assert state["dead_lettered"] is False
    claimed_a2 = db.claim_job(tenant_id=a, worker_id="worker-a")
    state = db.fail_job(tenant_id=a, job_id=claimed_a2["job_id"], error="still broken")
    assert state["dead_lettered"] is True and state["status"] == "dead-letter"

    claimed_b = db.claim_job(tenant_id=b, worker_id="worker-b")
    assert claimed_b and claimed_b["tenant_id"] == b and claimed_b["job_id"] == jb["job_id"]
    done = db.complete_job(tenant_id=b, job_id=claimed_b["job_id"], result={"ok": True, "token": "never-log"})
    assert done["status"] == "done"
    db.delete_tenant(a); db.delete_tenant(b)


def test_backup_delete_restore_roundtrip_recovers_blob_audit_and_job():
    db = store(); tenant = "restore-test"
    db.delete_tenant(tenant)
    db.save_upload("CASE-R", payload("doc-r"), tenant_id=tenant, content=CONTENT)
    db.append_audit(tenant_id=tenant, actor_id="owner", role="owner", event_type="created", payload={"safe": True})
    db.enqueue_job(tenant_id=tenant, kind="review", payload={"document_id": "doc-r"}, idempotency_key="job-r")
    snapshot = db.export_tenant(tenant)
    assert snapshot["schema"] == "pruefpilot-tenant-backup/1.0"
    assert snapshot["tables"]["document_blobs"][0]["content_b64"]

    db.delete_tenant(tenant)
    assert db.get_blob("doc-r", tenant_id=tenant) is None
    restored = db.restore_tenant(snapshot, expected_tenant_id=tenant)
    assert restored["uploads"] == 1 and restored["document_blobs"] == 1
    assert db.get_blob("doc-r", tenant_id=tenant) == CONTENT
    assert db.list_audit(tenant_id=tenant)[0]["event_type"] == "created"
    job = db.claim_job(tenant_id=tenant, worker_id="worker-r")
    assert job and job["kind"] == "review"
    db.delete_tenant(tenant)


def test_retention_sweep_removes_only_expired_tenant_data():
    db = store(); a, b = "retention-a", "retention-b"
    db.delete_tenant(a); db.delete_tenant(b)
    db.append_audit(tenant_id=a, actor_id="a", role="admin", event_type="old", payload={})
    db.append_audit(tenant_id=b, actor_id="b", role="admin", event_type="keep", payload={})
    old = datetime.now(timezone.utc) - timedelta(days=40)
    with db._connect() as conn, conn.cursor() as cur:
        cur.execute("UPDATE audit_events SET created_at=%s WHERE tenant_id=%s", (old, a))
    deleted = db.retention_sweep(tenant_id=a, retention_days=30)
    assert deleted["audit_events"] == 1
    assert db.list_audit(tenant_id=a) == []
    assert len(db.list_audit(tenant_id=b)) == 1
    db.delete_tenant(a); db.delete_tenant(b)
