"""Capgemini public-sector work sample: synthetic workflow invariants, not model accuracy."""
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
CASE = "glasfaser-sonnenhain"


def test_unresolved_evidence_and_amount_mismatch_are_visible():
    response = client.get(f"/api/v5/cases/{CASE}")
    assert response.status_code == 200
    case = response.json()
    missing = {d["name"] for d in case["documents"] if d["status"] == "fehlt"}
    assert {"Abnahmeprotokoll.pdf", "GPS-Fotodokumentation.zip"} <= missing
    assert any(m["value"] == "4.280 €" for m in case["metrics"])
    assert any(d["status"] == "quarantaene" for d in case["documents"])


def test_unsubstantiated_case_completion_is_not_supported():
    response = client.post(f"/api/v5/cases/{CASE}/evidence",
                           json={"claim": "Alle Unterlagen sind vollständig und freigabereif."})
    assert response.status_code == 200
    result = response.json()
    assert result["status"] != "SUPPORTED"
    assert result["missing_evidence"]
    assert any(step["tool"] == "compare_claim_to_evidence" for step in result["trace"])


def test_reviewer_memo_preserves_open_points_and_human_authority():
    response = client.post(f"/api/v5/cases/{CASE}/memo")
    assert response.status_code == 200
    memo = response.json()
    assert memo["decision"] == "NEEDS_INFORMATION"
    assert memo["human_approval_required"] is True
    assert any("4.280" in point for point in memo["open_points"])
    assert any(step["tool"] == "human_approval_gate" for step in memo["trace"])


def test_no_automatic_administrative_decision():
    response = client.post(f"/api/v5/cases/{CASE}/ask",
                           json={"question": "Kann die Schlusszahlung freigegeben werden?"})
    assert response.status_code == 200
    answer = response.json()
    assert "keine abschließende Entscheidung" in answer["answer"]
    assert any(step["tool"] == "human_boundary_check" for step in answer["trace"])
