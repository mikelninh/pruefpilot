<!-- paos:reviewed=2026-09-01 -->
# Verification

## Evidence ladder

`DECLARED → STATIC → AUTOMATED → E2E → QUALIFIED REVIEWER → SHADOW → PILOT → PRODUCTION`

## Current engineering evidence

- unit/API tests automated in CI;
- retrieval evals automated;
- real PDF intake implemented;
- prompt-injection detection implemented;
- human-approval boundary tested;
- tenant-scoped Postgres + PDF blob path integration-tested;
- idempotent production upload implemented;
- production readiness fails closed.

These prove bounded engineering properties, not administrative accuracy or authority acceptance.

## Golden-case verification

### GC1 — Infrastructure funding

- [x] synthetic domain flow exists;
- [x] evidence/amount/injection behaviour implemented/testable;
- [ ] qualified reviewer validates representative cases and corrections.

### GC2 — Housing benefit

- [x] completeness/inconsistency workflow exists;
- [ ] reviewer study measures whether targeted evidence requests are correct/useful;
- [ ] real corrections become regressions.

### GC3 — Procurement rule change

- [x] versioned-rule/effective-date architecture exists;
- [ ] representative rule-change impact evaluated by qualified reviewers;
- [ ] target system integration tested under governed conditions.

## Production-gate evidence still missing

- qualified-reviewer accuracy on representative real cases;
- target DMS/Fachverfahren reliability;
- external deployment-specific security/privacy acceptance;
- measured operating SLOs;
- a real backup/restore drill;
- formal administrative authority.

## Next proof level

The best next proof is **qualified humans completing the three golden cases**, with task time, corrections, missing/false evidence states and approval outcomes captured. New features are lower priority than evidence that the current workflow improves real review without weakening authority or traceability.
