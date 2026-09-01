from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .config import settings
from .findings import FindingError, create_finding, decide_finding, get_finding_view, production_gate
from .storage import store

router = APIRouter(tags=["findings"])
production_mode = settings.app_env.strip().lower() == "production"


class FindingCreateRequest(BaseModel):
    document_id: str = Field(min_length=3, max_length=200)
    field_name: str = Field(min_length=1, max_length=200)
    authority_id: str = Field(min_length=2, max_length=200)
    finding_text: str = Field(min_length=3, max_length=2000)


class FindingDecisionRequest(BaseModel):
    status: Literal["approved", "rejected"]
    note: str = Field(default="", max_length=2000)


def _principal(request: Request):
    return getattr(request.state, "principal", None)


def _tenant_id(request: Request) -> str:
    principal = _principal(request)
    return principal.tenant_id if principal else "demo"


def _require_role(request: Request, allowed: set[str]) -> None:
    if not production_mode:
        return
    principal = _principal(request)
    if not principal:
        raise HTTPException(status_code=403, detail="Authenticated production principal required")
    if principal.role not in allowed:
        raise HTTPException(status_code=403, detail="Role not permitted for this finding operation")


def _reviewer_actor(request: Request) -> str:
    if production_mode:
        _require_role(request, {"reviewer", "admin", "owner"})
        principal = _principal(request)
        return principal.actor_id
    return "demo-reviewer"


def _audit(request: Request, event_type: str, payload: dict[str, Any]) -> None:
    principal = _principal(request)
    if not principal or not hasattr(store, "append_audit"):
        return
    store.append_audit(
        tenant_id=principal.tenant_id,
        actor_id=principal.actor_id,
        role=principal.role,
        request_id=getattr(request.state, "request_id", None),
        event_type=event_type,
        payload=payload,
    )


def _raise_finding_error(exc: FindingError) -> None:
    code = str(exc)
    if code in {"document_not_found", "finding_not_found"}:
        raise HTTPException(status_code=404, detail=code) from exc
    if code in {
        "document_case_mismatch", "quarantined_document_cannot_support_finding",
        "source_blob_hash_mismatch", "source_trust_hash_mismatch",
    }:
        raise HTTPException(status_code=409, detail=code) from exc
    raise HTTPException(status_code=422, detail=code) from exc


def _reserve_write(request: Request, *, operation: str) -> tuple[str | None, dict[str, Any] | None]:
    key = request.headers.get("x-idempotency-key")
    if production_mode and not key:
        raise HTTPException(status_code=400, detail="x-idempotency-key is required for production finding writes")
    if not key:
        return None, None
    result = store.reserve_idempotency(tenant_id=_tenant_id(request), operation=operation, key=key)
    if result["created"]:
        return key, None
    if result["response"]:
        return key, result["response"]
    raise HTTPException(status_code=409, detail="Write with this idempotency key is already in progress")


def _complete_write(request: Request, *, operation: str, key: str | None, response: dict[str, Any]) -> None:
    if key:
        store.complete_idempotency(
            tenant_id=_tenant_id(request), operation=operation, key=key, response=response,
        )


@router.post("/cases/{case_id}/findings")
def create_case_finding(case_id: str, payload: FindingCreateRequest, request: Request) -> dict[str, Any]:
    _require_role(request, {"operator", "reviewer", "admin", "owner"})
    operation = f"finding_create:{case_id}"
    idem_key, cached = _reserve_write(request, operation=operation)
    if cached is not None:
        return cached
    try:
        result = create_finding(
            store,
            tenant_id=_tenant_id(request),
            case_id=case_id,
            document_id=payload.document_id,
            field_name=payload.field_name,
            authority_id=payload.authority_id,
            finding_text=payload.finding_text,
            trace_id=getattr(request.state, "request_id", "finding-create"),
        )
    except FindingError as exc:
        _raise_finding_error(exc)
    _complete_write(request, operation=operation, key=idem_key, response=result)
    _audit(request, "finding.created", {
        "finding_id": result["finding"]["finding_id"],
        "case_id": case_id,
        "document_id": payload.document_id,
        "authority_id": payload.authority_id,
    })
    return result


@router.get("/findings/{finding_id}")
def read_finding(finding_id: str, request: Request) -> dict[str, Any]:
    _require_role(request, {"operator", "reviewer", "auditor", "admin", "owner"})
    try:
        return get_finding_view(store, tenant_id=_tenant_id(request), finding_id=finding_id)
    except FindingError as exc:
        _raise_finding_error(exc)


@router.post("/findings/{finding_id}/decisions")
def review_finding(finding_id: str, payload: FindingDecisionRequest, request: Request) -> dict[str, Any]:
    actor_id = _reviewer_actor(request)
    operation = f"finding_decision:{finding_id}"
    idem_key, cached = _reserve_write(request, operation=operation)
    if cached is not None:
        return cached
    try:
        result = decide_finding(
            store,
            tenant_id=_tenant_id(request),
            finding_id=finding_id,
            status=payload.status,
            actor_id=actor_id,
            note=payload.note,
            trace_id=getattr(request.state, "request_id", "finding-decision"),
        )
    except FindingError as exc:
        _raise_finding_error(exc)
    _complete_write(request, operation=operation, key=idem_key, response=result)
    _audit(request, "finding.decision_recorded", {
        "finding_id": finding_id,
        "status": payload.status,
        "actor_id": actor_id,
        "decision_id": result["decisions"][-1]["decision_id"],
    })
    return result


@router.get("/findings/{finding_id}/production-gate")
def check_finding_production_gate(finding_id: str, request: Request) -> dict[str, Any]:
    _require_role(request, {"operator", "reviewer", "auditor", "admin", "owner"})
    try:
        result = production_gate(store, tenant_id=_tenant_id(request), finding_id=finding_id)
    except FindingError as exc:
        _raise_finding_error(exc)
    _audit(request, "finding.production_gate_checked", {
        "finding_id": finding_id,
        "allow": result["allow"],
        "chain_sha256": result["chain_sha256"],
        "decision_id": result["decision_id"],
    })
    return result
