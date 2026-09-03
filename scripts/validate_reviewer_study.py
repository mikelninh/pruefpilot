from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "proof" / "reviewer-study"
REQUIRED_DIMENSIONS = {"correctness", "evidence", "uncertainty", "next_action", "handoff"}
REQUIRED_CHALLENGES = {"ordinary", "incomplete", "ambiguous", "rule_dependent", "multi_document", "adversarial"}
REQUIRED_CAPTURE = {
    "agree_partial_disagree",
    "material_corrections",
    "missed_issues",
    "unsupported_findings",
    "evidence_opened",
    "next_action_correction",
    "review_time_seconds",
}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _fixture_ids(path: Path) -> set[str]:
    rows = load(path)
    values: set[str] = set()
    for row in rows:
        if row.get("id"):
            values.add(str(row["id"]))
        if row.get("question"):
            values.add(str(row["question"]))
    return values


def validate_pack() -> list[str]:
    errors: list[str] = []
    cases = load(PACK / "cases.json")
    rubric = load(PACK / "rubric.json")
    response = load(PACK / "response-template.json")

    rows = cases.get("cases") or []
    ids = [row.get("case_id") for row in rows]
    if cases.get("data_class") != "synthetic":
        errors.append("study data_class must remain synthetic")
    if len(rows) < 8 or len(ids) != len(set(ids)):
        errors.append("study needs at least 8 uniquely identified cases")

    challenge_types = {row.get("challenge_type") for row in rows}
    if not REQUIRED_CHALLENGES.issubset(challenge_types):
        errors.append("case set does not cover all required challenge types")

    fixture_cache: dict[Path, set[str]] = {}
    for row in rows:
        for ref in row.get("fixture_refs") or []:
            file_name, _, anchor = ref.partition("#")
            path = ROOT / file_name
            if not path.exists():
                errors.append(f"missing fixture file: {file_name}")
                continue
            if anchor:
                values = fixture_cache.setdefault(path, _fixture_ids(path))
                if anchor not in values:
                    errors.append(f"fixture anchor not found: {ref}")

    dimension_ids = {item.get("id") for item in rubric.get("dimensions") or []}
    if dimension_ids != REQUIRED_DIMENSIONS:
        errors.append("rubric dimensions changed or incomplete")

    captured = set(rubric.get("required_capture") or [])
    if not REQUIRED_CAPTURE.issubset(captured):
        errors.append("rubric no longer requires full correction capture")

    response_rows = response.get("case_reviews") or []
    if [row.get("case_id") for row in response_rows] != ids:
        errors.append("response template case ids must exactly match study case order")
    for row in response_rows:
        if not REQUIRED_CAPTURE.issubset(row):
            errors.append(f"response template missing correction fields for {row.get('case_id')}")
        if set((row.get("scores") or {}).keys()) != REQUIRED_DIMENSIONS:
            errors.append(f"response scores incomplete for {row.get('case_id')}")

    readme = (PACK / "README.md").read_text(encoding="utf-8")
    if "does not establish general accuracy" not in readme:
        errors.append("README must preserve the narrow-claim boundary")
    return errors


def validate_response(path: Path) -> list[str]:
    errors = validate_pack()
    template = load(PACK / "response-template.json")
    response = load(path)
    if response.get("study_id") != template.get("study_id"):
        errors.append("response study_id does not match the pack")
    allowed = {"agree", "partial", "disagree"}
    for row in response.get("case_reviews") or []:
        verdict = row.get("agree_partial_disagree")
        if verdict not in allowed:
            errors.append(f"invalid review verdict for {row.get('case_id')}: {verdict!r}")
        for key, value in (row.get("scores") or {}).items():
            if not isinstance(value, int) or value not in range(1, 6):
                errors.append(f"invalid {key} score for {row.get('case_id')}: {value!r}")
        if not isinstance(row.get("critical_safety_failure"), bool):
            errors.append(f"critical_safety_failure must be boolean for {row.get('case_id')}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--response", type=Path)
    args = parser.parse_args()
    errors = validate_response(args.response) if args.response else validate_pack()
    if errors:
        for error in errors:
            print(f"REVIEWER STUDY FAIL: {error}")
        return 1
    print("REVIEWER STUDY PASS: pack structure, fixture coverage and correction capture are valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
