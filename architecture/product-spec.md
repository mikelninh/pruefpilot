# PrüfPilot — Product Spec

## Core workflow
1. Ingest documents and retain fingerprint/original bytes where configured.
2. Classify/extract into typed case state.
3. Retrieve versioned rules with citations/effective dates.
4. Run deterministic evidence and consistency checks.
5. Show confirmed / partial / missing evidence and uncertainty.
6. Prepare a targeted next action or review memo.
7. Require human approval for the consequential decision.

## Domain-pack model
One shared Case Engine is configured by domain packs defining schemas, required documents, versioned rules, deterministic checks, permissions, output templates and eval cases.

## Acceptance
A reviewer must be able to inspect why a conclusion/action was prepared and identify missing/conflicting evidence before approval.
