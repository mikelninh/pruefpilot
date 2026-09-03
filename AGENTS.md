# AGENTS.md — PrüfPilot

## Mission
Build a reusable document-review engine that turns source documents into inspectable, evidence-backed review work without hiding uncertainty, formalities, contradictions or production-readiness limits.

## Start here
1. Read `README.md`.
2. Read `.harness/project.json`.
3. Read `.harness/active-task.json` and `.harness/HANDOFF.md`.
4. Load only the domain, architecture or eval material needed for the task.

## Source-of-truth map
- Product and workflow: `README.md`
- Application/runtime: `app/`
- Architecture: `architecture/`, `docs/`
- Evaluation sets and metrics: `evals/`
- Test truth: `tests/`
- Frontend/browser proof: `frontend/`, `proof/`
- Deployment assumptions: `deployments/`, `Dockerfile`, `docker-compose.yml`
- Packaging/dependencies: `pyproject.toml`
- Current work state: `.harness/`
- CI truth: `.github/workflows/ci.yml`

## Contract before work
Every substantial task must define goal, authoritative sources, outputs, constraints, done criteria, forbidden actions, risk class, retry budget and next owner.

Do not silently redefine a review result or call a partial document analysis complete.

## Roles
- Chief: triage, decompose, route and collect.
- Scout: retrieves rules, source documents and factual evidence. Read-only by default.
- Builder: implements extraction, case logic, UI or remediation.
- Verifier: independently runs tests/evals and checks evidence/claims.
- Operator: performs approved deployment or external actions only after policy gates.

## Action classes
- A0 Observe — read/search/analyse. Automatic.
- A1 Local reversible — draft/test/edit isolated work. Automatic.
- A2 Shared reversible — branch, PR, preview, issue. Logged; normally automatic.
- A3 Consequential — deploy, send, publish, write externally. Human approval required.
- A4 High-impact — sensitive document/data egress, destructive production changes, legally consequential actions. Explicit approval plus stronger verification.

Trust the action class, not the agent personality.

## Verification
Minimum harness check:
`python scripts/harness_check.py`

Core project verification:
- `pytest -q`
- `python evals/run_evals.py`

Production-readiness proof is defined in `.github/workflows/ci.yml`; do not infer it from an environment flag alone.

Never claim a test/eval passed unless the command actually ran and its result is captured.

## Durable state
The conversation is not the system of record.
Keep current work in `.harness/active-task.json`.
Keep handoff context in `.harness/HANDOFF.md`.
Keep accepted run receipts in `.harness/receipts/`.

Preferences may live in memory; current documents, rule versions, case state, test results and deployment readiness must be re-opened from authoritative sources.

## Handoffs
A handoff must state status, current step, evidence, decisions, failures/uncertainties, open risks, next owner and exact next action.

Do not pass substantive review logic as chat-only context.

## Retries
Use bounded local repair loops. Default maximum: 3 attempts.
If the same failure repeats twice, improve the rule/check/eval or escalate rather than blindly retrying.

## Failure upgrades
- missing source -> source/retrieval requirement
- wrong extraction -> regression fixture
- bad decision -> deterministic rule/eval
- contradiction missed -> contradiction sensor
- repeated loop -> retry cap/escalation
- unsafe action -> permission gate
- lost decision -> durable state
- unknown failure -> tracing/evidence capture

A production-worthy fix should reduce recurrence across future cases.

## Hard boundaries
- Original documents and authoritative rules beat remembered values.
- Missing evidence must remain missing/unknown, not guessed.
- Derived text must remain traceable to source evidence.
- Synthetic/public demo evidence is not real production evidence.
- Production-readiness claims require the repository's durable-infrastructure gates.
- Sensitive data and credentials never belong in harness state.
- Consequential external actions require explicit authority and evidence.

## Definition of done
Work is done only when the task's done criteria are evidenced, uncertainty and source provenance remain visible, rollback/next step is known, and required approvals are recorded.
