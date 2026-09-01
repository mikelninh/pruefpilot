from __future__ import annotations

from io import BytesIO
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from app.main import app

client = TestClient(app)


def blank_pdf() -> bytes:
    stream = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    writer.write(stream)
    return stream.getvalue()


def test_health_and_openapi():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["x-request-id"].startswith("req_")
    assert client.get("/api/openapi.json").status_code == 200


def test_queue_endpoint():
    response = client.get("/api/queue")
    assert response.status_code == 200
    assert response.json()[0]["case_id"] == "GF-2026-014"


def test_upload_rejects_non_pdf():
    response = client.post("/api/upload", files={"file": ("note.txt", b"hello", "text/plain")})
    assert response.status_code == 415


def test_upload_processes_real_pdf_captures_source_trust_and_serves_original():
    pdf = blank_pdf()
    response = client.post("/api/upload", files={"file": ("demo.pdf", pdf, "application/pdf")})
    assert response.status_code == 200
    payload = response.json()
    assert payload["page_count"] == 1
    assert len(payload["sha256"]) == 64
    assert payload["status"] in {"ready", "manual_review"}
    trust = payload["source_trust"]
    assert trust["authenticity"]["status"] == "original_as_received"
    assert trust["integrity"]["verified"] is True
    assert trust["integrity"]["sha256"] == payload["sha256"]
    assert trust["provenance"]["source_uri"].endswith(payload["document_id"])
    assert any(step["tool"] == "capture_source_provenance" for step in payload["trace"])

    original = client.get(f'/api/documents/{payload["document_id"]}/original')
    assert original.status_code == 200
    assert original.content == pdf
    assert original.headers["content-type"].startswith("application/pdf")
    assert original.headers["x-document-sha256"] == payload["sha256"]
    assert original.headers["x-source-integrity"] == "sha256-recomputed-on-read"
    assert original.headers["cache-control"] == "private, no-store"


def test_original_document_is_tenant_scoped_by_storage_key():
    response = client.get("/api/documents/not-a-real-document/original")
    assert response.status_code == 404


def test_feedback_endpoint():
    response = client.post("/api/feedback", json={
        "case_id": "GF-2026-014",
        "document_id": "D05",
        "field_name": "amount",
        "previous_value": "730000",
        "corrected_value": "734280",
        "note": "Review correction",
    })
    assert response.status_code == 200
    assert response.json()["eval_case"]["expected"] == "734280"


def test_benchmark_endpoint():
    response = client.post("/api/benchmark/run", json={"providers": ["deterministic", "openai"]})
    assert response.status_code == 200
    metrics = response.json()["metrics"]
    assert metrics[0]["status"] == "measured"
    assert metrics[1]["status"] == "not_configured"
