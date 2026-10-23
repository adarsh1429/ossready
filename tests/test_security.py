from __future__ import annotations

import pytest
from conftest import GOOD_README, git, needs_git, result, status

from ossready import Status
from ossready.checks.security import injection_lines

# Fake credentials are assembled at runtime so this file never contains one verbatim
# (otherwise ossready's own secret scan would flag it).
FAKE_AWS_KEY = "AKIA" + "Q" * 16
FAKE_GITHUB_TOKEN = "ghp" + "_" + "a1B2" * 9
PRIVATE_KEY_HEADER = "-----BEGIN " + "RSA PRIVATE KEY-----"
PRIVATE_KEY = PRIVATE_KEY_HEADER + "\n" + "MIIEpAIBAAKCAQEA" + "q7Zx" * 12 + "\n"

# ------------------------------------------------------------------ secrets


def test_aws_key_fails_with_location(make_repo):
    r = result(make_repo({"config/settings.py": f"DEBUG = True\nKEY = '{FAKE_AWS_KEY}'\n"}), "secrets")
    assert r.status is Status.FAIL
    assert "config/settings.py:2 (AWS access key)" in r.message
    assert FAKE_AWS_KEY not in r.message


def test_github_token_and_private_key(make_repo):
    files = {"a.txt": FAKE_GITHUB_TOKEN, "deploy/key.pem": PRIVATE_KEY}
    r = result(make_repo(files), "secrets")
    assert r.status is Status.FAIL
    assert "GitHub token" in r.message and "private key" in r.message


def test_documented_example_keys_are_ignored(make_repo):
    example = "AKIA" + "IOSFODNN7" + "EXAMPLE"
    assert status(make_repo({"docs/aws.md": f"Use `{example}`\n"}), "secrets") is Status.PASS


def test_credential_files_warn(make_repo):
    r = result(make_repo({".env": "DEBUG=1\n", "certs/store.p12": b"\x00\x01"}), "secrets")
    assert r.status is Status.WARN
    assert ".env" in r.message and "certs/store.p12" in r.message


def test_keys_in_test_fixtures_only_warn(make_repo):
    r = result(make_repo({"tests/certs/server.key": PRIVATE_KEY}), "secrets")
    assert r.status is Status.WARN
    assert "tests/certs/server.key:1 (private key)" in r.message


def test_real_leak_beats_fixture_warning(make_repo):
    files = {"tests/certs/server.key": PRIVATE_KEY, "app/config.py": f"KEY = '{FAKE_AWS_KEY}'"}
    r = result(make_repo(files), "secrets")
    assert r.status is Status.FAIL
    assert "app/config.py:1" in r.message and "tests/" not in r.message


def test_key_header_without_key_material_is_ignored(make_repo):
    text = f'PRIVATE_KEY="{PRIVATE_KEY_HEADER}\\n...\\n-----END RSA PRIVATE KEY-----"\n'
    assert status(make_repo({"app/settings.py": text}), "secrets") is Status.PASS


def test_keys_in_docs_only_warn(make_repo):
    r = result(make_repo({"guide/env.mdx": f"Example:\n\n{PRIVATE_KEY}"}), "secrets")
    assert r.status is Status.WARN
    assert "tests or docs" in r.message


def test_env_file_in_test_app_is_fine(make_repo):
    assert status(make_repo({"tests/test_apps/.env": "FOO=bar\n"}), "secrets") is Status.PASS


@pytest.mark.parametrize("name", [".env.example", ".env.sample", ".env.template"])
def test_env_templates_are_fine(make_repo, name):
    assert status(make_repo({name: "API_KEY=\n"}), "secrets") is Status.PASS


def test_binary_files_are_not_scanned(make_repo):
    data = b"\x00\x00" + FAKE_AWS_KEY.encode()
    assert status(make_repo({"blob.dat": data}), "secrets") is Status.PASS


@needs_git
def test_gitignored_files_are_skipped(make_repo):
    root = make_repo({".gitignore": ".env\nbuild/\n", ".env": f"KEY={FAKE_AWS_KEY}\n", "build/README.md": GOOD_README})
    git(root, "init", "-q")
    assert status(root, "secrets") is Status.PASS
    assert status(root, "readme") is Status.FAIL


@needs_git
def test_untracked_but_not_ignored_files_are_checked(make_repo):
    root = make_repo({"README.md": GOOD_README})
    git(root, "init", "-q")
    assert status(root, "readme") is Status.PASS


def test_symlinks_out_of_the_repository_are_ignored(make_repo, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text(f"KEY={FAKE_AWS_KEY}\n")
    root = make_repo({"README.md": GOOD_README})
    try:
        (root / "leak.txt").symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported here")
    assert status(root, "secrets") is Status.PASS


# ------------------------------------------------------------------ workflow security

SAFE = """\
on: issues
permissions:
  issues: write
jobs:
  greet:
    runs-on: ubuntu-latest
    steps:
      - env:
          TITLE: ${{ github.event.issue.title }}
        run: echo "$TITLE"
"""

INJECTABLE_BLOCK = """\
on: issues
permissions: {}
jobs:
  greet:
    runs-on: ubuntu-latest
    steps:
      - name: Greet
        run: |
          echo "Thanks for opening"
          echo "${{ github.event.issue.title }}"
      - run: echo done
"""

INJECTABLE_INLINE = """\
on: pull_request
permissions: read-all
jobs:
  x:
    runs-on: ubuntu-latest
    steps:
      - run: git checkout ${{ github.head_ref }}
"""

PWN_REQUEST = """\
on: pull_request_target
permissions:
  contents: write
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event.pull_request.head.sha }}
      - run: make
"""

NO_PERMISSIONS = "on: push\njobs:\n  t:\n    runs-on: ubuntu-latest\n    steps:\n      - run: make test\n"


def test_injection_lines():
    assert injection_lines(INJECTABLE_BLOCK) == [10]
    assert injection_lines(INJECTABLE_INLINE) == [7]
    assert injection_lines(SAFE) == []


def test_safe_workflow_passes(make_repo):
    assert status(make_repo({".github/workflows/greet.yml": SAFE}), "workflow-security") is Status.PASS


@pytest.mark.parametrize(
    ("workflow", "expected"),
    [
        (INJECTABLE_BLOCK, "greet.yml:10 (untrusted input in run)"),
        (INJECTABLE_INLINE, "greet.yml:7 (untrusted input in run)"),
        (PWN_REQUEST, "pull_request_target checks out PR code"),
    ],
)
def test_exploitable_workflows_fail(make_repo, workflow, expected):
    r = result(make_repo({".github/workflows/greet.yml": workflow}), "workflow-security")
    assert r.status is Status.FAIL
    assert expected in r.message


def test_workflow_without_permissions_warns(make_repo):
    r = result(make_repo({".github/workflows/test.yml": NO_PERMISSIONS}), "workflow-security")
    assert r.status is Status.WARN
    assert ".github/workflows/test.yml" in r.message


def test_no_workflows_is_skipped(make_repo):
    assert status(make_repo({".gitlab-ci.yml": "test: {}\n"}), "workflow-security") is Status.SKIP
