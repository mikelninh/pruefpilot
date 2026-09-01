# PrüfPilot — Architecture

## System shape
`documents → typed intake → Case Engine → versioned rules/retrieval → evidence + consistency checks → reviewable action → human approval`

## Production engineering boundary
- API principal binds tenant / actor / role;
- cross-tenant requests fail closed;
- durable Postgres backend for tenant-scoped state;
- original PDF bytes + SHA-256 persisted in v1;
- production writes use idempotency keys;
- reviewer feedback, benchmarks and document state are tenant scoped;
- readiness fails closed until required operational controls are configured.

## Hard-to-reverse choices
Tenant isolation, source-document integrity, rule versioning, authority boundaries and durable audit semantics are RED. Domain-specific extraction/presentation can evolve inside those constraints.
