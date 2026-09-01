from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any

from .data import load_rules
from .document_ai import extract_pdf_text
from .models import Citation, FindingTrustChain, UploadResult
from .trust import (
    authority_from_citation,
    build_finding_trust_chain,
    evidence_from_upload,
    to_runtime_contract,
    trust_chain_digest,
    validate_for_consequential_action,
    with_human_decision,
)


class FindingError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rule(authority_id: str) -> dict[str, Any]:
    matches = [rule for rule in load_rules() if rule.get("id") == authority_id]
    if len(matches) != 1:
        raise FindingError("authority_not_found_or_ambiguous")
    return matches[0]


def _field(upload: UploadResult, field_name: str):
    matches = [field for field in upload.extracted_fields if field.name == field_name]
    if len(matches) != 1:
        raise FindingError("evidence_field_not_found_or_ambiguous")
    return matches[0]


def _verify_upload_source(store, *, tenant_id: str, document_id: str, upload: UploadResult) -> bytes:
    blob = store.get_blob(document_id, tenant_id=tenant_id)
    if blob is None:
        raise FindingError("source_blob_missing")
    digest = hashlib.sha256(blob).hexdigest()
    if digest != upload.sha256:
        raise FindingError("source_blob_hash_mismatch")
    if digest != upload.source_trust.integrity.sha256:
        raise FindingError("source_trust_hash_mismatch")
    if upload.source_trust.integrity.verified is not True:
        raise FindingError("source_integrity_not_verified")
    return blob


def create_finding(
    store,
    *,
    tenant_id: str,
    case_id: str,
    document_id: str,
    field_name: str,
    authority_id: str,
    finding_text: str,
    trace_id: str,
) -> dict[str, Any]:
    if not hasattr(store, "get_upload_record") or not hasattr(store, "save_finding"):
        raise FindingError("finding_storage_unavailable")
    record = store.get_upload_record(document_id, tenant_id=tenant_id)
    if not record:
        raise FindingError("document_not_found")
    if record["case_id"] != case_id:
        raise FindingError("document_case_mismatch")

    upload = UploadResult.model_validate(record["payload"])
    if upload.status == "quarantined":
        raise FindingError("quarantined_document_cannot_support_finding")
    _verify_upload_source(store, tenant_id=tenant_id, document_id=document_id, upload=upload)

    field = _field(upload, field_name)
    evidence_id = f"ev_{uuid.uuid4().hex[:12]}"
    try:
        evidence = evidence_from_upload(evidence_id=evidence_id, document_id=document_id, field=field)
    except ValueError as exc:
        raise FindingError(str(exc)) from exc

    rule = _rule(authority_id)
    citation = Citation(
        source_id=rule["id"],
        title=rule["title"],
        version=rule["version"],
        page=rule["page"],
        section=rule["section"],
        source_url=rule["source_url"],
        confidence=1.0,
    )
    authority = authority_from_citation(citation)
    finding_id = f"finding_{uuid.uuid4().hex[:16]}"
    chain = build_finding_trust_chain(
        finding_id=finding_id,
        subject_type="case",
        subject_id=case_id,
        source_trust=upload.source_trust,
        authority=authority,
        evidence=[evidence],
        derivation_summary=finding_text.strip(),
        derivation_method="pruefpilot_rule_evidence_check/v1",
        trace_id=trace_id,
    )
    created_at = _now()
    payload = {
        "finding_id": finding_id,
        "case_id": case_id,
        "document_id": document_id,
        "field_name": field_name,
        "authority_id": authority_id,
        "finding_text": finding_text.strip(),
        "created_at": created_at,
        "trust_chain": chain.model_dump(mode="json"),
        "runtime_trust_chain": to_runtime_contract(chain),
        "chain_sha256": trust_chain_digest(chain),
    }
    store.save_finding(payload, tenant_id=tenant_id)
    return get_finding_view(store, tenant_id=tenant_id, finding_id=finding_id)


def decide_finding(
    store,
    *,
    tenant_id: str,
    finding_id: str,
    status: str,
    actor_id: str,
    note: str,
    trace_id: str,
) -> dict[str, Any]:
    if status not in {"approved", "rejected"}:
        raise FindingError("decision_status_invalid")
    if not actor_id.strip():
        raise FindingError("reviewer_identity_required")
    finding = store.get_finding(finding_id, tenant_id=tenant_id)
    if not finding:
        raise FindingError("finding_not_found")

    base_chain = FindingTrustChain.model_validate(finding["trust_chain"])
    decided_at = _now()
    chain = with_human_decision(
        base_chain,
        status=status,
        actor_id=actor_id,
        decided_at=decided_at,
        trace_id=trace_id,
    )
    decision = {
        "decision_id": f"decision_{uuid.uuid4().hex[:16]}",
        "finding_id": finding_id,
        "status": status,
        "actor_id": actor_id,
        "note": note.strip(),
        "created_at": decided_at,
        "trust_chain": chain.model_dump(mode="json"),
        "runtime_trust_chain": to_runtime_contract(chain),
        "chain_sha256": trust_chain_digest(chain),
    }
    store.append_finding_decision(decision, tenant_id=tenant_id)
    return get_finding_view(store, tenant_id=tenant_id, finding_id=finding_id)


