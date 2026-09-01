from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Request
from reportlab.pdfgen import canvas

from app import findings_api
from app.document_ai import ingest_pdf
from app.findings import FindingError, create_finding, decide_finding, production_gate
from app.storage import SQLiteStore


def text_pdf(text: str) -> bytes:
    stream = BytesIO()
    pdf = canvas.Canvas(stream)
    pdf.drawString(72, 760, text)
    pdf.save()
    return stream.getvalue()


def stored_real_upload(store: SQLiteStore, *, case_id: str = "CASE-1"):
    content = text_pdf("Verwendungsnachweis beantragte Erstattung 12.450,00 EUR")
    upload = ingest_pdf("verwendungsnachweis.pdf", content)
    assert upload.extracted_fields
    assert upload.extracted_fields[0].page == 1
    store.save_upload(case_id, upload.model_dump(), tenant_id="tenant-a", content=content)
    return upload, content


def test_real_pdf_finding_stays_blocked_until_named_human_approval_and_history_is_append_only(tmp_path):
    store = SQLiteStore(str(tmp_path / "finding.db"))
    upload, _ = stored_real_upload(store)
    field_name = upload.extracted_fields[0].name

    created = create_finding(
        store,
        tenant_id="tenant-a",
        case_id="CASE-1",
        document_id=upload.document_id,
        field_name=field_name,
        authority_id="bnbest_reimbursement",
        finding_text="The submitted reimbursement amount requires review against the applicable reimbursement rule.",
        trace_id="req-create",
    )
    assert created["decisions"] == []
    assert created["production_gate"]["allow"] is False
    assert "human_decision_pending" in created["production_gate"]["reasons"]
    runtime = created["current_trust_chain"]
    assert runtime["version"] == "trust-chain/v1"
    assert runtime["subject"] == {"type": "case", "id": "CASE-1"}
    assert runtime["evidence"][0]["sourceId"] == upload.document_id
    assert runtime["evidence"][0]["locator"] == {"kind": "page", "value": "1"}
    assert runtime["authority"]["id"] == "bnbest_reimbursement"
    assert runtime["authority"]["version"] == "Stand 26.06.2026"

    approved = decide_finding(
        store,
        tenant_id="tenant-a",
        finding_id=created["finding"]["finding_id"],
        status="approved",
        actor_id="reviewer-alice",
        note="Evidence and authority checked in the original PDF.",
        trace_id="req-approve",
    )
    assert len(approved["decisions"]) == 1
    assert approved["decisions"][0]["status"] == "approved"
    assert approved["decisions"][0]["actor_id"] == "reviewer-alice"
    assert approved["production_gate"]["allow"] is True
    assert approved["production_gate"]["approved_by"] == "reviewer-alice"
    approved_decision_id = approved["decisions"][0]["decision_id"]
    approved_digest = approved["decisions"][0]["chain_sha256"]

    rejected = decide_finding(
        store,
        tenant_id="tenant-a",
        finding_id=created["finding"]["finding_id"],
        status="rejected",
        actor_id="reviewer-bob",
        note="Later review found the prepared conclusion should not be used.",
        trace_id="req-reject",
    )
    assert len(rejected["decisions"]) == 2
    assert rejected["decisions"][0]["decision_id"] == approved_decision_id
    assert rejected["decisions"][0]["chain_sha256"] == approved_digest
    assert rejected["decisions"][1]["status"] == "rejected"
    assert rejected["production_gate"]["allow"] is False
    assert "human_decision_rejected" in rejected["production_gate"]["reasons"]


def test_gate_rechecks_original_bytes_and_closes_after_source_tampering(tmp_path):
    store = SQLiteStore(str(tmp_path / "tamper.db"))
    upload, _ = stored_real_upload(store)
    view = create_finding(
        store,
        tenant_id="tenant-a",
        case_id="CASE-1",
        document_id=upload.document_id,
        field_name=upload.extracted_fields[0].name,
        authority_id="bnbest_reimbursement",
        finding_text="Prepared finding bound to the submitted reimbursement evidence.",
        trace_id="req-create",
    )
    view = decide_finding(
        store,
        tenant_id="tenant-a",
        finding_id=view["finding"]["finding_id"],
        status="approved",
        actor_id="reviewer-alice",
        note="approved",
        trace_id="req-approve",
    )
    assert view["production_gate"]["allow"] is True

    tampered = text_pdf("Different bytes and different evidence 99.999,00 EUR")
    with store._lock, store._connect() as conn:
        conn.execute(
            "UPDATE document_blobs SET content=? WHERE tenant_id=? AND document_id=?",
            (tampered, "tenant-a", upload.document_id),
        )
    gate = production_gate(store, tenant_id="tenant-a", finding_id=view["finding"]["finding_id"])
    assert gate["allow"] is False
    assert "source_integrity_changed" in gate["reasons"]


def test_client_cannot_supply_unknown_authority_or_nonexistent_evidence_field(tmp_path):
    store = SQLiteStore(str(tmp_path / "server-resolved.db"))
    upload, _ = stored_real_upload(store)
    with pytest.raises(FindingError, match="authority_not_found_or_ambiguous"):
        create_finding(
            store,
            tenant_id="tenant-a",
            case_id="CASE-1",
            document_id=upload.document_id,
            field_name=upload.extracted_fields[0].name,
            authority_id="made-up-rule",
            finding_text="finding",
            trace_id="req",
        )
    with pytest.raises(FindingError, match="evidence_field_not_found_or_ambiguous"):
        create_finding(
            store,
            tenant_id="tenant-a",
            case_id="CASE-1",
            document_id=upload.document_id,
            field_name="made-up-field",
            authority_id="bnbest_reimbursement",
            finding_text="finding",
            trace_id="req",
        )


def request_with_principal(*, actor_id: str, role: str) -> Request:
    request = Request({"type": "http", "method": "POST", "path": "/", "headers": []})
    request.state.principal = SimpleNamespace(tenant_id="tenant-a", actor_id=actor_id, role=role)
    return request


def test_production_reviewer_identity_is_derived_from_authenticated_principal(monkeypatch):
    monkeypatch.setattr(findings_api, "production_mode", True)
    request = request_with_principal(actor_id="alice", role="reviewer")
    assert findings_api._reviewer_actor(request) == "alice"

    operator = request_with_principal(actor_id="ops", role="operator")
    with pytest.raises(HTTPException) as exc:
        findings_api._reviewer_actor(operator)
    assert exc.value.status_code == 403
