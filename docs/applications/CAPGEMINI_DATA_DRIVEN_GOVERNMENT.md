# PrüfPilot — Public-sector document review work sample

**Thesis:** Do not pitch RAG. Show a caseworker how a document-heavy process becomes reviewable, evidence-grounded and easier to resolve while the final decision remains human.

[Demo (60 seconds)](https://mikelninh.github.io/pruefpilot/) · [Code](https://github.com/mikelninh/pruefpilot) · [API docs](https://pruefpilot-v5-api.vercel.app/api/docs)

## Synthetic example: GF-2026-014 / Glasfaser-Ausbau Sonnenhain

- 7 of 9 required documents visible; **Abnahmeprotokoll** and **GPS-Fotodokumentation** missing.
- €734,280 invoice pack versus €730,000 requested reimbursement: **€4,280 discrepancy**.
- R-007 has no documented service period.
- One document is marked as a prompt-injection quarantine case.
- Result: prepare a specific evidence request, **do not automatically approve the final payment**.

## 60-second walkthrough

| Time | What the hiring team sees | Value |
| --- | --- | --- |
| 0–10s | A grant review file, 9 expected supporting documents | Real administrative problem |
| 10–25s | Two missing proofs, unresolved R-007, €4,280 difference | Specific, reviewable findings |
| 25–40s | Source references, versioned rules, quarantined untrusted document | Evidence, uncertainty, safety |
| 40–55s | Draft reviewer memo: `NEEDS_INFORMATION`; human approval required | Hand-off not autonomous award |
| 55–60s | Suggested next evidence request + evaluation plan | Clear next action and adoption path |

## Endpoints behind the demonstration

```bash
# Verify API host before using this outside the repository.
curl -s https://pruefpilot-v5-api.vercel.app/api/v5/cases/glasfaser-sonnenhain
curl -s -X POST https://pruefpilot-v5-api.vercel.app/api/v5/cases/glasfaser-sonnenhain/evidence \
  -H 'content-type: application/json' \
  -d '{"claim":"Alle Unterlagen sind vollständig und die Zahlung kann freigegeben werden."}'
curl -s -X POST https://pruefpilot-v5-api.vercel.app/api/v5/cases/glasfaser-sonnenhain/memo
```

**Important distinction:** `/api/upload` is an implemented real-PDF intake/extraction path. The public V5 scenario is a **preconfigured synthetic case**; uploading a new PDF does not automatically rewrite that scripted scenario. Avoid suggesting it does.

## Quality evidence: what is real, what still needs measurement

| Metric | Operational definition | Status |
| --- | --- | --- |
| Missing-document detection recall | Flagged, labelled missing proofs / all labelled missing proofs | Needs independent labelled public-sector cases |
| Extraction precision | Correct fields / all fields extracted, human adjudicated | Real PDF engine exists; representative benchmark pending |
| Unsupported release rate | Automated consequential releases despite mandatory evidence gap | Human-boundary regression checks, not a field-accuracy guarantee |
| Evidence coverage | Material findings with independently verified exact source spans / total material findings | Citation and trace mechanism exists; independent semantic review pending |
| Reviewer correction rate | Corrections made / reviewed findings | Track in pilot |
| Median handling time | Assisted vs manual baseline on comparable cases | Track in pilot |

Contract checks in `tests/test_government_application_proof.py` exercise missing evidence, contradiction, reviewer gate and no automated release. **Four workflow regression checks must not be reported as an accuracy percentage.**

## Production/honesty boundary

Current strengths: FastAPI typed contracts, PDF bytes and SHA-256, classification, versioned rules, evidence states, consistency checks, reviewer hand-offs, tenant-scoped Postgres integration tests, fail-closed readiness. `ENGINEERING_PRODUCTION_READY` is an engineering status only.

Not externally validated: real administration adoption, a target DMS/Fachverfahren interface, public-law correctness, qualified reviewer evaluation, deployment-specific information security/DSGVO assessment, measured SLA and decision authority.

**Interview angle:** „Meine Frage war: Was brauchen Sachbearbeitende, um Verantwortung behalten und trotzdem Zeit gewinnen zu können? Die Lösung ist kein autonomer Bewilligungsagent, sondern ein nachvollziehbarer Prüf- und Nachforderungsprozess, dessen Qualität wir mit Fachpersonen messen.“
