from __future__ import annotations

import pytest
from conftest import COMPLETE_REPO

from ossready import ConfigError, load_config
from ossready.checks import CHECK_IDS
from ossready.cli import main

tomllib = pytest.importorskip("tomllib" if __import__("sys").version_info >= (3, 11) else "tomli")


def test_no_config(make_repo):
    config = load_config(make_repo({}), CHECK_IDS)
    assert config.ignore == () and config.fail_under is None and config.weights == {} and config.source is None


def test_dedicated_file(make_repo):
    root = make_repo({".ossready.toml": 'ignore = ["funding"]\nfail-under = 80\n\n[weights]\ntests = 15\n'})
    config = load_config(root, CHECK_IDS)
    assert config.ignore == ("funding",)
    assert config.fail_under == 80
    assert config.weights == {"tests": 15}
    assert config.source == ".ossready.toml"


def test_pyproject_table(make_repo):
    root = make_repo({"pyproject.toml": '[project]\nname = "x"\n\n[tool.ossready]\nignore = ["codeowners"]\n'})
    config = load_config(root, CHECK_IDS)
    assert config.ignore == ("codeowners",)
    assert "pyproject.toml" in config.source


def test_dedicated_file_wins_over_pyproject(make_repo):
    root = make_repo({".ossready.toml": "fail-under = 50\n", "pyproject.toml": "[tool.ossready]\nfail-under = 90\n"})
    assert load_config(root, CHECK_IDS).fail_under == 50


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("colour = true\n", "unknown setting"),
        ('ignore = "funding"\n', "'ignore' must be a list"),
        ("fail-under = 120\n", "between 0 and 100"),
        ('fail-under = "high"\n', "whole number"),
        ("[weights]\ntests = -1\n", "'weights'"),
        ('ignore = ["nope"]\n', "unknown check id"),
        ("ignore = [\n", ".ossready.toml"),
    ],
)
def test_invalid_config(make_repo, content, message):
    with pytest.raises(ConfigError, match=message):
        load_config(make_repo({".ossready.toml": content}), CHECK_IDS)


def test_cli_uses_config(make_repo, capsys):
    files = {k: v for k, v in COMPLETE_REPO.items() if k != ".github/CODEOWNERS"}
    root = make_repo({**files, ".ossready.toml": 'ignore = ["codeowners"]\nfail-under = 100\n'})
    assert main([str(root), "--no-color"]) == 0
    assert "Code owners" not in capsys.readouterr().out


def test_cli_fail_under_from_config(make_repo, capsys):
    root = make_repo({".ossready.toml": "fail-under = 90\n"})
    assert main([str(root)]) == 1
    assert "below the minimum of 90" in capsys.readouterr().err


def test_cli_flag_overrides_config(make_repo):
    root = make_repo({".ossready.toml": "fail-under = 90\n"})
    assert main([str(root), "--fail-under", "0"]) == 0


def test_cli_no_config(make_repo, capsys):
    root = make_repo({".ossready.toml": "fail-under = 90\n"})
    assert main([str(root), "--no-config"]) == 0


def test_cli_reports_bad_config(make_repo, capsys):
    root = make_repo({".ossready.toml": "colour = true\n"})
    assert main([str(root)]) == 2
    assert "unknown setting" in capsys.readouterr().err
