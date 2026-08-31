from __future__ import annotations

from pathlib import Path

from app.production import (
    Principal,
    authenticate_api_key,
    load_api_principals,
    production_readiness,
)
from app.storage import SQLiteStore


def test_principals_parse_and_authenticate_constant_contract():
    principals = load_api_principals(
        '{"key-a":{"tenant_id":"tenant-a","actor_id":"alice","role":"reviewer"}}'
    )
    assert principals["key-a"] == Principal("tenant-a", "alice", "reviewer")
    assert authenticate_api_key("key-a", principals) == principals["key-a"]
    assert authenticate_api_key("wrong", principals) is None


def test_local_sqlite_does_not_masquerade_as_production_durable(monkeypatch):
    monkeypatch.setenv(
        "PRUEFPILOT_API_PRINCIPALS",
        '{"key-a":{"tenant_id":"tenant-a","actor_id":"alice","role":"reviewer"}}',
    )
    monkeypatch.setenv("PRUEFPILOT_OBSERVABILITY_ENABLED", "true")
    monkeypatch.setenv("PRUEFPILOT_RETENTION_DAYS", "30")
    monkeypatch.setenv("PRUEFPILOT_BACKUP_RESTORE_TESTED", "true")
    monkeypatch.setenv("PRUEFPILOT_ROLLBACK_READY", "true")

    result = production_readiness(
        app_env="production",
        store_mode="sqlite-durable",
        allowed_origins=("https://review.example",),
        tenant_scoped_persistence=True,
    )
    assert result["ready"] is False
    assert result["gates"]["durable_persistence"] is False
    assert "durable_persistence" in result["missing"]


def test_readiness_fails_closed_on_wildcard_cors(monkeypatch):
    monkeypatch.setenv(
        "PRUEFPILOT_API_PRINCIPALS",
        '{"key-a":{"tenant_id":"tenant-a","actor_id":"alice","role":"reviewer"}}',
    )
    monkeypatch.setenv("PRUEFPILOT_OBSERVABILITY_ENABLED", "true")
    monkeypatch.setenv("PRUEFPILOT_RETENTION_DAYS", "30")
    monkeypatch.setenv("PRUEFPILOT_BACKUP_RESTORE_TESTED", "true")
    monkeypatch.setenv("PRUEFPILOT_ROLLBACK_READY", "true")
    result = production_readiness(
        app_env="production",
        store_mode="postgres-durable",
        allowed_origins=("*",),
        tenant_scoped_persistence=True,
    )
    assert result["ready"] is False
    assert result["gates"]["strict_cors"] is False


def test_tenant_scoped_feedback_never_leaks_between_tenants(tmp_path: Path):
    store = SQLiteStore(str(tmp_path / "pilot.db"))
    base = {
        "case_id": "CASE-1",
        "document_id": "DOC-1",
        "field_name": "amount",
        "previous_value": "10",
        "corrected_value": "11",
        "note": "reviewed",
    }
    store.save_feedback(base, tenant_id="tenant-a")
    store.save_feedback({**base, "document_id": "DOC-2"}, tenant_id="tenant-b")

    a = store.list_feedback(tenant_id="tenant-a")
    b = store.list_feedback(tenant_id="tenant-b")
    assert len(a) == 1
    assert len(b) == 1
    assert a[0]["document_id"] == "DOC-1"
    assert b[0]["document_id"] == "DOC-2"


def test_production_can_only_be_engineering_ready_when_every_gate_is_explicit(monkeypatch):
    monkeypatch.setenv(
        "PRUEFPILOT_API_PRINCIPALS",
        '{"key-a":{"tenant_id":"tenant-a","actor_id":"alice","role":"reviewer"}}',
    )
    monkeypatch.setenv("PRUEFPILOT_OBSERVABILITY_ENABLED", "true")
    monkeypatch.setenv("PRUEFPILOT_RETENTION_DAYS", "30")
    monkeypatch.setenv("PRUEFPILOT_BACKUP_RESTORE_TESTED", "true")
    monkeypatch.setenv("PRUEFPILOT_ROLLBACK_READY", "true")
    result = production_readiness(
        app_env="production",
        store_mode="postgres-durable",
        allowed_origins=("https://review.example",),
        tenant_scoped_persistence=True,
    )
    assert result["ready"] is True
    assert result["stage"] == "ENGINEERING_READY"
    assert result["missing"] == []
    assert "does not prove" in result["truth_boundary"]
