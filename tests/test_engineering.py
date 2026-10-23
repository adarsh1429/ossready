from __future__ import annotations

import pytest
from conftest import CI_WORKFLOW, git, needs_git, result, status

from ossready import Status

# ------------------------------------------------------------------ CI


@pytest.mark.parametrize(
    "path",
    [".github/workflows/test.yaml", ".gitlab-ci.yml", ".circleci/config.yml", "Jenkinsfile", ".travis.yml"],
)
def test_ci_detected(make_repo, path):
    assert status(make_repo({path: "script: npm test\n"}), "ci") is Status.PASS


def test_ci_missing(make_repo):
    assert status(make_repo({".github/dependabot.yml": "x\n"}), "ci") is Status.FAIL


def test_ci_that_runs_no_tests_warns(make_repo):
    workflow = "on: push\njobs:\n  lint:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hello\n"
    r = result(make_repo({".github/workflows/lint.yml": workflow}), "ci")
    assert r.status is Status.WARN
    assert "no test command" in r.message


@pytest.mark.parametrize(
    "step",
    [
        "      - run: ${{ env.CARGO }} test --workspace\n",
        "      - name: Run tests\n        run: ./scripts/check.sh\n",
        "      - run: make ci\n",
    ],
)
def test_ci_test_detection_heuristics(make_repo, step):
    workflow = "on: push\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n" + step
    assert status(make_repo({".github/workflows/ci.yml": workflow}), "ci") is Status.PASS


def test_ci_calling_a_reusable_workflow_passes(make_repo):
    workflow = "on: push\njobs:\n  call:\n    uses: org/shared/.github/workflows/test.yml@v1\n"
    assert status(make_repo({".github/workflows/ci.yml": workflow}), "ci") is Status.PASS


# ------------------------------------------------------------------ tests


@pytest.mark.parametrize(
    "path",
    [
        "tests/helpers.py",
        "pkg/test_core.py",
        "pkg/core_test.go",
        "src/app.test.tsx",
        "src/app.spec.js",
        "spec/model_spec.rb",
        "src/main/java/FooTest.java",
    ],
)
def test_tests_detected(make_repo, path):
    assert status(make_repo({path: "x\n"}), "tests") is Status.PASS


def test_inline_rust_tests(make_repo):
    code = "fn add(a: i32, b: i32) -> i32 { a + b }\n#[cfg(test)]\nmod tests {}\n"
    assert status(make_repo({"src/lib.rs": code}), "tests") is Status.PASS


def test_no_tests(make_repo):
    assert status(make_repo({"src/contest.py": "x\n", "latest.js": "x\n"}), "tests") is Status.FAIL


# ------------------------------------------------------------------ manifest


def test_manifests(make_repo):
    r = result(make_repo({"package.json": "{}", "Cargo.toml": "", "demo.gemspec": ""}), "manifest")
    assert r.status is Status.PASS
    assert "Node.js" in r.message and "Rust" in r.message and "Ruby" in r.message


def test_nested_manifest_does_not_count(make_repo):
    assert status(make_repo({"examples/package.json": "{}"}), "manifest") is Status.FAIL


# ------------------------------------------------------------------ code style


@pytest.mark.parametrize(
    ("files", "expected"),
    [
        ({".editorconfig": "root = true"}, "EditorConfig"),
        ({".pre-commit-config.yaml": "repos: []"}, "pre-commit"),
        ({"pyproject.toml": "[tool.ruff]\nline-length = 100\n"}, "Ruff (pyproject.toml)"),
        ({"package.json": '{"prettier": {}}'}, "prettier (package.json)"),
        ({"eslint.config.mjs": "export default []"}, "ESLint"),
        ({"go.mod": "module x"}, "gofmt"),
    ],
)
def test_code_style_detected(make_repo, files, expected):
    r = result(make_repo(files), "code-style")
    assert r.status is Status.PASS
    assert expected in r.message


def test_code_style_missing(make_repo):
    assert status(make_repo({"package.json": "{}"}), "code-style") is Status.FAIL


# ------------------------------------------------------------------ releases


