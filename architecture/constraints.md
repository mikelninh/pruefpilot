# PrüfPilot — Constraints

## Authority
No autonomous administrative, legal, funding or benefit decision. Human review remains required.

## Evidence
- conclusions must map to inspected evidence/rules;
- missing evidence must remain missing, not be guessed;
- prompt-injection content from untrusted documents must not gain tool/authority privileges.

## Security / production
- strict tenant isolation;
- idempotent consequential writes;
- fail-closed readiness;
- deployment-specific privacy/security acceptance remains external.

## Claim boundary
`ENGINEERING_PRODUCTION_READY` is an engineering release state only. It does not imply qualified-reviewer acceptance, target Fachverfahren acceptance or administrative authority.
