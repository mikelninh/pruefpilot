from __future__ import annotations

import hashlib
import json
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
    if human_status == "pending":
        blockers.append("human_decision_pending")
    elif human_status == "rejected":
        blockers.append("human_decision_rejected")
    elif human_status == "approved" and (not human_actor_id or not human_decided_at):
        blockers.append("approval_identity_required")

    assurance = "insufficient"
    structural = [
        blocker for blocker in blockers
        if blocker not in {"source_authenticity_unverified", "human_decision_pending", "human_decision_rejected"}
    ]
    if not structural and source_trust.authenticity.status == "original_as_received":
        assurance = "traceable"
    if not structural and source_trust.authenticity.status == "verified_issuer" and authority.status == "authoritative":
        assurance = "verified"

    production_eligible = (
        assurance in {"traceable", "verified"}
        and human_status == "approved"
        and not blockers
    )

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
        production_eligible=production_eligible,
        blockers=blockers,
    )


def with_human_decision(
    chain: FindingTrustChain,
    *,
    status: str,
    actor_id: str,
    decided_at: str,
    trace_id: str,
) -> FindingTrustChain:
    source_trust = SourceTrustEnvelope(
        authenticity=chain.authenticity,
        integrity=chain.integrity,
        provenance=chain.provenance,
    )
    return build_finding_trust_chain(
        finding_id=chain.finding_id,
        subject_type=chain.subject_type,
        subject_id=chain.subject_id,
        source_trust=source_trust,
        authority=chain.authority,
        evidence=chain.evidence,
        derivation_summary=chain.derivation.summary,
        derivation_method=chain.derivation.method,
        trace_id=trace_id,
        human_status=status,
        human_actor_id=actor_id,
        human_decided_at=decided_at,
    )


def to_runtime_contract(chain: FindingTrustChain) -> dict:
    """Serialize the Python model into the canonical Digital Worker Factory trust-chain/v1 shape."""
    return {
        "version": chain.version,
        "subject": {"type": chain.subject_type, "id": chain.subject_id},
        "authenticity": {
            "status": chain.authenticity.status,
            "method": chain.authenticity.method,
        },
        "integrity": {
            "sha256": chain.integrity.sha256,
            "verified": chain.integrity.verified,
            "version": chain.integrity.version,
            "capturedAt": chain.integrity.captured_at,
        },
        "provenance": {
            "sourceSystem": chain.provenance.source_system,
            "sourceUri": chain.provenance.source_uri,
            "acquiredAt": chain.provenance.acquired_at,
        },
        "authority": {
            "id": chain.authority.id,
            "title": chain.authority.title,
            "version": chain.authority.version,
            "sourceUrl": chain.authority.source_url,
            "status": chain.authority.status,
        },
        "evidence": [
            {
                "id": item.id,
                "sourceId": item.source_id,
                "locator": {"kind": item.locator.kind, "value": item.locator.value},
                "excerptHash": item.excerpt_sha256,
            }
            for item in chain.evidence
        ],
        "derivation": {
            "summary": chain.derivation.summary,
            "method": chain.derivation.method,
            "evidenceIds": list(chain.derivation.evidence_ids),
        },
        "humanDecision": {
            "required": chain.human_decision.required,
            "status": chain.human_decision.status,
            "actorId": chain.human_decision.actor_id,
            "at": chain.human_decision.decided_at,
        },
        "audit": {
            "traceId": chain.audit.trace_id,
            "createdAt": chain.audit.created_at,
        },
    }


def trust_chain_digest(chain: FindingTrustChain) -> str:
    payload = json.dumps(
        to_runtime_contract(chain),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_for_consequential_action(chain: FindingTrustChain, approved_by: str) -> list[str]:
    reasons = list(chain.blockers)
    if not chain.production_eligible:
        reasons.append("finding_not_production_eligible")
    if chain.human_decision.status != "approved":
        reasons.append("human_approval_not_recorded")
    if chain.human_decision.actor_id != approved_by:
        reasons.append("human_approval_mismatch")
    return list(dict.fromkeys(reasons))
