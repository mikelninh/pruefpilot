from app.models import Citation, ExtractedField, SourceTrustEnvelope
from app.trust import (
    authority_from_citation,
    build_finding_trust_chain,
    evidence_from_upload,
    to_runtime_contract,
    trust_chain_digest,
    validate_for_consequential_action,
    with_human_decision,
)


def source_trust() -> SourceTrustEnvelope:
    return SourceTrustEnvelope.model_validate({
        "authenticity": {"status": "original_as_received", "method": "raw_pdf_capture"},
        "integrity": {"sha256": "a" * 64, "verified": True, "version": "sha256:aaaaaaaaaaaaaaaa", "captured_at": "2026-09-01T12:00:00Z"},
        "provenance": {"source_system": "pruefpilot_upload", "source_uri": "pruefpilot://upload/doc-1", "acquired_at": "2026-09-01T12:00:00Z"},
    })


def test_traceable_finding_is_not_executable_while_human_decision_is_pending():
    import hashlib
    field = ExtractedField(name="Betrag", value="12.450 EUR", confidence=0.95, evidence="12.450", page=2, evidence_sha256=hashlib.sha256(b"12.450").hexdigest())
    evidence = evidence_from_upload(evidence_id="ev-amount", document_id="doc-1", field=field)
    citation = Citation(source_id="rule-1", title="Official rule", version="2026-08-01", page=4, section="4.2", source_url="https://authority.example/rule.pdf", confidence=0.99)
    chain = build_finding_trust_chain(
        finding_id="finding-1", subject_type="case", subject_id="case-1", source_trust=source_trust(),
        authority=authority_from_citation(citation), evidence=[evidence],
        derivation_summary="The submitted amount is compared with the applicable requirement.", derivation_method="deterministic_rule_check", trace_id="trace-1",
    )
    assert chain.assurance == "traceable"
    assert chain.production_eligible is False
    assert "human_decision_pending" in chain.blockers
    reasons = validate_for_consequential_action(chain, "reviewer-1")
    assert "finding_not_production_eligible" in reasons
    assert "human_approval_not_recorded" in reasons


def test_consequential_action_requires_matching_recorded_human_approval():
    import hashlib
    field = ExtractedField(name="Betrag", value="12.450 EUR", confidence=0.95, evidence="12.450", page=2, evidence_sha256=hashlib.sha256(b"12.450").hexdigest())
    evidence = evidence_from_upload(evidence_id="ev-amount", document_id="doc-1", field=field)
    citation = Citation(source_id="rule-1", title="Official rule", version="2026-08-01", page=4, section="4.2", source_url="https://authority.example/rule.pdf", confidence=0.99)
    pending = build_finding_trust_chain(
        finding_id="finding-1", subject_type="case", subject_id="case-1", source_trust=source_trust(),
        authority=authority_from_citation(citation), evidence=[evidence], derivation_summary="Evidence and rule support the prepared finding.",
        derivation_method="deterministic_rule_check", trace_id="trace-1",
    )
    chain = with_human_decision(
        pending, status="approved", actor_id="reviewer-1", decided_at="2026-09-01T12:05:00Z", trace_id="trace-2",
    )
    assert chain.production_eligible is True
    assert chain.blockers == []
    assert validate_for_consequential_action(chain, "reviewer-1") == []
    assert "human_approval_mismatch" in validate_for_consequential_action(chain, "reviewer-2")


def test_runtime_contract_matches_shared_digital_worker_factory_shape():
    import hashlib
    field = ExtractedField(name="Betrag", value="1 EUR", confidence=0.9, evidence="1", page=1, evidence_sha256=hashlib.sha256(b"1").hexdigest())
    evidence = evidence_from_upload(evidence_id="ev-1", document_id="doc-1", field=field)
    citation = Citation(source_id="rule-1", title="Rule", version="v1", page=1, section="1", source_url="https://authority.example/rule", confidence=0.9)
    chain = build_finding_trust_chain(
        finding_id="f", subject_type="case", subject_id="c", source_trust=source_trust(),
        authority=authority_from_citation(citation), evidence=[evidence], derivation_summary="summary",
        derivation_method="rule", trace_id="t",
    )
    runtime = to_runtime_contract(chain)
    assert runtime["version"] == "trust-chain/v1"
    assert runtime["subject"] == {"type": "case", "id": "c"}
    assert runtime["integrity"]["capturedAt"] == "2026-09-01T12:00:00Z"
    assert runtime["provenance"]["sourceUri"] == "pruefpilot://upload/doc-1"
    assert runtime["evidence"][0]["sourceId"] == "doc-1"
    assert runtime["evidence"][0]["excerptHash"] == hashlib.sha256(b"1").hexdigest()
    assert runtime["humanDecision"]["status"] == "pending"
    assert len(trust_chain_digest(chain)) == 64


def test_unverified_source_never_becomes_production_eligible():
    trust = source_trust()
    trust.authenticity.status = "unverified"
    import hashlib
    field = ExtractedField(name="Betrag", value="1 EUR", confidence=0.9, evidence="1", page=1, evidence_sha256=hashlib.sha256(b"1").hexdigest())
    evidence = evidence_from_upload(evidence_id="ev-1", document_id="doc-1", field=field)
    citation = Citation(source_id="rule-1", title="Rule", version="v1", page=1, section="1", source_url="https://authority.example/rule", confidence=0.9)
    chain = build_finding_trust_chain(finding_id="f", subject_type="case", subject_id="c", source_trust=trust, authority=authority_from_citation(citation), evidence=[evidence], derivation_summary="summary", derivation_method="rule", trace_id="t")
    assert chain.production_eligible is False
    assert "source_authenticity_unverified" in chain.blockers
