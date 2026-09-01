from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from .models import (
    AuditAnchor,
    AuthorityRecord,
    Citation,
    DerivationRecord,
    FindingEvidence,
    FindingTrustChain,
    HumanDecisionRecord,
    SourceTrustEnvelope,
)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def authority_from_citation(citation: Citation, *, status: str = "authoritative") -> AuthorityRecord:
    return AuthorityRecord(
        id=citation.source_id,
        title=citation.title,
        version=citation.version,
        source_url=citation.source_url,
        status=status,
    )


def evidence_from_upload(*, evidence_id: str, document_id: str, field) -> FindingEvidence:
    if field.page is None:
        raise ValueError("exact_page_required")
    if not field.evidence_sha256:
        raise ValueError("evidence_hash_required")
    return FindingEvidence(
        id=evidence_id,
        source_id=document_id,
        locator={"kind": "page", "value": str(field.page)},
        excerpt=field.evidence,
        excerpt_sha256=field.evidence_sha256,
    )


def build_finding_trust_chain(
    *,
    finding_id: str,
    subject_type: str,
    subject_id: str,
    source_trust: SourceTrustEnvelope,
    authority: AuthorityRecord,
    evidence: list[FindingEvidence],
    derivation_summary: str,
    derivation_method: str,
    trace_id: str,
    human_status: str = "pending",
    human_actor_id: str | None = None,
    human_decided_at: str | None = None,
) -> FindingTrustChain:
    blockers: list[str] = []
    if source_trust.integrity.verified is not True or len(source_trust.integrity.sha256) != 64:
        blockers.append("integrity_not_verified")
    if source_trust.authenticity.status == "unverified":
        blockers.append("source_authenticity_unverified")
    if not evidence:
        blockers.append("exact_evidence_required")
    evidence_ids = {item.id for item in evidence}
    if any(not item.locator.value for item in evidence):
        blockers.append("exact_locator_required")
    if any(item.excerpt_sha256 != sha256_text(item.excerpt) for item in evidence):
        blockers.append("evidence_hash_mismatch")
    if not authority.source_url or not authority.version:
        blockers.append("authority_version_or_source_missing")
    if human_status == "approved" and (not human_actor_id or not human_decided_at):
        blockers.append("approval_identity_required")

    assurance = "insufficient"
    structural = [b for b in blockers if b != "source_authenticity_unverified"]
    if not structural and source_trust.authenticity.status == "original_as_received":
        assurance = "traceable"
    if not structural and source_trust.authenticity.status == "verified_issuer" and authority.status == "authoritative":
        assurance = "verified"

    return FindingTrustChain(
        finding_id=finding_id,
        subject_type=subject_type,
        subject_id=subject_id,
        authenticity=source_trust.authenticity,
        integrity=source_trust.integrity,
        provenance=source_trust.provenance,
        authority=authority,
        evidence=evidence,
        derivation=DerivationRecord(summary=derivation_summary, method=derivation_method, evidence_ids=sorted(evidence_ids)),
        human_decision=HumanDecisionRecord(required=True, status=human_status, actor_id=human_actor_id, decided_at=human_decided_at),
        audit=AuditAnchor(trace_id=trace_id, created_at=datetime.now(timezone.utc).isoformat()),
        assurance=assurance,
        production_eligible=assurance in {"traceable", "verified"} and not blockers,
        blockers=blockers,
    )


def validate_for_consequential_action(chain: FindingTrustChain, approved_by: str) -> list[str]:
    reasons = list(chain.blockers)
    if not chain.production_eligible:
        reasons.append("finding_not_production_eligible")
    if chain.human_decision.status != "approved":
        reasons.append("human_approval_not_recorded")
    if chain.human_decision.actor_id != approved_by:
        reasons.append("human_approval_mismatch")
    return list(dict.fromkeys(reasons))
