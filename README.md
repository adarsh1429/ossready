# ossready

**Score how ready a repository is for open source, then fix it in one command.**

`ossready` checks a repository against 22 things maintainers, contributors and security teams
expect from an open-source project, scores it from 0 to 100, and tells you exactly how to close
each gap. `ossready fix` then writes the missing files for you (license, contributing guide,
security policy, CI workflow, Dependabot config, issue templates and more), tailored to your
project's language and never touching files you already have.

```text
$ ossready fix
ossready fix — /home/jane/tinylib

Created
  + LICENSE                                     MIT, Copyright (c) 2026 Jane Doe
  + CODE_OF_CONDUCT.md
  + SECURITY.md
  + CHANGELOG.md
  + .gitignore                                  Python
  + .editorconfig
  + .github/workflows/ci.yml                    Python
  + .github/dependabot.yml                      pip, github-actions
  + .github/ISSUE_TEMPLATE/bug_report.yml
  + .github/ISSUE_TEMPLATE/feature_request.yml
  + .github/ISSUE_TEMPLATE/config.yml
  + .github/pull_request_template.md
  + .github/CODEOWNERS                          @janedoe
  + CONTRIBUTING.md
  + README.md

Please review
  · SECURITY.md: turn on private vulnerability reporting in the repository's Security settings
  · README.md: add a real usage example

Still to do by hand
  ✗ Funding: Add .github/FUNDING.yml (GitHub Sponsors, Open Collective, ...) to show a Sponsor
    button.
  ! Versioned releases: Version 0.1.0 in pyproject.toml, but no version tags
    → Tag releases with semantic versions (git tag v1.0.0 && git push --tags) and list them in the
      changelog.

Score  27/100 (F) → 98/100 (A)
```

## Why

Publishing code is easy. Running a project other people can safely use and contribute to is not:
without a license nobody may legally reuse your code, without a security policy vulnerabilities
get reported in public, and a single careless workflow can hand your CI to anyone who opens a pull
request. ossready turns that checklist into one command that runs in seconds.

- **Finds problems and fixes them.** 22 checks, a concrete fix for every failure, and `ossready fix` to write the files.
- **Knows your stack.** Detects 17 ecosystems and generates matching CI jobs, Dependabot config, `.gitignore` and contributor instructions for Python, Node.js, Rust, Go, Java, Ruby, PHP, .NET, Dart and Deno.
- **Checks security, not just paperwork.** Finds committed secrets, script injection and `pull_request_target` mistakes in GitHub Actions workflows, and workflows running with default token permissions.
- **Checks any repository.** `ossready github.com/owner/repo` works without cloning by hand.
- **Fits into CI.** GitHub Action with job summary, pre-commit hook, `--fail-under`, JSON, Markdown and badge output.
- **Lightweight and offline.** Pure Python standard library on 3.11+ (3.9+ supported), no network calls for local checks, respects `.gitignore`.

## Installation

```bash
pip install git+https://github.com/OWNER/ossready.git
```

Or from a clone: `pip install .`

## Usage

### Check a repository

```bash
ossready                                # the current directory
ossready path/to/repo                   # another directory
ossready github.com/pallets/flask       # any public git repository (also gh:owner/repo or a full URL)
ossready --format json                  # machine-readable
ossready --format markdown              # a table for a PR comment or job summary
ossready --format badge                 # a shields.io badge for your README
ossready --fail-under 80                # exit 1 below 80, for CI
ossready --ignore funding,codeowners    # skip checks that don't apply to you
```

### Fix what's missing

```bash
ossready fix --dry-run                  # preview the files it would create
ossready fix                            # create them
ossready fix --only license,ci          # just these checks
ossready fix --license Apache-2.0       # choose the license (default: what your manifest declares, else MIT)
ossready fix --owner my-org --email security@example.com
```

`fix` reads your project before writing anything:

