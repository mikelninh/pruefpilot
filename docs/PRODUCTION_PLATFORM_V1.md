# PrüfPilot — Production Platform v1

This document describes the **engineering production path**, not a claim that PrüfPilot is an approved production government system.

## Runtime chain

```text
API key
  ↓
tenant + actor + role
  ↓
strict production CORS
  ↓
Postgres 17
  ├─ case / reviewer state
  ├─ original PDF bytes + SHA-256
  ├─ idempotency keys
  ├─ durable audit
  └─ durable jobs
         ↓
     claim by same tenant
         ↓
     bounded retry
         ↓
     dead-letter
  ↓
retention / tenant deletion
  ↓
backup → delete → restore drill
  ↓
/api/ready
```

## Production roles

| Role | Intended capability |
|---|---|
| `reviewer` | bounded review APIs, feedback and source-grounded preparation |
| `worker` | claim/complete/fail jobs for its own tenant |
| `operator` | enqueue and operate bounded jobs for its own tenant |
| `auditor` | inspect tenant-scoped audit events |
| `admin` / `owner` | operations plus retention, backup/restore and tenant deletion |

An API principal is bound to exactly one `tenant_id`, `actor_id` and `role`. A client-supplied `x-tenant-id` that conflicts with the principal is blocked.

## Durable operations endpoints

All endpoints below require an authenticated production principal.

### Queue

- `POST /api/jobs` — enqueue idempotently; operator/admin/owner
- `POST /api/jobs/claim` — claim the oldest available job **for the principal's tenant only**
- `POST /api/jobs/{job_id}/complete` — complete a running tenant job
- `POST /api/jobs/{job_id}/fail` — retry or dead-letter after the bounded attempt budget

Job payloads are secret-redacted before persistence. `idempotency_key` is unique per tenant.

### Audit

- `GET /api/audit?limit=100` — auditor/admin/owner

Audit events contain tenant, actor, role, request ID, event type and a redacted payload. Keys matching secret/token/password/API-key/authorization patterns are stored as `[REDACTED]`.

### Retention

- `POST /api/admin/retention/run` — admin/owner

Uses `PRUEFPILOT_RETENTION_DAYS`. The sweep is tenant-scoped. Old uploads cascade-delete their stored PDF bytes.

### Backup / restore drill

- `GET /api/admin/backup` — admin/owner
- `POST /api/admin/restore` — admin/owner

The v1 backup format is `pruefpilot-tenant-backup/1.0`. It is a **semantic restore harness** that exports tenant-scoped state and original PDF bytes, then can restore that tenant. It is intentionally testable in CI.

This is not a substitute for a managed infrastructure backup policy. `PRUEFPILOT_BACKUP_RESTORE_TESTED=true` should only be set in a deployment after the relevant backup/restore procedure has actually succeeded for that environment.

## Readiness gates

`GET /api/ready` returns success only when all configured engineering gates are true:

- production mode;
- identity/access + tenant binding;
- durable persistence;
- durable original-document storage;
- durable tenant-scoped job queue;
- durable tenant-scoped audit;
- healthy storage connection;
- strict CORS;
- observability configured;
- retention/deletion configured;
- successful backup/restore evidence declared;
- rollback readiness declared;
- tenant-scoped persistence.

SQLite and Vercel `/tmp` deliberately remain red.

## CI proof

The repository CI starts a clean Postgres 17 service and proves:

1. tenant A cannot see/delete tenant B's records or PDF bytes;
2. idempotency is tenant-scoped;
3. job claims are tenant-scoped;
4. duplicate jobs do not create duplicate effects;
5. bounded failures end in dead-letter state;
6. secrets are redacted from persisted job/audit payloads;
7. retention deletes only the intended tenant's expired data;
8. a backup → tenant deletion → restore roundtrip recovers original PDF bytes, audit and queued work;
9. the full configured engineering gate reaches `ENGINEERING_PRODUCTION_READY` on durable infrastructure.

## External gates still required

Code and CI do **not** prove:

- accuracy on representative real administrative cases;
- acceptance by qualified reviewers;
- integration reliability with a target DMS/Fachverfahren;
- deployment-specific penetration/security/privacy acceptance;
- measured live SLO attainment;
- formal administrative authority;
- legal completeness of a domain pack.

Those remain real pilot / operating evidence gates.
