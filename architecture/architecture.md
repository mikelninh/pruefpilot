<!-- paos:reviewed=2026-09-01 -->
# Architecture

## Product architecture

```text
API principal → tenant + actor + role
                ↓
        controlled Case Engine
 documents · versioned rules · evidence · consistency
                ↓
        domain-specific packs
                ↓
      reviewable next action
                ↓
          HUMAN APPROVAL
```

## Stable core

The shared Case Engine owns document intake, versioned-rule access, evidence states, consistency checks, next-action preparation and approval boundaries.

Domain Packs provide domain schemas, required documents, rule versions, deterministic checks, output templates, permissions and eval cases.

## Production boundary

Controlled-production v1 uses:

- API principal → tenant/actor/role binding;
- strict production CORS;
- tenant-scoped Postgres state;
- original PDF bytes + SHA-256;
- idempotency keys for production uploads;
- readiness gates that fail closed;
- retention / tenant deletion paths.

## Decision reversibility

### GREEN

- reversible extraction/ranking/UI improvements inside existing contracts;
- new synthetic fixtures/regressions;
- domain-pack content updates with versioned evidence and unchanged authority.

### AMBER

- new document types/parsers;
- new external rule/data source;
- changes to domain-pack permission model;
- storage/performance architecture changes;
- integration with a target DMS/Fachverfahren.

### RED

- tenant/identity isolation model;
- retention/deletion semantics;
- formal decision authority;
- production external actions;
- deployment-specific security/privacy acceptance claims;
- stable public API contract changes that would create downstream lock-in.

## Shared-platform relationship

PrüfPilot is the first concrete product wired to the Digital Worker Factory Production Platform v1 contract. Shared infrastructure may be reused; the administrative product still owns its domain rules, evidence semantics and authority boundary.
