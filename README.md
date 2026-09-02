# PrüfPilot 📄

**Turn document review into a clear path to resolution — not just a list of problems.**

PrüfPilot takes document packs, versioned rules and evidence requirements and turns them into reviewable findings, exact next actions and prepared hand-offs. The model may extract, compare and propose; **authority stays outside the model**.

**[Try the 60-second workflow →](https://mikelninh.github.io/pruefpilot/)** · **[OpenAPI →](https://pruefpilot-v5-api.vercel.app/api/docs)**

## Three cases, one workflow

The public demo shows three synthetic review paths:

1. **Funding · missing evidence** → identify the exact missing proofs, prepare the applicant request, move the case to `Waiting for applicant`.
2. **Travel · policy exception** → explain the €144 mismatch, prepare correction or exception review, move the case to `Waiting for correction / justification`.
3. **Funding · complete pack** → checks pass, evidence is inspectable, human approves and releases the prepared outcome.

The important pattern is:

```text
documents
   ↓
structured intake
   ↓
versioned rules + evidence requirements
   ↓
checks + contradictions
   ↓
explain the finding
   ↓
prepare the smallest useful next action
   ↓
human / policy authority
   ↓
re-check when new evidence arrives
```

## What is implemented

- FastAPI document intake and typed contracts
- real PDF extraction with SHA-256 fingerprints
- document classification and structured field extraction
- versioned rule retrieval with citations
- evidence states: confirmed / partial / missing
- consistency and amount checks
- prompt-injection detection for untrusted documents
- bounded agent/tool workflows with visible traces
- prepared reviewer memos and hand-offs
- explicit human approval boundaries
- reusable domain packs
- tenant/actor/role binding for controlled-production paths
- durable Postgres backend and tenant-scoped document state
- idempotent production uploads
- readiness gates that fail closed

## Production shape

```text
API principal
   ↓ tenant + actor + role
strict CORS
   ↓
Postgres 17
   ├─ tenant-scoped case/reviewer state
   ├─ original PDF bytes + SHA-256
   └─ idempotency keys
   ↓
checks + prepared action
   ↓
human / policy gate
```

`ENGINEERING_PRODUCTION_READY` is an engineering release state only. It does **not** mean a public authority, external security team or target Fachverfahren has accepted the system.

## Proof at a glance

| Signal | Current state |
| --- | --- |
| Real PDF intake | implemented |
| Versioned rule / evidence checks | implemented |
| Prompt-injection detection | implemented |
| Human approval boundary | tested |
| Tenant-scoped Postgres path | integration-tested in CI |
| Idempotent production upload | implemented |
| Public resolution flow | browser-tested |
| Production readiness | fail-closed |

These are engineering evaluations, not claims of production accuracy.

## Autonomy policy

PrüfPilot should not auto-release because a model is “confident.” Release authority belongs to the workflow and risk tier.

```text
SHADOW / REVIEW → HUMAN RELEASE → BOUNDED AUTO-RELEASE
```

Low-risk, stable case classes can earn broader automation after enough reviewed evidence. High-impact decisions can remain human-only indefinitely.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
uvicorn app.main:app --reload
```

For Postgres:

```bash
pip install -e ".[dev,postgres]"
export PRUEFPILOT_DATABASE_URL='postgresql://...'
```

## Boundary

PrüfPilot is a **controlled-production engineering candidate**, not a validated government decision system.

Still external/unproven: qualified-reviewer accuracy on representative real cases, target DMS/Fachverfahren integrations, deployment-specific security/privacy acceptance, measured operating SLOs and formal administrative authority.

**No autonomous legal, funding or benefit decisions.**

---

Built by [Michael Ninh](https://mikelninh.github.io/) in Berlin.
