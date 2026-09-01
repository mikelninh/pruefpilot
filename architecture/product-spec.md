<!-- paos:reviewed=2026-09-01 -->
# Product specification

## Product loop

```text
documents → structured intake → versioned rules/retrieval → evidence + consistency checks → visible uncertainty → reviewable next action → human approval
```

## Workflow 1 — Infrastructure funding review

The reviewer receives an application/documents and needs to determine completeness, amount consistency and the next review action.

Acceptance:
- required documents/evidence states visible;
- amount inconsistencies surfaced;
- prompt-injection-like instructions in documents quarantined as untrusted content;
- applicable rule/source inspectable;
- recommendation remains a prepared action until human approval.

## Workflow 2 — Housing-benefit completeness

The reviewer needs to identify missing or contradictory evidence and request only what is actually needed.

Acceptance:
- confirmed / partial / missing states are explicit;
- inconsistencies are visible rather than silently resolved;
- targeted missing-evidence request is reviewable;
- no final eligibility/benefit authority is assigned to the model.

## Workflow 3 — Versioned procurement rule change

A rule version/effective date changes and reviewers need to understand the impact on active cases.

Acceptance:
- rule version + effective date are explicit;
- affected cases are identified reproducibly;
- old/new rule evidence remains inspectable;
- impact analysis is separated from final administrative/legal decision;
- reviewer approval remains required.

## Domain-pack contract

The Case Engine owns stable intake/evidence/consistency/approval behaviour. Domain Packs may define schemas, required documents, rules, deterministic checks, templates, permissions and evaluation cases without creating one unconstrained general-purpose agent.

## Failure states

- wrong tenant/case data;
- stale/wrong rule version;
- missing evidence treated as present;
- untrusted document instructions executed as authority;
- duplicated non-idempotent production write;
- human review bypass;
- `ENGINEERING_PRODUCTION_READY` represented as government acceptance.
