# External Golden Path #1

## Goal

Prove one narrow real-world PrüfPilot workflow from original input to independently checkable human decision.

This is **not** a claim of general production accuracy. It is the first external proof that the architecture works on a real or lawfully anonymised/deidentified case rather than a synthetic fixture.

## Preferred first case

A document-completeness / reimbursement / funding-review case with:

- a real or lawfully anonymised PDF document pack;
- a real versioned requirement, guideline, notice, contract clause or other applicable authority;
- at least one reviewer who understands the workflow;
- a known expected outcome or a reviewer-created gold review after seeing the original documents.

If a funding/reimbursement case is unavailable, use another narrow document-review workflow with the same proof structure. Do not manufacture a "real" case.

## Data gate before upload

A run may start only when all are true:

- the tester is authorised to use the documents for this evaluation;
- secrets and unnecessary personal data have been removed where appropriate;
- the source is labelled truthfully as `real`, `anonymised_real`, `deidentified_real`, or `synthetic`;
- privileged, medical, employment or other sensitive documents are not used without the necessary permission/governance;
- the authority source and version are independently identifiable.

If any condition is unknown, stop and use synthetic data instead. Synthetic runs remain useful engineering tests but do not count as External Golden Path #1.

## Required workflow

```text
original PDF(s)
    ↓
real upload / persisted original
    ↓
SHA-256 + source identity
    ↓
extracted field / finding
    ↓
exact page locator
    ↓
versioned authority
    ↓
reviewable derivation
    ↓
human decision
    ↓
append-only decision history
    ↓
production gate revalidates source + authority + latest decision
```

The reviewer must be able to navigate backwards from every material finding:

`Finding → exact page → original PDF → authority/version → derivation → decision history`

## What we record

Use `proof/external-golden-path-1-run-template.json` for the run record. Keep sensitive document bytes outside the public repository.

For each material finding record:

- finding text;
- whether the reviewer agrees;
- original document ID/hash;
- exact page/field locator;
- authority ID/version/source;
- whether opening the source lands on the correct evidence;
- reviewer correction, if any;
- final decision and actor role.

Also record:

- baseline manual-review time, if measurable;
- PrüfPilot-assisted review time;
- number of source opens;
- unsupported findings;
- reviewer-detected missed issues;
- corrections before approval;
- whether any source or authority drift correctly closed the gate.

## Pass criteria for this first architectural proof

All of the following must hold:

1. **100% of material PrüfPilot findings have an exact source locator.**
2. **100% of rule-dependent findings have an independently openable, versioned authority.**
3. **0 material findings depend only on model prose/confidence.**
4. The reviewer can open the original evidence supporting every material finding.
5. Evidence or source tampering/drift causes the gate to close.
6. `pending` and `rejected` are not executable states.
7. Human approval identity is recorded and cannot be supplied as trusted truth by an untrusted client.
8. Later decisions do not overwrite earlier decisions.
9. Any observed false positive / false negative is recorded, not hidden.
10. No claim broader than the evidence from this run is published.

A single run can prove the **workflow and trust chain**. It cannot establish general accuracy, recall, legal correctness or production reliability. Those require a larger preregistered evaluation set and multiple independent reviewers.

## Deliberate failure test

After the normal reviewer flow, run one controlled negative test on a disposable copy or test environment:

- alter a stored source snapshot, **or**
- change the authority version, **or**
- append a later rejection.

Expected result: the production gate must fail closed.

Never alter the only copy of a real source document.

## Done means

External Golden Path #1 is complete only when we have:

- one admissible non-synthetic run;
- complete run manifest;
- source/authority verification by the reviewer;
- human decision history;
- a successful deliberate fail-closed test;
- a short `SUPPORTED / FAILED / UNKNOWN` conclusion.

### Allowed conclusion example

> On one anonymised real document-review case, PrüfPilot preserved the original source, produced page-linked evidence, bound the finding to a versioned authority, recorded reviewer decisions and failed closed after controlled source drift. This proves the end-to-end trust workflow for this case; it does not establish general accuracy.

That is the bar. No stronger claim until the evidence supports it.
