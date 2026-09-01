from __future__ import annotations

from copy import deepcopy

from scripts.validate_external_golden_path import evaluate_run


HASH = "a" * 64


def valid_run():
    return {
        "schema_version": "pruefpilot-external-golden-path/v1",
        "run_id": "run-1",
        "started_at": "2026-09-01T17:00:00Z",
        "completed_at": "2026-09-01T17:10:00Z",
        "case_source_class": "anonymised_real",
        "authorised_to_use": True,
        "sensitive_data_review_complete": True,
        "sources": [{
            "document_id": "doc-1",
            "display_name": "safe.pdf",
            "sha256": HASH,
            "original_retrieval_verified": True,
        }],
        "authorities": [{
            "authority_id": "rule-1",
            "title": "Applicable requirement",
            "version": "2026-08-01",
            "source_url": "https://authority.example/rule",
            "reviewer_opened_source": True,
        }],
        "findings": [{
            "finding_id": "finding-1",
            "finding_text": "Required proof is missing.",
            "reviewer_agrees": True,
            "evidence": [{
                "document_id": "doc-1",
                "page_or_field_locator": "page 2",
                "excerpt_hash": HASH,
                "reviewer_verified_locator": True,
            }],
            "authority_id": "rule-1",
            "derivation_visible": True,
            "reviewer_correction": None,
        }],
        "decision_history": [{
            "decision_id": "decision-1",
            "status": "approved",
            "actor_role": "reviewer",
            "actor_id_or_pseudonymous_id": "reviewer-1",
            "at": "2026-09-01T17:08:00Z",
        }],
        "metrics": {
            "material_findings": 1,
            "exact_locator_coverage": 1,
            "authority_coverage": 1,
            "unsupported_material_findings": 0,
            "reviewer_detected_missed_issues": 0,
            "reviewer_corrections": 0,
            "source_opens": 2,
        },
        "fail_closed_test": {
            "method": "append later rejection in test environment",
            "expected_gate_allow": False,
            "observed_gate_allow": False,
            "observed_reasons": ["human_decision_rejected"],
        },
        "conclusion": {
            "status": "SUPPORTED",
            "statement": "Supported for this single run only.",
            "limitations": ["One run does not establish general accuracy."],
        },
    }


def test_complete_non_synthetic_evidence_pack_can_be_supported():
    result = evaluate_run(valid_run())
    assert result["supported"] is True
    assert result["reasons"] == []


def test_synthetic_run_cannot_be_called_external_golden_path_proof():
    run = valid_run()
    run["case_source_class"] = "synthetic"
    result = evaluate_run(run)
    assert result["supported"] is False
    assert "non_synthetic_case_required" in result["reasons"]


def test_missing_source_verification_or_fail_closed_observation_blocks_supported_claim():
    run = deepcopy(valid_run())
    run["sources"][0]["original_retrieval_verified"] = False
    run["fail_closed_test"]["observed_gate_allow"] = True
    result = evaluate_run(run)
    assert result["supported"] is False
    assert "original_retrieval_not_verified:0" in result["reasons"]
    assert "fail_closed_test_not_proven" in result["reasons"]
    assert "supported_claim_not_allowed_with_open_gaps" in result["reasons"]
