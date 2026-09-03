# Reviewer-quality study handoff

## Status
Builder stage complete; independent verification pending.

## Current step
Run the repository test/eval/harness suite plus `python scripts/validate_reviewer_study.py` on branch `mission-21-reviewer-study`.

## Evidence
- Mission Control approval: `mikelninh/council#21`.
- Target-repo runner trace: `mikelninh/pruefpilot#14`.
- Reviewer pack: `proof/reviewer-study/`.
- Deterministic pack validator: `scripts/validate_reviewer_study.py`.
- Regression coverage: `tests/test_reviewer_study.py`.

## Decisions
- Reuse the existing 12-case synthetic benchmark and retrieval fixtures instead of inventing a disconnected evidence set.
- Add the missing human-quality layer: correctness, evidence traceability, uncertainty, next-action usefulness and handoff quality.
- Preserve all corrections, missed issues and unsupported findings; do not average them away.
- Do not claim general accuracy from one reviewer study.

## Open risks
- No qualified reviewer judgement exists yet; that is the intended next evidence gate.
- Sending the pack externally is outside the approved A2 runner boundary and requires Michael/operator approval.
- Real-world performance remains unknown until a governed non-synthetic evaluation is completed.

## Next owner
Verifier. If CI is green, next owner becomes Michael/operator to choose a qualified reviewer and approve the external handoff.
