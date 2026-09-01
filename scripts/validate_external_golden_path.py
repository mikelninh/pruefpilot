from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "pruefpilot-external-golden-path/v1"
NON_SYNTHETIC = {"real", "anonymised_real", "deidentified_real"}
SHA256 = re.compile(r"^[a-f0-9]{64}$", re.IGNORECASE)


def validate_run(run: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if run.get("schema_version") != SCHEMA_VERSION:
        reasons.append("schema_version_invalid")
    if run.get("case_source_class") not in NON_SYNTHETIC:
        reasons.append("non_synthetic_case_required")
    if run.get("authorised_to_use") is not True:
        reasons.append("authorisation_to_use_not_proven")
    if run.get("sensitive_data_review_complete") is not True:
        reasons.append("sensitive_data_review_incomplete")
    if not run.get("started_at") or not run.get("completed_at"):
        reasons.append("run_timestamps_incomplete")

    sources = run.get("sources") or []
    if not sources:
        reasons.append("source_required")
    for index, source in enumerate(sources):
        if not source.get("document_id"):
            reasons.append(f"source_document_id_missing:{index}")
        if not SHA256.match(str(source.get("sha256") or "")):
            reasons.append(f"source_sha256_invalid:{index}")
        if source.get("original_retrieval_verified") is not True:
            reasons.append(f"original_retrieval_not_verified:{index}")

    authorities = run.get("authorities") or []
    if not authorities:
        reasons.append("authority_required")
    for index, authority in enumerate(authorities):
        for field in ("authority_id", "title", "version", "source_url"):
            if not authority.get(field):
                reasons.append(f"authority_{field}_missing:{index}")
        if authority.get("reviewer_opened_source") is not True:
            reasons.append(f"authority_not_independently_opened:{index}")

    findings = run.get("findings") or []
    if not findings:
        reasons.append("material_finding_required")
    for index, finding in enumerate(findings):
        if not finding.get("finding_id") or not finding.get("finding_text"):
            reasons.append(f"finding_identity_missing:{index}")
        if not finding.get("authority_id"):
            reasons.append(f"finding_authority_missing:{index}")
        if finding.get("derivation_visible") is not True:
            reasons.append(f"finding_derivation_not_visible:{index}")
        evidence = finding.get("evidence") or []
        if not evidence:
            reasons.append(f"finding_evidence_missing:{index}")
        for ev_index, item in enumerate(evidence):
            if not item.get("document_id") or not item.get("page_or_field_locator"):
                reasons.append(f"exact_evidence_locator_missing:{index}:{ev_index}")
            if not SHA256.match(str(item.get("excerpt_hash") or "")):
                reasons.append(f"evidence_hash_invalid:{index}:{ev_index}")
            if item.get("reviewer_verified_locator") is not True:
                reasons.append(f"evidence_locator_not_verified:{index}:{ev_index}")

    decisions = run.get("decision_history") or []
    if not decisions:
        reasons.append("human_decision_required")
    for index, decision in enumerate(decisions):
        if decision.get("status") not in {"approved", "rejected"}:
            reasons.append(f"decision_status_invalid:{index}")
        if not decision.get("actor_role") or not decision.get("actor_id_or_pseudonymous_id") or not decision.get("at"):
            reasons.append(f"decision_identity_incomplete:{index}")

    metrics = run.get("metrics") or {}
    if metrics.get("exact_locator_coverage") != 1:
        reasons.append("exact_locator_coverage_not_100_percent")
    if metrics.get("authority_coverage") != 1:
        reasons.append("authority_coverage_not_100_percent")
    if metrics.get("unsupported_material_findings") != 0:
        reasons.append("unsupported_material_findings_present")

    failure = run.get("fail_closed_test") or {}
    if failure.get("expected_gate_allow") is not False:
        reasons.append("fail_closed_expectation_invalid")
    if failure.get("observed_gate_allow") is not False:
        reasons.append("fail_closed_test_not_proven")
    if not failure.get("method") or not (failure.get("observed_reasons") or []):
        reasons.append("fail_closed_evidence_incomplete")

    conclusion = run.get("conclusion") or {}
    if conclusion.get("status") == "SUPPORTED" and reasons:
        reasons.append("supported_claim_not_allowed_with_open_gaps")
    return list(dict.fromkeys(reasons))


def evaluate_run(run: dict[str, Any]) -> dict[str, Any]:
    reasons = validate_run(run)
    return {
        "supported": not reasons,
        "status": "SUPPORTED" if not reasons else "NOT_SUPPORTED",
        "reasons": reasons,
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python scripts/validate_external_golden_path.py <run.json>", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    run = json.loads(path.read_text(encoding="utf-8"))
    result = evaluate_run(run)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["supported"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
