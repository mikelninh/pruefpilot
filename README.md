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

## Proof at a glance

| Signal | Current repository check |
| --- | ---: |
| Unit + API tests | **22 / 22** |
| Retrieval evals | **10 / 10** |
| Real PDF intake | **implemented** |
| Prompt-injection detection | **implemented** |
| Human-approval boundary | **tested** |

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

## Stack

**Python · FastAPI · Pydantic · pypdf · React · TypeScript · RAG · structured outputs · evals · human-in-the-loop**

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
uvicorn app.main:app --reload
```

## Boundary

PrüfPilot is a working prototype, not a production government system. A real deployment would still require stronger identity and access controls, persistence, observability, retention/deletion workflows, integrations, security review and validation with qualified reviewers.

**No autonomous legal, funding or benefit decisions. Human review remains required.**

---

Built by [Michael Ninh](https://mikelninh.github.io/) in Berlin.
