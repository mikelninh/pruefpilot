from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Principal:
    tenant_id: str
    actor_id: str
    role: str


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_api_principals(raw: str | None = None) -> dict[str, Principal]:
    raw = raw if raw is not None else os.getenv("PRUEFPILOT_API_PRINCIPALS", "{}")
    try:
        payload: dict[str, Any] = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError("PRUEFPILOT_API_PRINCIPALS must be valid JSON") from exc
    principals: dict[str, Principal] = {}
    for api_key, item in payload.items():
        if not isinstance(api_key, str) or not api_key or not isinstance(item, dict):
            continue
        tenant_id = str(item.get("tenant_id", "")).strip()
        actor_id = str(item.get("actor_id", "")).strip()
        role = str(item.get("role", "")).strip()
        if tenant_id and actor_id and role:
            principals[api_key] = Principal(tenant_id=tenant_id, actor_id=actor_id, role=role)
    return principals


def authenticate_api_key(candidate: str | None, principals: dict[str, Principal]) -> Principal | None:
    if not candidate:
        return None
    for api_key, principal in principals.items():
        if hmac.compare_digest(candidate, api_key):
            return principal
    return None


def fingerprint_actor(principal: Principal | None) -> str | None:
    if not principal:
        return None
    value = f"{principal.tenant_id}:{principal.actor_id}:{principal.role}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()[:16]


def production_readiness(
    *,
    app_env: str,
    store_mode: str,
    allowed_origins: tuple[str, ...],
    tenant_scoped_persistence: bool,
    object_store_durable: bool = False,
    storage_health: dict[str, Any] | None = None,
) -> dict[str, Any]:
    principals = load_api_principals()
    production = app_env.strip().lower() == "production"
    storage_health = storage_health or {"ok": False}
    gates = {
        "production_mode": production,
        "identity_and_access": bool(principals),
        "tenant_principal_binding": bool(principals),
        "durable_persistence": store_mode in {"postgres-durable", "external-durable"},
        "durable_object_storage": bool(object_store_durable),
        "durable_queue": bool(storage_health.get("queue_durable")),
        "durable_audit": bool(storage_health.get("audit_durable")),
        "storage_health": bool(storage_health.get("ok")),
        "strict_cors": "*" not in allowed_origins,
        "observability_configured": _bool_env("PRUEFPILOT_OBSERVABILITY_ENABLED"),
        "retention_deletion_configured": bool(os.getenv("PRUEFPILOT_RETENTION_DAYS")),
        "backup_restore_evidence": _bool_env("PRUEFPILOT_BACKUP_RESTORE_TESTED"),
        "rollback_runbook": _bool_env("PRUEFPILOT_ROLLBACK_READY"),
        "tenant_scoped_persistence": bool(tenant_scoped_persistence),
    }
    required = [
        "identity_and_access", "tenant_principal_binding", "durable_persistence", "durable_object_storage",
        "durable_queue", "durable_audit", "storage_health", "strict_cors", "observability_configured",
        "retention_deletion_configured", "backup_restore_evidence", "rollback_runbook", "tenant_scoped_persistence",
    ]
    missing = [name for name in required if not gates[name]]
    return {
        "ready": production and not missing,
        "stage": "ENGINEERING_PRODUCTION_READY" if production and not missing else "CONTROLLED_PRODUCTION_CANDIDATE" if production else "DEMO_OR_PILOT",
        "gates": gates,
        "missing": missing,
        "storage": storage_health,
        "truth_boundary": (
            "Engineering readiness does not prove reviewer accuracy, legal/administrative authority, "
            "security acceptance or production integration reliability."
        ),
    }
