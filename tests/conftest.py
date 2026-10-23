from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Callable

import pytest

from ossready import Status, run_checks

GOOD_README = """# demo

A small library that does one thing well. This paragraph exists so the README is long enough
to count as real documentation rather than a placeholder that only repeats the project name.

## Installation

    pip install demo

## Usage

```python
import demo
demo.run()
```

See [CONTRIBUTING.md](CONTRIBUTING.md) and the [license](LICENSE).
"""

MIT_TEXT = """MIT License

Copyright (c) 2026 Someone

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction.
"""

CI_WORKFLOW = """name: CI
on: [push, pull_request]
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pytest
"""

# A repository that passes every check.
COMPLETE_REPO = {
    "README.md": GOOD_README,
    "LICENSE": MIT_TEXT,
    "CONTRIBUTING.md": "How to contribute.\n",
    "CHANGELOG.md": "# Changelog\n\n## [Unreleased]\n\n## [1.0.0] - 2026-01-01\n\n- First release.\n",
    "CODE_OF_CONDUCT.md": "Be kind.\n",
    "SECURITY.md": "Report privately.\n",
    ".github/ISSUE_TEMPLATE/bug_report.yml": "name: Bug\n",
    ".github/pull_request_template.md": "- [ ] tests\n",
    ".github/CODEOWNERS": "* @someone\n",
    ".github/FUNDING.yml": "github: [someone]\n",
    ".github/workflows/ci.yml": CI_WORKFLOW,
    ".github/dependabot.yml": "version: 2\n",
    ".editorconfig": "root = true\n",
    "tests/test_demo.py": "def test_ok():\n    assert True\n",
    "pyproject.toml": '[project]\nname = "demo"\nversion = "1.0.0"\nlicense = "MIT"\n',
    ".gitignore": "__pycache__/\n",
    "src/demo/__init__.py": "def run():\n    return 1\n",
}

MakeRepo = Callable[[dict], Path]

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def write_files(root: Path, files: dict) -> Path:
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
    return root


@pytest.fixture
def make_repo(tmp_path: Path) -> MakeRepo:
    """Create a directory containing ``files`` ({relative path: text or bytes})."""

    def make(files: dict) -> Path:
        root = tmp_path / "repo"
        root.mkdir(exist_ok=True)
        return write_files(root, files)

    return make


def git(root: Path, *args: str) -> str:
    """Run git in ``root`` with a throwaway identity."""
    proc = subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "-c", "init.defaultBranch=main", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout


def result(root, check_id):
    report = run_checks(root)
    found = report.get(check_id)
    assert found is not None
    return found


def status(root, check_id) -> Status:
    return result(root, check_id).status
