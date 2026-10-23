from __future__ import annotations

import pytest
from conftest import COMPLETE_REPO, GOOD_README, result

from ossready import Status, run_checks
from ossready.checks import CHECKS
from ossready.model import grade_for


def without(files: dict, *paths: str) -> dict:
    return {k: v for k, v in files.items() if k not in paths}


def test_weights_add_up_to_100():
    assert sum(c.weight for c in CHECKS) == 100


def test_check_ids_are_unique_and_kebab_case():
    ids = [c.id for c in CHECKS]
    assert len(ids) == len(set(ids))
    assert all(i == i.lower() and " " not in i and "_" not in i for i in ids)


def test_every_check_explains_itself():
    for check in CHECKS:
        assert check.hint.strip() and check.rationale.strip(), check.id


def test_complete_repo_scores_100(make_repo):
    report = run_checks(make_repo(COMPLETE_REPO))
    problems = [(r.id, r.message) for r in report.results if r.status is not Status.PASS]
    assert problems == []
    assert report.score == 100
    assert report.grade == "A"


def test_empty_repo(make_repo):
    report = run_checks(make_repo({}))
    passed = {r.id for r in report.results if r.status is Status.PASS}
    skipped = {r.id for r in report.results if r.status is Status.SKIP}
    assert passed == {"secrets", "large-files"}
    assert skipped == {"readme-links", "license-consistency", "workflow-security"}
    # 10 points earned out of the 91 that apply.
    assert report.score == round(100 * 10 / 91)
    assert report.grade == "F"


def test_skipped_checks_are_left_out_of_the_score(make_repo):
    files = without(COMPLETE_REPO, ".github/workflows/ci.yml")
    report = run_checks(make_repo(files))
    assert report.get("workflow-security").status is Status.SKIP
    assert report.get("ci").status is Status.FAIL
    assert report.score == round(100 * (100 - 3 - 9) / (100 - 3))


def test_warning_earns_half_the_weight(make_repo):
    root = make_repo({**COMPLETE_REPO, "README.md": "# demo\n"})  # too short -> warn
    assert result(root, "readme").status is Status.WARN
    assert run_checks(root).score == round(100 - 9 / 2)


def test_ignored_checks_do_not_count(make_repo):
    root = make_repo(without(COMPLETE_REPO, ".github/CODEOWNERS"))
    assert run_checks(root).score == 98
    report = run_checks(root, ignore=["codeowners"])
    assert report.get("codeowners") is None
    assert report.score == 100


def test_custom_weights(make_repo):
    root = make_repo(without(COMPLETE_REPO, ".github/CODEOWNERS"))
    report = run_checks(root, weights={"codeowners": 0})
    assert report.get("codeowners").weight == 0
    assert report.score == 100


def test_unknown_ids_raise(make_repo):
    with pytest.raises(ValueError, match="nope"):
        run_checks(make_repo({}), ignore=["nope"])
    with pytest.raises(ValueError, match="bogus"):
        run_checks(make_repo({}), weights={"bogus": 3})


def test_hints_only_on_problems(make_repo):
    report = run_checks(make_repo({"README.md": GOOD_README}))
    for r in report.results:
        assert bool(r.hint) == (r.status in (Status.WARN, Status.FAIL))


def test_not_a_directory(tmp_path):
    with pytest.raises(NotADirectoryError):
        run_checks(tmp_path / "missing")


@pytest.mark.parametrize(
    ("score", "grade"), [(100, "A"), (90, "A"), (89, "B"), (75, "B"), (60, "C"), (40, "D"), (0, "F")]
)
def test_grades(score, grade):
    assert grade_for(score) == grade
