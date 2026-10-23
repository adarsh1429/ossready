from __future__ import annotations

import pytest
from conftest import COMPLETE_REPO, git, needs_git, write_files

from ossready import run_checks
from ossready.cli import main
from ossready.remote import RemoteError, checkout, is_remote, normalize_url


@pytest.mark.parametrize(
    "target",
    [
        "https://github.com/pallets/flask",
        "git@github.com:pallets/flask.git",
        "github.com/pallets/flask",
        "gitlab.com/group/project",
        "gh:pallets/flask",
        "file:///tmp/repo",
    ],
)
def test_is_remote(target):
    assert is_remote(target)


@pytest.mark.parametrize("target", [".", "src", "owner/repo", "./github.com/x/y/z", "ext::sh -c touch% /tmp/pwned"])
def test_is_not_remote(target):
    assert not is_remote(target)


def test_normalize_url():
    assert normalize_url("gh:pallets/flask") == "https://github.com/pallets/flask"
    assert normalize_url("github.com/pallets/flask/") == "https://github.com/pallets/flask"
    assert normalize_url("https://example.com/x.git") == "https://example.com/x.git"


@pytest.fixture
def upstream(tmp_path):
    """A local repository with a tagged commit, reachable through a file:// URL."""
    source = write_files(tmp_path / "upstream", COMPLETE_REPO)
    git(source, "init", "-q")
    git(source, "add", ".")
    git(source, "commit", "-qm", "initial")
    git(source, "tag", "v1.0.0")
    return source.as_uri()


@needs_git
def test_checkout_scans_a_remote_repository(upstream):
    with checkout(upstream) as repo:
        root = repo.root
        assert repo.display == upstream
        assert repo.tags == ["v1.0.0"]
        report = run_checks(repo)
    assert report.score == 100
    assert report.root == upstream
    assert not root.exists(), "temporary clone should be removed"


@needs_git
def test_cli_accepts_urls(upstream, capsys):
    assert main([upstream, "--format", "badge"]) == 0
    assert "100%2F100%20A-brightgreen" in capsys.readouterr().out


@needs_git
def test_missing_remote_is_a_clear_error(tmp_path):
    with pytest.raises(RemoteError, match="could not clone"):
        with checkout((tmp_path / "nothing-here").as_uri()):
            pass


@needs_git
def test_fix_refuses_remote_targets(capsys):
    assert main(["fix", "github.com/pallets/flask"]) == 2
    assert "local checkout" in capsys.readouterr().err
