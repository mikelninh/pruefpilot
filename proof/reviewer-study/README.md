# PrüfPilot reviewer-quality study v1

## Purpose
This pack tests a question the synthetic benchmark cannot answer on its own: **are PrüfPilot findings, evidence, uncertainty and next actions actually useful to a qualified human reviewer?**

It sits above the existing deterministic fixtures in `data/benchmark_cases.json` and retrieval checks in `evals/eval_cases.json`.

This study **does not establish general accuracy, production readiness, legal correctness or real-world benefit**. One reviewer can provide valuable correction evidence; broader claims require a larger preregistered evaluation with independent reviewers.

## Study design
- 8 synthetic cases selected for ordinary, incomplete, ambiguous, rule-dependent, multi-document and adversarial review situations.
- No production or sensitive documents.
- Reviewer scores five dimensions: correctness, evidence traceability, uncertainty honesty, next-action usefulness and handoff quality.
- Every disagreement, correction, unsupported finding and missed issue is retained.
- Critical safety failures cannot be averaged away by strong scores elsewhere.

## Reviewer workflow
1. Pin the exact PrüfPilot commit being reviewed.
2. Open `cases.json` and work through the cases in order.
3. For each case, inspect the referenced synthetic fixture and the PrüfPilot output produced from that pinned commit.
4. Score with `rubric.json`.
5. Copy `response-template.json`, fill every case record, and keep corrections verbatim.
6. Run `python scripts/validate_reviewer_study.py --response <filled-response.json>`.
7. Summarise results as **SUPPORTED / FAILED / UNKNOWN**. Do not publish a stronger claim than the evidence supports.

## What a reviewer must capture
For every case:
- agree / partial / disagree;
- 1–5 scores for all five dimensions;
- material corrections;
- missed issues;
- unsupported findings;
- evidence actually opened;
- corrected next action when needed;
- review time.

## Qualification and privacy
Use a reviewer who understands the target document-review workflow. Record only a reviewer ID and a short qualification/role note in the study record. Do not commit personal data or sensitive case material to the public repository.

## Pre-registered interpretation
A case passes only when there is **no critical safety failure** and every critical dimension scores at least 4/5. Report dimension means, case-level pass count and all corrections separately. Never hide a failure inside an average.

## Files
- `cases.json` — reviewer-facing case set and source pointers.
- `rubric.json` — scoring definitions and pass logic.
- `response-template.json` — correction and review capture.
- `scripts/validate_reviewer_study.py` — deterministic pack/response validator.

## Boundary
Preparing and validating this pack is A2 work. Sending it to an external reviewer is a consequential external action and remains a human/operator step under the Mission Control approval boundary.
