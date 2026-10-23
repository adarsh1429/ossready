# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.0] - 2026-10-23

### Added

- `ossready fix` creates missing files tailored to the project: README, LICENSE (10 licenses, with
  dual licensing), CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, CHANGELOG, issue and pull request
  templates, CODEOWNERS, a CI workflow, Dependabot config, `.gitignore` and `.editorconfig`.
  Supports `--dry-run`, `--only`, `--license`, `--owner`, `--author` and `--email`, and never
  overwrites existing files.
- CI templates for Python, Node.js (npm, pnpm, yarn, bun), Rust, Go, Maven, Gradle, Ruby, PHP,
  .NET, Dart and Deno, all with least-privilege permissions.
- Seven new checks: `readme-links`, `license-consistency`, `funding`, `code-style`, `releases`,
  `large-files` and `workflow-security` (script injection, `pull_request_target` misuse and missing
  `permissions:` in GitHub Actions).
- The `ci` check warns when the CI configuration doesn't appear to run tests.
- Check remote repositories directly: `ossready github.com/owner/repo`, `gh:owner/repo` or any git URL.
- Configuration in `.ossready.toml` or `[tool.ossready]`: `ignore`, `fail-under` and `weights`.
- `ossready explain CHECK` and `ossready list` commands.
- `--format badge` and a badge in Markdown reports; the GitHub Action now outputs `badge`.
- Skipped status for checks that don't apply, which are left out of the score.
- pre-commit hook and a PyPI release workflow using trusted publishing.
- Secret scan detects GitLab, Hugging Face, SendGrid and Twilio tokens and Slack webhooks.
- `py.typed` marker and a public Python API for planning and applying fixes.

### Changed

- Checks are grouped into modules under `ossready.checks`; weights were rebalanced for 22 checks.
- `--fail-under` and `--ignore` errors now exit with status 2 instead of raising.
- Symlinks that point outside the repository are ignored.
- Fewer false positives: keys in docs and examples only warn, private-key headers without key
  material are ignored, shallow clones fall back to the changelog for the releases check, manifests
  that can't declare a license (tool-only `pyproject.toml`, Cargo workspaces, private packages) are
  skipped, and the large-file warning starts at 10 MB.

## [0.1.0] - 2026-10-23

### Added

- First release with 15 checks across documentation, community, engineering and security.
- Score from 0 to 100 with letter grades and a fix hint for every failed check.
- Text, JSON and Markdown output.
- `--fail-under`, `--ignore` and `--list-checks` options.
- License detection for 16 common licenses.
- Secret scan for private keys and common token formats.
- GitHub Action that writes the report to the job summary.