- **Project details** (name, description, install command) come from `pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod` or `composer.json`.
- **GitHub owner, author and contact email** come from your `origin` remote and git config. Flags override them.
- **License** follows what your package manifest declares. `MIT OR Apache-2.0` produces Rust-style `LICENSE-MIT` and `LICENSE-APACHE` files. Texts come from [choosealicense.com](https://choosealicense.com), so GitHub recognises them. Available: MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause, ISC, MPL-2.0, GPL-3.0, LGPL-3.0, AGPL-3.0, Unlicense.
- **CI** uses your package manager (npm, pnpm, yarn or bun), your Python version range from `requires-python`, your Gradle wrapper, `global.json` or `.ruby-version`. Every workflow it writes has least-privilege `permissions`.
- **Links** only point at files that exist or are being created, so the README it writes passes the link check.

Existing files are never modified or overwritten. Anything that needs a human (writing tests, tagging a
release, filling in a usage example) is listed at the end.

### Learn about a check

```bash
ossready list                 # every check with its ID, weight and whether fix can create it
ossready explain workflow-security
```

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success (and the score met `--fail-under`, if set) |
| 1 | The score is below `--fail-under` |
| 2 | Bad arguments, bad config, a path that isn't a directory, or a repository that couldn't be cloned |

## What it checks

| ID | Weight | Passes when | Fix |
|----|-------:|-------------|:---:|
| **Documentation** | | | |
| `readme` | 9 | A README of real length with installation and usage sections | ✓ |
| `readme-links` | 3 | Every relative link and image in the README points at a file that exists | |
| `license` | 12 | A LICENSE file whose text is recognised (16 common licenses) | ✓ |
| `license-consistency` | 3 | The license in your package manifest matches the LICENSE file | |
| `contributing` | 6 | `CONTRIBUTING.md` in the root, `.github/` or `docs/` | ✓ |
| `changelog` | 3 | `CHANGELOG`, `CHANGES`, `HISTORY` or `NEWS` | ✓ |
| **Community** | | | |
| `code-of-conduct` | 4 | `CODE_OF_CONDUCT.md` | ✓ |
| `security-policy` | 6 | `SECURITY.md` | ✓ |
| `issue-templates` | 3 | Templates in `.github/ISSUE_TEMPLATE/` | ✓ |
| `pr-template` | 2 | A pull request template | ✓ |
| `codeowners` | 2 | A `CODEOWNERS` file | ✓ |
| `funding` | 1 | `.github/FUNDING.yml` | |
| **Engineering** | | | |
| `ci` | 9 | CI configuration (9 systems) that runs a test command | ✓ |
| `tests` | 9 | Test files or directories for common languages, or inline Rust/Zig tests | |
| `manifest` | 4 | A package manifest for one of 17 ecosystems | |
| `code-style` | 3 | A formatter, linter or `.editorconfig` (or a language with a standard formatter) | ✓ |
| `releases` | 3 | Semantic version tags, or released versions in the changelog | |
| `gitignore` | 2 | A `.gitignore` | ✓ |
| `dependency-updates` | 3 | Dependabot or Renovate configuration | ✓ |
| `large-files` | 2 | No files over 10 MB outside Git LFS (over 50 MB fails) | |
| **Security** | | | |
| `secrets` | 8 | No private keys, cloud, registry or AI provider tokens, or credential files | |
| `workflow-security` | 3 | GitHub Actions workflows set `permissions:`, don't interpolate untrusted input into `run:`, and don't run PR code from `pull_request_target` | |

A pass earns the full weight, a warning half, a failure nothing. Checks that don't apply (for
example workflow security in a repository without workflows) are skipped and left out of the
score. Grades: A ≥ 90, B ≥ 75, C ≥ 60, D ≥ 40, otherwise F.

The secret scan reports file and line only, never the secret. Keys found in tests, fixtures,
docs or examples only produce a warning, since those often contain dummy keys on purpose, and a
private-key header without key material after it (as in documentation) is ignored. It is a quick
safety net, not a replacement for a dedicated scanner such as gitleaks or GitHub secret scanning.

## Configuration

Put settings in `.ossready.toml`, or under `[tool.ossready]` in `pyproject.toml`:

```toml
ignore = ["funding", "codeowners"]   # checks that don't apply to this project
fail-under = 85                      # minimum score, used when --fail-under isn't given

[weights]                            # change how much individual checks count
tests = 15
```

Command-line flags add to `ignore` and override `fail-under`. Use `--no-config` to ignore the file.

## Use it in CI

### GitHub Action

```yaml
# .github/workflows/ossready.yml
name: ossready
on: [push, pull_request]

permissions:
  contents: read

jobs:
  ossready:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # lets the releases check see your tags
      - uses: OWNER/ossready@v0.2.0
        with:
          fail-under: 80
```

The report appears in the job log and as a table in the job summary.

| Input | Default | Description |
|-------|---------|-------------|
| `path` | `.` | Directory to check |
| `fail-under` | from config, else none | Fail the job below this score |
| `ignore` | | Comma-separated check IDs to skip |
| `python-version` | `3.13` | Python used to run ossready |

Outputs: `score`, `grade` and `badge` (Markdown for a shields.io badge).

### pre-commit

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/OWNER/ossready
    rev: v0.2.0
    hooks:
      - id: ossready
        args: [--fail-under, "80"]
```

## Use it from Python

```python
from ossready import FixOptions, apply_plan, plan_fixes, run_checks

report = run_checks("path/to/repo", ignore=["funding"])
print(report.score, report.grade)
for result in report.results:
    print(result.id, result.status.value, result.message)

plan = plan_fixes("path/to/repo", FixOptions(license="Apache-2.0", owner="my-org"))
for new_file in plan.files:
    print("would create", new_file.path)
apply_plan(plan, "path/to/repo")
```

## Limitations

- ossready only sees what is in the folder. Community files that GitHub inherits from an
  organization's `.github` repository (a shared `SECURITY.md`, for example) aren't visible to it;
  skip those checks with `ignore` if that's how your project is set up.
- Repository settings that live on GitHub, such as branch protection or private vulnerability
  reporting, can't be checked offline. `fix` reminds you to turn the important ones on.

## Contributing

New checks, new ecosystems and bug reports are all welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md)
to get set up. This project follows a [Code of Conduct](CODE_OF_CONDUCT.md), and security issues
should be reported as described in [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE)
