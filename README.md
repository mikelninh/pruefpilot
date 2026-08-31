# PrüfPilot 📄

**Document AI for reviewable public-sector workflows.**

PrüfPilot turns documents, versioned rules and evidence gaps into a clear next step for a human reviewer — without pretending the model should make the final decision.

**[Try the live demo →](https://mikelninh.github.io/pruefpilot/)** · **[OpenAPI](https://pruefpilot-v5-api.vercel.app/api/docs)**

## What you can try

Three synthetic cases run through the same controlled case engine:

- **Infrastructure funding** — required documents, amount checks, evidence states and prompt-injection quarantine
- **Housing benefit** — completeness, inconsistencies and targeted requests for missing evidence
- **Procurement rules** — versioned rules, effective dates and impact analysis across active cases

All people, documents and amounts in the public demo are synthetic.

## The workflow

```text
documents
   ↓
structured intake
   ↓
versioned rules + retrieval
   ↓
evidence & consistency checks
   ↓
visible uncertainty
   ↓
reviewable next action
   ↓
human approval
```

The model may extract, retrieve and prepare. **Authority stays outside the model.**

## Production Platform v1 reference implementation

PrüfPilot is the first concrete product wired to the shared Digital Worker Factory production contract.

```text
API principal
  ↓ tenant + actor + role
strict production CORS
  ↓
Postgres 17
  ├─ tenant-scoped case/reviewer state
  ├─ original PDF bytes + SHA-256
  └─ idempotency keys
  ↓
health + /api/ready
  ↓
retention / tenant deletion
```

Implemented now:

- production API principal → tenant/actor/role binding;
- cross-tenant request blocking;
- durable Postgres backend selected by `PRUEFPILOT_DATABASE_URL`;
- original uploaded PDF bytes persisted tenant-scoped in Postgres BYTEA in v1;
- production uploads require `x-idempotency-key` and replay the recorded result instead of creating a duplicate write;
- tenant-scoped reviewer feedback, benchmarks and document state;
- admin/owner tenant-data deletion endpoint;
- storage health surfaced in `/api/health`;
- `/api/ready` fails closed until durable persistence/object storage, tenant isolation, strict CORS, observability, retention, backup/restore evidence and rollback are all configured;
- CI boots a real Postgres 17 service and exercises the production storage path.

`ENGINEERING_PRODUCTION_READY` is an engineering release state only. It does **not** mean qualified public-sector reviewers, external security teams or target Fachverfahren have accepted the system.

## Proof at a glance

| Signal | Current repository check |
| --- | ---: |
| Unit + API tests | automated in CI |
| Retrieval evals | automated in CI |
| Real PDF intake | **implemented** |
| Prompt-injection detection | **implemented** |
| Human-approval boundary | **tested** |
| Tenant-scoped Postgres + PDF blob storage | **integration-tested in CI** |
| Idempotent production upload | **implemented** |
| Production readiness | **fail-closed** |

These are engineering evaluations, not claims of production accuracy.

## What is implemented

- FastAPI document intake and typed contracts
- PDF extraction with SHA-256 fingerprints
- document classification and field extraction
- versioned rule retrieval with citations
- evidence states: confirmed / partial / missing
- prompt-injection detection for untrusted documents
- bounded agent/tool workflows with visible traces
- review memos and explicit human-approval boundaries
- reusable domain packs
- controlled-production identity/tenant boundary
- durable Postgres production backend
- idempotent upload writes
- tenant deletion and readiness gates

## Architecture

PrüfPilot uses a shared **Case Engine + Domain Packs** rather than one giant general-purpose agent.

```text
Case Engine
├── document intake
├── versioned rules
├── evidence checks
├── consistency checks
├── next-action preparation
└── human approval
       ↑
   Domain Packs
```

A domain pack can define schemas, required documents, versioned rules, deterministic checks, output templates, permissions and evaluation cases.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
uvicorn app.main:app --reload
```

For the Postgres backend:

```bash
pip install -e ".[dev,postgres]"
export PRUEFPILOT_DATABASE_URL='postgresql://...'
```

## Boundary

PrüfPilot is now a **controlled production engineering candidate**, not a production government system.

Still external/unproven:

- qualified-reviewer accuracy on representative real cases;
- target DMS/Fachverfahren integration reliability;
- deployment-specific external security/privacy acceptance;
- measured operating SLOs and a real backup/restore drill;
- formal administrative authority.

**No autonomous legal, funding or benefit decisions. Human review remains required.**

---

Built by [Michael Ninh](https://mikelninh.github.io/) in Berlin.
