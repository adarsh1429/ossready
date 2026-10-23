from __future__ import annotations

import pytest
from conftest import GOOD_README, git, needs_git, write_files

from ossready import FixOptions, Status, apply_plan, plan_fixes, run_checks
from ossready.fix import FIXABLE

try:  # generated YAML is parsed when PyYAML is available
    import yaml as _yaml
except ImportError:  # pragma: no cover
    _yaml = None

ECOSYSTEM_REPOS = {
    "python": {"pyproject.toml": '[project]\nname = "tiny"\nversion = "0.1.0"\nrequires-python = ">=3.12"\n'},
    "node": {"package.json": '{"name": "tiny", "version": "1.0.0", "scripts": {"test": "node --test"}}'},
    "pnpm": {"package.json": '{"name": "tiny", "scripts": {"test": "vitest"}}', "pnpm-lock.yaml": ""},
    "rust": {"Cargo.toml": '[package]\nname = "tiny"\nversion = "0.1.0"\n'},
    "go": {"go.mod": "module github.com/acme/tiny\n"},
    "maven": {"pom.xml": "<project></project>"},
    "gradle": {"build.gradle.kts": "plugins {}\n", "gradlew": "#!/bin/sh\n"},
    "ruby": {"Gemfile": "source 'https://rubygems.org'\n", "spec/a_spec.rb": ""},
    "php": {"composer.json": '{"name": "acme/tiny", "scripts": {"test": "phpunit"}}'},
    "dotnet": {"Tiny.csproj": "<Project></Project>"},
    "dart": {"pubspec.yaml": "name: tiny\n"},
    "deno": {"deno.json": "{}"},
}


def fix(root, **options):
    plan = plan_fixes(root, FixOptions(**options))
    apply_plan(plan, root)
    return plan


def test_fix_on_an_empty_folder(make_repo):
    root = make_repo({})
    before = run_checks(root)
    plan = fix(root, owner="acme", email="maintainers@example.com")
    after = run_checks(root)
    assert after.score > before.score
    fixed = {f.check_id for f in plan.files}
    # Everything fixable that was failing now passes, except CI and Dependabot, which need a language.
    assert fixed == FIXABLE - {"ci", "dependency-updates"}
    for check_id in fixed:
        assert after.get(check_id).status is Status.PASS, (check_id, after.get(check_id).message)


@pytest.mark.parametrize("ecosystem", sorted(ECOSYSTEM_REPOS))
def test_fix_produces_passing_files_for_each_ecosystem(make_repo, ecosystem):
    root = make_repo(ECOSYSTEM_REPOS[ecosystem])
    plan = fix(root, owner="acme")
    after = run_checks(root)
    for check_id in {f.check_id for f in plan.files}:
        assert after.get(check_id).status in (Status.PASS, Status.WARN), (check_id, after.get(check_id).message)
    assert after.get("workflow-security").status is Status.PASS
    for new in plan.files:
        if new.path.endswith(".yml") and _yaml is not None:
            assert _yaml.safe_load((root / new.path).read_text()) is not None, new.path


def test_python_ci_matrix_respects_requires_python(make_repo):
    root = make_repo(ECOSYSTEM_REPOS["python"])
    fix(root)
    workflow = (root / ".github/workflows/ci.yml").read_text()
    assert '"3.12"' in workflow and '"3.11"' not in workflow


def test_dry_run_writes_nothing(make_repo):
    root = make_repo({"README.md": GOOD_README})
    plan = plan_fixes(root)
    assert plan.files
    assert sorted(p.name for p in root.iterdir()) == ["README.md"]


def test_existing_files_are_never_touched(make_repo):
    root = make_repo({"LICENSE": "my own words\n", "CONTRIBUTING.md": "custom\n"})
    plan = fix(root)
    assert "LICENSE" not in [f.path for f in plan.files]
    assert (root / "LICENSE").read_text() == "my own words\n"
    assert (root / "CONTRIBUTING.md").read_text() == "custom\n"


def test_apply_skips_files_created_in_the_meantime(make_repo):
    root = make_repo({})
    plan = plan_fixes(root)
    (root / "CHANGELOG.md").write_text("mine\n")
    written = apply_plan(plan, root)
    assert "CHANGELOG.md" not in [f.path for f in written]
    assert (root / "CHANGELOG.md").read_text() == "mine\n"


def test_only(make_repo):
    root = make_repo({})
    plan = fix(root, only=("license", "changelog"))
    assert sorted(f.path for f in plan.files) == ["CHANGELOG.md", "LICENSE"]


def test_only_rejects_unknown_ids(make_repo):
    with pytest.raises(ValueError, match="nope"):
        plan_fixes(make_repo({}), FixOptions(only=("nope",)))


