<!-- paos:reviewed=2026-09-01 -->
# Constraints

## Authority

- no autonomous legal, funding, benefit or procurement decision;
- human review remains required for consequential case outcomes;
- formal administrative authority is external/unproven and may not be implied by product readiness.

## Evidence

- evidence states remain explicit: confirmed / partial / missing;
- rule version and effective date are inspectable;
- uncertainty may not be converted into a confident final answer;
- prompt-injection-like instructions inside documents are untrusted content, not system authority;
- generated review memos remain distinguishable from source evidence.

## Production boundary

- production requests bind tenant + actor + role;
- cross-tenant access is blocked;
- writes requiring idempotency must not duplicate on replay;
- readiness fails closed when durable storage, isolation, CORS, observability, retention, backup/restore or rollback requirements are not satisfied;
- tenant deletion/retention semantics must remain explicit.

## Product truth

- engineering production readiness ≠ target authority acceptance;
- automated retrieval/document evals ≠ qualified-reviewer accuracy on representative real cases;
- integration-tested Postgres/PDF storage ≠ target Fachverfahren reliability;
- a synthetic domain pack ≠ proven generality across public administration.

## External evidence still required

- qualified-reviewer accuracy;
- target DMS/Fachverfahren integration reliability;
- deployment-specific external security/privacy acceptance;
- measured operating SLOs + real backup/restore drill;
- formal administrative authority.
