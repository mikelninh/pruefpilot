# PrüfPilot — Verification

## Evidence today
- unit + API tests in CI;
- retrieval evals in CI;
- real PDF intake;
- prompt-injection detection;
- tested human-approval boundary;
- tenant-scoped Postgres + PDF storage integration tests;
- idempotent production upload;
- fail-closed production readiness;
- durable queue/audit/restore operating path.

## External / unproven
- qualified-reviewer accuracy on representative real cases;
- target DMS/Fachverfahren reliability;
- external security/privacy acceptance;
- measured operating SLOs in a real deployment;
- formal administrative authority.

## Next proof
Run three representative reviewer workflows with qualified users and record time, corrections, evidence misses, rule/citation failures and whether the prepared next action was actually useful.
