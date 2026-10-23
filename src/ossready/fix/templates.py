"""Text templates used by ``ossready fix``.

Placeholders look like ``[[name]]`` so they never clash with GitHub Actions ``${{ }}``
expressions, Markdown or YAML.
"""

from __future__ import annotations

import re

_PLACEHOLDER = re.compile(r"\[\[(\w+)\]\]")


def fill(template: str, **values: str) -> str:
    def replace(match: re.Match[str]) -> str:
        return values[match.group(1)]

    return _PLACEHOLDER.sub(replace, template)


# --------------------------------------------------------------------------- community files

CODE_OF_CONDUCT = """\
# Code of Conduct

[[name]] adopts the [Contributor Covenant, version 2.1](https://www.contributor-covenant.org/version/2/1/code_of_conduct/)
as its code of conduct. Everyone taking part in issues, pull requests, discussions and any other
project space is expected to follow it.

## In short

- Be respectful and welcoming, whatever someone's background or level of experience.
- Give and accept constructive feedback gracefully; critique code, not people.
- No harassment, insults, sexualised language or imagery, or publishing others' private information.

## Reporting

If you experience or witness unacceptable behaviour, [[contact]]. All reports will be reviewed
promptly and handled confidentially. Maintainers may remove comments, commits or other
contributions, and may ban contributors temporarily or permanently, as described in the
Contributor Covenant's enforcement guidelines.
"""

SECURITY = """\
# Security Policy

## Supported versions

Security fixes are made for the latest release. Please check that you can reproduce an issue on
the latest version before reporting it.

## Reporting a vulnerability

Please **do not** report security vulnerabilities through public issues, discussions or pull requests.

Instead, report them privately [[channel]].

Please include:

- a description of the problem and its impact,
- steps to reproduce it, or a proof of concept,
- the versions affected.

You should receive a response within 7 days. We will keep you informed while we work on a fix and,
unless you prefer to stay anonymous, credit you in the release notes.
"""

CHANGELOG = """\
# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
"""

BUG_REPORT = """\
name: Bug report
description: Something isn't working as expected.
labels: [bug]
body:
  - type: markdown
    attributes:
      value: Thanks for taking the time to report a problem! Please search existing issues first.
  - type: textarea
    id: what-happened
    attributes:
      label: What happened?
      description: Include the exact steps, commands or code that trigger the problem, and any error output.
    validations:
      required: true
  - type: textarea
    id: expected
    attributes:
      label: What did you expect to happen?
    validations:
      required: true
  - type: input
    id: version
    attributes:
      label: Version
      description: Which version of [[name]] are you using?
    validations:
      required: true
  - type: input
    id: environment
    attributes:
      label: Environment
      placeholder: e.g. operating system, runtime version
"""

FEATURE_REQUEST = """\
name: Feature request
description: Suggest an idea or improvement.
labels: [enhancement]
body:
  - type: textarea
    id: problem
    attributes:
      label: What problem would this solve?
    validations:
      required: true
  - type: textarea
    id: proposal
    attributes:
      label: What would you like to happen?
    validations:
      required: true
  - type: textarea
    id: alternatives
    attributes:
      label: Alternatives you've considered
"""

ISSUE_CONFIG = """\
blank_issues_enabled: true
contact_links:
  - name: Report a security vulnerability
    url: https://github.com/[[slug]]/security/advisories/new
    about: Please report security issues privately, not as public issues.
"""

PULL_REQUEST = """\
## What does this change?

<!-- Describe the change and link the issue it closes, e.g. "Closes #123". -->

## Checklist

- [ ] Tests added or updated for the change
[[checks]]- [ ] Documentation updated if behaviour changed
"""

CODEOWNERS = """\
# These owners are requested for review on every pull request.
# See https://docs.github.com/articles/about-code-owners
* @[[owner]]
"""

# --------------------------------------------------------------------------- engineering files

EDITORCONFIG = """\
# https://editorconfig.org
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
trim_trailing_whitespace = true
indent_style = space
indent_size = 4

[*.{js,jsx,ts,tsx,mjs,cjs,json,jsonc,yml,yaml,html,css,scss,vue,svelte,rb,dart,tf}]
indent_size = 2

[*.md]
trim_trailing_whitespace = false

[{Makefile,*.mk,*.go,go.mod}]
indent_style = tab
"""

DEPENDABOT_HEADER = """\
# Keeps dependencies up to date. Minor and patch updates are grouped into a single
# pull request per ecosystem to keep the noise down.
# https://docs.github.com/code-security/dependabot/working-with-dependabot/dependabot-options-reference
version: 2
updates:
"""

DEPENDABOT_ENTRY = """\
  - package-ecosystem: [[ecosystem]]
    directory: /
    schedule:
      interval: weekly
    groups:
      [[ecosystem]]-minor-and-patch:
        update-types: [minor, patch]
"""

CI_HEADER = """\
name: CI

on:
  push:
    branches: [[[branch]]]
  pull_request:

permissions:
  contents: read

jobs:
"""

GITIGNORE_COMMON = """\
# Environment and secrets
.env
.env.*
!.env.example

# Editors and operating systems
.idea/
.vscode/
*.swp
.DS_Store
Thumbs.db
"""

GITIGNORE: dict[str, str] = {
    "python": """\
# Python
__pycache__/
*.py[cod]
*.egg-info/
.eggs/
build/
dist/
.venv/
venv/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.tox/
.nox/
.coverage
htmlcov/
""",
    "node": """\
# Node.js
node_modules/
dist/
coverage/
.npm/
*.log
.next/
.nuxt/
.turbo/
""",
    "deno": """\
# Deno
.deno/
""",
    "rust": """\
# Rust
/target/
""",
    "go": """\
# Go
/bin/
*.test
*.out
coverage.*
""",
    "maven": """\
# Maven
target/
""",
    "gradle": """\
# Gradle
.gradle/
build/
!gradle/wrapper/gradle-wrapper.jar
""",
    "ruby": """\
# Ruby
/.bundle/
/vendor/bundle/
/coverage/
/pkg/
*.gem
""",
    "php": """\
# PHP
/vendor/
.phpunit.result.cache
""",
    "elixir": """\
# Elixir
/_build/
/deps/
/cover/
*.ez
""",
    "swift": """\
# Swift
.build/
.swiftpm/
DerivedData/
""",
    "dotnet": """\
# .NET
bin/
obj/
*.user
.vs/
TestResults/
""",
    "dart": """\
# Dart
.dart_tool/
build/
""",
    "haskell": """\
# Haskell
dist-newstyle/
.stack-work/
""",
    "zig": """\
# Zig
zig-cache/
.zig-cache/
zig-out/
""",
    "cpp": """\
# C/C++
build/
cmake-build-*/
*.o
*.obj
*.a
*.so
*.dylib
*.dll
*.exe
""",
}
