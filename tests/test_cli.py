from __future__ import annotations

import json

import pytest
from conftest import COMPLETE_REPO

from ossready import __version__
from ossready.checks import CHECK_IDS
from ossready.cli import main


def test_text_output(make_repo, capsys):
    assert main([str(make_repo(COMPLETE_REPO)), "--no-color"]) == 0
    out = capsys.readouterr().out
    assert "Score  100/100 (A)" in out
    assert "\033[" not in out


def test_check_is_the_default_command(make_repo, capsys):
    root = str(make_repo(COMPLETE_REPO))
    main(["check", root, "-f", "json"])
    explicit = json.loads(capsys.readouterr().out)
    main([root, "-f", "json"])
    assert json.loads(capsys.readouterr().out) == explicit


def test_force_color(make_repo, capsys, monkeypatch):
    monkeypatch.setenv("FORCE_COLOR", "1")
    monkeypatch.delenv("NO_COLOR", raising=False)
    main([str(make_repo(COMPLETE_REPO))])
    assert "\033[" in capsys.readouterr().out


def test_hints_and_fix_tip_are_printed(make_repo, capsys):
    main([str(make_repo({})), "--no-color"])
    out = capsys.readouterr().out
    assert "Add a LICENSE file" in out
    assert "Tip: 'ossready fix' can create the missing files" in out


def test_json_output(make_repo, capsys):
    assert main([str(make_repo(COMPLETE_REPO)), "--format", "json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["version"] == __version__
    assert data["score"] == 100
    assert data["summary"] == {"pass": len(CHECK_IDS), "warn": 0, "fail": 0, "skip": 0}
    assert [c["id"] for c in data["checks"]] == list(CHECK_IDS)


def test_markdown_output(make_repo, capsys):
    assert main([str(make_repo({"README.md": "# x\n"})), "-f", "markdown"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("## ossready report")
    assert "img.shields.io/badge/ossready-" in out
    assert "| ⚠️ | README |" in out
    assert "| ➖ | License metadata |" in out
    assert "### How to improve" in out
    assert "**License** (+12 pts)" in out


def test_badge_output(make_repo, capsys):
    assert main([str(make_repo(COMPLETE_REPO)), "-f", "badge"]) == 0
    assert capsys.readouterr().out == (
        "![ossready 100/100](https://img.shields.io/badge/ossready-100%2F100%20A-brightgreen)\n"
    )


def test_fail_under(make_repo, capsys):
    root = str(make_repo({}))
    assert main([root, "--fail-under", "50"]) == 1
    assert "below the minimum of 50" in capsys.readouterr().err
    assert main([root, "--fail-under", "10"]) == 0


def test_fail_under_out_of_range(make_repo, capsys):
    assert main([str(make_repo({})), "--fail-under", "150"]) == 2


def test_ignore(make_repo, capsys):
    root = str(make_repo({k: v for k, v in COMPLETE_REPO.items() if k != ".github/CODEOWNERS"}))
    assert main([root, "--ignore", "codeowners, changelog", "--fail-under", "100", "-f", "json"]) == 0
    ids = [c["id"] for c in json.loads(capsys.readouterr().out)["checks"]]
    assert "codeowners" not in ids and "changelog" not in ids


def test_unknown_ignore_id(make_repo, capsys):
    assert main([str(make_repo({})), "--ignore", "bogus"]) == 2
    assert "bogus" in capsys.readouterr().err


def test_missing_directory(tmp_path, capsys):
    assert main([str(tmp_path / "nope")]) == 2
    assert "not a directory" in capsys.readouterr().err


@pytest.mark.parametrize("argv", [["list"], ["--list-checks"]])
def test_list_checks(capsys, argv):
    assert main(argv) == 0
    out = capsys.readouterr().out
    for check_id in CHECK_IDS:
        assert check_id in out


def test_explain(capsys):
    assert main(["explain", "license"]) == 0
    out = capsys.readouterr().out
    assert "Why it matters" in out and "all-rights-reserved" in out
    assert "ossready fix --only license" in out


def test_explain_unknown_check(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["explain", "nope"])
    assert exc.value.code == 2


def test_version(capsys):
    with pytest.raises(SystemExit):
        main(["--version"])
    assert __version__ in capsys.readouterr().out


# ------------------------------------------------------------------ fix


def test_fix_dry_run(make_repo, capsys):
    root = make_repo({})
    assert main(["fix", str(root), "--dry-run", "--no-color"]) == 0
    out = capsys.readouterr().out
    assert "Would create" in out and "+ LICENSE" in out
    assert "Dry run: nothing was written" in out
    assert list(root.iterdir()) == []


def test_fix_writes_and_reports_new_score(make_repo, capsys):
    root = make_repo({"pyproject.toml": '[project]\nname = "tiny"\n'})
    assert main(["fix", str(root), "--no-color", "--owner", "acme", "--author", "Acme Inc."]) == 0
    out = capsys.readouterr().out
    assert "Created" in out and "+ .github/workflows/ci.yml" in out
    assert "MIT, Copyright (c) " in out and "Acme Inc." in out
    assert "Still to do by hand" in out and "Tests:" in out
    assert "Score  " in out and " → " in out
    assert (root / "LICENSE").is_file()


def test_fix_when_nothing_is_missing(make_repo, capsys):
    assert main(["fix", str(make_repo(COMPLETE_REPO)), "--no-color"]) == 0
    assert "Nothing to create" in capsys.readouterr().out


def test_fix_bad_license(make_repo, capsys):
    assert main(["fix", str(make_repo({})), "--license", "WTFPL"]) == 2
    assert "unknown license" in capsys.readouterr().err


def test_fix_missing_directory(tmp_path, capsys):
    assert main(["fix", str(tmp_path / "nope")]) == 2