def test_unknown_license_is_rejected(make_repo):
    with pytest.raises(ValueError, match="unknown license"):
        plan_fixes(make_repo({}), FixOptions(license="WTFPL"))


@pytest.mark.parametrize(("name", "spdx"), [("apache-2.0", "Apache-2.0"), ("GPLv3", "GPL-3.0"), ("mit", "MIT")])
def test_license_choice(make_repo, name, spdx):
    root = make_repo({})
    fix(root, license=name, author="Ada Lovelace", only=("license",))
    assert run_checks(root).get("license").message == f"{spdx} (LICENSE)"


def test_license_defaults_to_what_the_manifest_declares(make_repo):
    root = make_repo({"package.json": '{"name": "x", "license": "ISC"}'})
    fix(root, only=("license",))
    assert run_checks(root).get("license-consistency").status is Status.PASS


def test_dual_license_from_manifest(make_repo):
    root = make_repo({"Cargo.toml": '[package]\nname = "x"\nlicense = "MIT OR Apache-2.0"\n'})
    plan = fix(root, only=("license", "readme"))
    assert {f.path for f in plan.files} == {"LICENSE-MIT", "LICENSE-APACHE", "README.md"}
    readme = (root / "README.md").read_text()
    assert "[MIT](LICENSE-MIT) or [Apache-2.0](LICENSE-APACHE)" in readme
    assert run_checks(root).get("readme-links").status is Status.PASS


def test_license_conflicting_with_manifest_is_flagged(make_repo):
    root = make_repo({"package.json": '{"name": "x", "license": "ISC"}'})
    plan = plan_fixes(root, FixOptions(license="MIT", only=("license",)))
    assert "declares ISC" in plan.files[0].review


def test_codeowners_needs_an_owner(make_repo):
    plan = plan_fixes(make_repo({}), FixOptions(only=("codeowners",)))
    assert not plan.files
    assert "--owner" in plan.manual[0].reason


def test_readme_only_links_to_files_that_will_exist(make_repo):
    root = make_repo({})
    fix(root, only=("readme",))
    text = (root / "README.md").read_text()
    assert "CONTRIBUTING.md" not in text and "(LICENSE)" not in text
    assert run_checks(root).get("readme-links").status is Status.PASS


def test_metadata_from_manifest_is_used(make_repo):
    root = make_repo({"pyproject.toml": '[project]\nname = "fancy-lib"\ndescription = "Makes things fancy."\n'})
    fix(root)
    readme = (root / "README.md").read_text()
    assert readme.startswith("# fancy-lib\n")
    assert "Makes things fancy." in readme
    assert "pip install fancy-lib" in readme
    assert "import fancy_lib" in readme


@needs_git
def test_github_remote_and_identity_are_detected(make_repo):
    root = make_repo({"pyproject.toml": '[project]\nname = "tiny"\n'})
    git(root, "init", "-q")
    git(root, "remote", "add", "origin", "git@github.com:acme/tiny.git")
    git(root, "config", "user.name", "Ada Lovelace")
    git(root, "config", "user.email", "ada@example.com")
    fix(root)
    assert (root / ".github/CODEOWNERS").read_text().strip().endswith("* @acme")
    assert "Copyright (c) " in (root / "LICENSE").read_text() and "Ada Lovelace" in (root / "LICENSE").read_text()
    security = (root / "SECURITY.md").read_text()
    assert "https://github.com/acme/tiny/security/advisories/new" in security and "ada@example.com" in security
    assert "https://github.com/acme/tiny/actions/workflows/ci.yml/badge.svg" in (root / "README.md").read_text()
    assert "branches: [main]" in (root / ".github/workflows/ci.yml").read_text()


def test_dependabot_covers_detected_ecosystems(make_repo):
    root = make_repo({"package.json": "{}", "go.mod": "module x\n", "Dockerfile": "FROM scratch\n"})
    fix(root, only=("ci", "dependency-updates"))
    config = (root / ".github/dependabot.yml").read_text()
    for ecosystem in ("npm", "gomod", "docker", "github-actions"):
        assert f"package-ecosystem: {ecosystem}" in config


def test_generated_files_use_lf_newlines(make_repo):
    root = make_repo({})
    fix(root, only=("license",))
    assert b"\r\n" not in (root / "LICENSE").read_bytes()


def test_fix_reaches_a_high_score_on_a_tested_python_project(make_repo, tmp_path):
    files = {**ECOSYSTEM_REPOS["python"], "tests/test_x.py": "def test(): pass\n", ".github/FUNDING.yml": "github: x\n"}
    root = write_files(make_repo({}), files)
    fix(root, owner="acme", email="a@example.com", author="Acme")
    report = run_checks(root)
    remaining = {r.id for r in report.results if r.status not in (Status.PASS, Status.SKIP)}
    assert remaining <= {"releases", "license-consistency"}
    assert report.score >= 95
