from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from .storage import store

router = APIRouter(prefix="/api", tags=["production-operations"])


def _principal(request: Request):
    principal = getattr(request.state, "principal", None)
    if not principal:
        raise HTTPException(status_code=403, detail="Authenticated production principal required")
    return principal


def _require_role(request: Request, allowed: set[str]):
    principal = _principal(request)
    if principal.role not in allowed:
        raise HTTPException(status_code=403, detail="Role not permitted for this operation")
    return principal


def _require_capability(method: str) -> None:
    if not hasattr(store, method):
        raise HTTPException(status_code=503, detail=f"Production storage capability unavailable: {method}")


def _audit(request: Request, event_type: str, payload: dict[str, Any] | None = None) -> None:
    if not hasattr(store, "append_audit"):
        return
    principal = _principal(request)
    store.append_audit(
        tenant_id=principal.tenant_id,
        actor_id=principal.actor_id,
        role=principal.role,
        request_id=getattr(request.state, "request_id", None),
        event_type=event_type,
        payload=payload or {},
    )


@router.post("/jobs")
def enqueue_job(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    principal = _require_role(request, {"operator", "admin", "owner"})
    _require_capability("enqueue_job")
    kind = str(payload.get("kind", "")).strip()
    idempotency_key = str(payload.get("idempotency_key") or request.headers.get("x-idempotency-key") or "").strip()
    if not kind:
        raise HTTPException(status_code=422, detail="kind is required")
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="idempotency_key is required")
    result = store.enqueue_job(
        tenant_id=principal.tenant_id,
        kind=kind,
        payload=payload.get("payload") or {},
        idempotency_key=idempotency_key,
        max_attempts=int(payload.get("max_attempts", 3)),
    )
    _audit(request, "job.enqueued", {"job_id": result["job_id"], "kind": kind, "idempotency_key": idempotency_key})
    return result


@router.post("/jobs/claim")
def claim_job(request: Request) -> dict[str, Any]:
    principal = _require_role(request, {"worker", "operator", "admin", "owner"})
    _require_capability("claim_job")
    job = store.claim_job(tenant_id=principal.tenant_id, worker_id=principal.actor_id)
    if not job:
        return {"job": None}
    _audit(request, "job.claimed", {"job_id": job["job_id"], "attempts": job["attempts"]})
    return {"job": job}


@router.post("/jobs/{job_id}/complete")
def complete_job(job_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    principal = _require_role(request, {"worker", "operator", "admin", "owner"})
    _require_capability("complete_job")
    try:
        result = store.complete_job(tenant_id=principal.tenant_id, job_id=job_id, result=payload.get("result") or {})
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _audit(request, "job.completed", {"job_id": job_id, "attempts": result["attempts"]})
    return result


@router.post("/jobs/{job_id}/fail")
def fail_job(job_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    principal = _require_role(request, {"worker", "operator", "admin", "owner"})
    _require_capability("fail_job")
    try:
        result = store.fail_job(
            tenant_id=principal.tenant_id,
            job_id=job_id,
            error=str(payload.get("error", "job_failed")),
            retry_delay_seconds=int(payload.get("retry_delay_seconds", 0)),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _audit(request, "job.dead_lettered" if result["dead_lettered"] else "job.retry_scheduled", {"job_id": job_id, "attempts": result["attempts"]})
    return result


@router.get("/audit")
def audit_log(request: Request, limit: int = 100) -> dict[str, Any]:
    principal = _require_role(request, {"auditor", "admin", "owner"})
    _require_capability("list_audit")
    return {"tenant_id": principal.tenant_id, "items": store.list_audit(tenant_id=principal.tenant_id, limit=limit)}


@router.post("/admin/retention/run")
def run_retention(request: Request) -> dict[str, Any]:
    principal = _require_role(request, {"admin", "owner"})
    _require_capability("retention_sweep")
    raw_days = os.getenv("PRUEFPILOT_RETENTION_DAYS", "").strip()
    if not raw_days:
        raise HTTPException(status_code=503, detail="PRUEFPILOT_RETENTION_DAYS is not configured")
    result = store.retention_sweep(tenant_id=principal.tenant_id, retention_days=int(raw_days))
    _audit(request, "retention.completed", {"deleted": result, "retention_days": int(raw_days)})
    return {"tenant_id": principal.tenant_id, "deleted": result}


@router.get("/admin/backup")
def backup_tenant(request: Request) -> dict[str, Any]:
    principal = _require_role(request, {"admin", "owner"})
    _require_capability("export_tenant")
    snapshot = store.export_tenant(principal.tenant_id)
    _audit(request, "backup.exported", {"schema": snapshot.get("schema")})
    return snapshot


@router.post("/admin/restore")
def restore_tenant(snapshot: dict[str, Any], request: Request) -> dict[str, Any]:
    principal = _require_role(request, {"admin", "owner"})
    _require_capability("restore_tenant")
    try:
        restored = store.restore_tenant(snapshot, expected_tenant_id=principal.tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit(request, "backup.restored", {"restored": restored, "schema": snapshot.get("schema")})
    return {"tenant_id": principal.tenant_id, "restored": restored}
