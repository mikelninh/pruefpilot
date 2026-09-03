# Harness handoff

## Status
Ready for independent verification.

## Current step
Run `python scripts/harness_check.py` plus the existing PrüfPilot CI.

## Evidence
- `AGENTS.md` maps authoritative product, runtime, eval and deployment sources.
- `.harness/project.json` defines sensors, action classes and bounded retries.
- `scripts/harness_check.py` rejects malformed task state and unapproved A3/A4 actions in receipts.
- `.github/workflows/harness.yml` makes the minimum contract continuous.

## Decisions
- Keep existing pytest/eval/readiness gates authoritative.
- Use source provenance and deterministic checks rather than remembered document state.
- Keep Builder and Verifier separate for consequential review logic.
- Do not let a demo or environment flag self-promote to production evidence.

## Failures / uncertainties
CI has not yet produced evidence for this branch.

## Open risks
Harness v0.1 validates process and state invariants; it does not replace document-domain evals or production infrastructure evidence.

## Next owner
Verifier — run CI, inspect failures, and convert any recurring failure into a fixture, validator, rule or policy gate.