def _verify_authority(chain: FindingTrustChain) -> list[str]:
    try:
        rule = _rule(chain.authority.id)
    except FindingError:
        return ["authority_no_longer_resolves"]
    reasons: list[str] = []
    if rule.get("version") != chain.authority.version:
        reasons.append("authority_version_mismatch")
    if rule.get("source_url") != chain.authority.source_url:
        reasons.append("authority_source_mismatch")
    if rule.get("title") != chain.authority.title:
        reasons.append("authority_title_mismatch")
    return reasons


def _verify_evidence_at_source(chain: FindingTrustChain, blob: bytes) -> list[str]:
    reasons: list[str] = []
    try:
        parsed = extract_pdf_text(blob)
    except Exception:
        return ["source_reparse_failed"]
    for item in chain.evidence:
        if hashlib.sha256(item.excerpt.encode("utf-8")).hexdigest() != item.excerpt_sha256:
            reasons.append(f"evidence_hash_mismatch:{item.id}")
            continue
        if item.locator.kind != "page":
            reasons.append(f"unsupported_evidence_locator:{item.id}")
            continue
        try:
            page = int(item.locator.value)
        except ValueError:
            reasons.append(f"evidence_page_invalid:{item.id}")
            continue
        if page < 1 or page > len(parsed.page_texts):
            reasons.append(f"evidence_page_out_of_range:{item.id}")
            continue
        page_text = " ".join(parsed.page_texts[page - 1].split()).lower()
        excerpt = " ".join(item.excerpt.split()).lower()
        if not excerpt or excerpt not in page_text:
            reasons.append(f"evidence_not_found_at_locator:{item.id}")
    return reasons


def production_gate(store, *, tenant_id: str, finding_id: str) -> dict[str, Any]:
    finding = store.get_finding(finding_id, tenant_id=tenant_id)
    if not finding:
        raise FindingError("finding_not_found")
    decisions = store.list_finding_decisions(finding_id, tenant_id=tenant_id)
    current = decisions[-1] if decisions else finding
    chain = FindingTrustChain.model_validate(current["trust_chain"])

    reasons: list[str] = []
    recomputed_digest = trust_chain_digest(chain)
    if current.get("chain_sha256") != recomputed_digest:
        reasons.append("trust_chain_digest_mismatch")

    approved_by = chain.human_decision.actor_id or ""
    reasons.extend(validate_for_consequential_action(chain, approved_by))
    if decisions:
        latest = decisions[-1]
        if latest.get("status") != chain.human_decision.status:
            reasons.append("decision_status_chain_mismatch")
        if latest.get("actor_id") != chain.human_decision.actor_id:
            reasons.append("decision_actor_chain_mismatch")

    upload_record = store.get_upload_record(finding["document_id"], tenant_id=tenant_id)
    if not upload_record:
        reasons.append("source_upload_missing")
    else:
        upload = UploadResult.model_validate(upload_record["payload"])
        blob = store.get_blob(finding["document_id"], tenant_id=tenant_id)
        if blob is None:
            reasons.append("source_blob_missing")
        else:
            digest = hashlib.sha256(blob).hexdigest()
            if digest != chain.integrity.sha256 or digest != upload.sha256:
                reasons.append("source_integrity_changed")
            else:
                reasons.extend(_verify_evidence_at_source(chain, blob))

    reasons.extend(_verify_authority(chain))
    reasons = list(dict.fromkeys(reasons))
    return {
        "allow": len(reasons) == 0,
        "finding_id": finding_id,
        "assurance": chain.assurance,
        "chain_sha256": recomputed_digest,
        "decision_id": decisions[-1]["decision_id"] if decisions else None,
        "approved_by": chain.human_decision.actor_id,
        "reasons": reasons,
        "runtime_trust_chain": to_runtime_contract(chain),
    }


def get_finding_view(store, *, tenant_id: str, finding_id: str) -> dict[str, Any]:
    finding = store.get_finding(finding_id, tenant_id=tenant_id)
    if not finding:
        raise FindingError("finding_not_found")
    decisions = store.list_finding_decisions(finding_id, tenant_id=tenant_id)
    gate = production_gate(store, tenant_id=tenant_id, finding_id=finding_id)
    return {
        "finding": finding,
        "decisions": decisions,
        "current_trust_chain": gate["runtime_trust_chain"],
        "production_gate": {key: value for key, value in gate.items() if key != "runtime_trust_chain"},
    }