@needs_git
def test_releases_from_git_tags(make_repo):
    root = make_repo({"README.md": "x"})
    git(root, "init", "-q")
    git(root, "add", ".")
    git(root, "commit", "-qm", "init")
    for tag in ("v1.2.0", "v1.10.0", "nightly", "pkg@0.3.1"):
        git(root, "tag", tag)
    r = result(root, "releases")
    assert r.status is Status.PASS
    assert "3 version tags (latest 1.10.0)" in r.message


@needs_git
def test_changelog_without_tags_warns_in_a_git_repo(make_repo):
    root = make_repo({"CHANGELOG.md": "## [1.0.0] - 2026-01-01\n"})
    git(root, "init", "-q")
    r = result(root, "releases")
    assert r.status is Status.WARN
    assert "no git tags" in r.message


@needs_git
def test_shallow_clone_without_tags_falls_back_to_the_changelog(make_repo, tmp_path):
    source = make_repo({"CHANGELOG.md": "## [1.0.0]\n"})
    git(source, "init", "-q")
    git(source, "add", ".")
    git(source, "commit", "-qm", "one")
    git(source, "commit", "-qm", "two", "--allow-empty")
    clone = tmp_path / "clone"
    git(tmp_path, "clone", "-q", "--depth", "1", "--no-tags", source.as_uri(), str(clone))
    assert status(clone, "releases") is Status.PASS


def test_version_headings_with_a_prefix(make_repo):
    text = "Changes\n=======\n\nVersion 3.1.0\n-------------\n\nReleased 2026-01-01\n\n## Version 2.0\n"
    r = result(make_repo({"CHANGES.rst": text}), "releases")
    assert r.status is Status.PASS
    assert "2 releases (latest 3.1.0)" in r.message


def test_changelog_counts_when_tags_are_unknown(make_repo):
    # Outside git (e.g. a downloaded archive) the changelog is the best evidence available.
    assert status(make_repo({"CHANGELOG.md": "## 1.0.0\n"}), "releases") is Status.PASS


@pytest.mark.parametrize(
    ("path", "content"),
    [("package.json", '{"version": "2.0.0"}'), ("pyproject.toml", '[project]\nversion = "0.4.0"\n')],
)
def test_manifest_version_without_releases_warns(make_repo, path, content):
    assert status(make_repo({path: content}), "releases") is Status.WARN


def test_no_releases(make_repo):
    assert status(make_repo({"README.md": "x"}), "releases") is Status.FAIL


# ------------------------------------------------------------------ hygiene


def test_gitignore(make_repo):
    assert status(make_repo({".gitignore": "x"}), "gitignore") is Status.PASS


def test_gitignore_missing(make_repo):
    assert status(make_repo({}), "gitignore") is Status.FAIL


def test_renovate_detected(make_repo):
    assert status(make_repo({"renovate.json": "{}"}), "dependency-updates") is Status.PASS


def _sparse(path, size):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as handle:
        handle.truncate(size)


def test_large_file_warns(make_repo):
    root = make_repo({"README.md": "x"})
    _sparse(root / "data" / "model.bin", 12 * 1024 * 1024)
    _sparse(root / "data" / "small.bin", 6 * 1024 * 1024)
    r = result(root, "large-files")
    assert r.status is Status.WARN
    assert "data/model.bin (12 MB)" in r.message and "small.bin" not in r.message


def test_huge_file_fails(make_repo):
    root = make_repo({"README.md": "x"})
    _sparse(root / "dump.sql", 60 * 1024 * 1024)
    assert status(root, "large-files") is Status.FAIL


def test_files_in_git_lfs_are_fine(make_repo):
    root = make_repo({".gitattributes": "*.bin filter=lfs diff=lfs merge=lfs -text\n"})
    _sparse(root / "weights" / "model.bin", 60 * 1024 * 1024)
    r = result(root, "large-files")
    assert r.status is Status.PASS
    assert "outside Git LFS" in r.message


def test_ci_workflow_fixture_is_clean(make_repo):
    assert status(make_repo({".github/workflows/ci.yml": CI_WORKFLOW}), "workflow-security") is Status.PASS
