from scripts.validate_reviewer_study import REQUIRED_CHALLENGES, REQUIRED_DIMENSIONS, load, validate_pack


def test_reviewer_study_pack_is_representative_and_valid():
    assert validate_pack() == []


def test_reviewer_study_preserves_human_correction_signal():
    cases = load(__import__("pathlib").Path("proof/reviewer-study/cases.json"))
    rubric = load(__import__("pathlib").Path("proof/reviewer-study/rubric.json"))
    response = load(__import__("pathlib").Path("proof/reviewer-study/response-template.json"))

    assert len(cases["cases"]) == 8
    assert REQUIRED_CHALLENGES <= {row["challenge_type"] for row in cases["cases"]}
    assert REQUIRED_DIMENSIONS == {row["id"] for row in rubric["dimensions"]}
    assert all("material_corrections" in row for row in response["case_reviews"])
    assert all("missed_issues" in row for row in response["case_reviews"])
    assert all("unsupported_findings" in row for row in response["case_reviews"])
