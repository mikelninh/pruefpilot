from __future__ import annotations

import os

import pytest

from app.postgres_store import PostgresStore


DATABASE_URL = os.getenv("PRUEFPILOT_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="PRUEFPILOT_TEST_DATABASE_URL not configured")


def payload(document_id: str) -> dict:
    content = b"%PDF-1.4\nproduction-platform-test\n"
    import hashlib
    return {
        "document_id": document_id,
        "filename": f"{document_id}.pdf",
        "sha256": hashlib.sha256(content).hexdigest(),
        "document_type": "test",
        "status": "review_required",
    }


def test_postgres_store_tenant_blob_idempotency_and_delete():
    assert DATABASE_URL
    store = PostgresStore(DATABASE_URL)
    a, b = "tenant-a-test", "tenant-b-test"
    store.delete_tenant(a)
    store.delete_tenant(b)

    content = b"%PDF-1.4\nproduction-platform-test\n"
    pa = payload("doc-shared")
    pb = payload("doc-shared")
    store.save_upload("CASE-A", pa, tenant_id=a, content=content)
    store.save_upload("CASE-B", pb, tenant_id=b, content=content)

    assert store.get_blob("doc-shared", tenant_id=a) == content
    assert store.get_blob("doc-shared", tenant_id=b) == content
    assert store.get_blob("missing", tenant_id=a) is None

    first = store.reserve_idempotency(tenant_id=a, operation="upload", key="same-key")
    assert first == {"created": True, "response": None}
    store.complete_idempotency(tenant_id=a, operation="upload", key="same-key", response=pa)
    duplicate = store.reserve_idempotency(tenant_id=a, operation="upload", key="same-key")
    assert duplicate["created"] is False
    assert duplicate["response"]["document_id"] == "doc-shared"

    other_tenant = store.reserve_idempotency(tenant_id=b, operation="upload", key="same-key")
    assert other_tenant["created"] is True

    health = store.health()
    assert health["ok"] is True
    assert health["mode"] == "postgres-durable"
    assert health["tenant_scoped"] is True
    assert health["object_store_durable"] is True

    deleted = store.delete_tenant(a)
    assert deleted["uploads"] == 1
    assert store.get_blob("doc-shared", tenant_id=a) is None
    assert store.get_blob("doc-shared", tenant_id=b) == content
    store.delete_tenant(b)
