"""CI, tests, packaging, style, releases and repository hygiene."""

from __future__ import annotations

import fnmatch
import json
import os
import re

from ..model import Outcome, Status
from ..repo import Repo
from ._util import plural, shorten
from .documentation import changelog_versions

# --------------------------------------------------------------------------- CI

CI_SYSTEMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("GitHub Actions", (".github/workflows/*.yml", ".github/workflows/*.yaml")),
    ("GitLab CI", (".gitlab-ci.yml",)),
    ("CircleCI", (".circleci/config.yml",)),
    ("Azure Pipelines", ("azure-pipelines.yml",)),
    ("Travis CI", (".travis.yml",)),
    ("Jenkins", ("jenkinsfile",)),
    ("Bitbucket Pipelines", ("bitbucket-pipelines.yml",)),
    ("Buildkite", (".buildkite/*.yml",)),
    ("Woodpecker", (".woodpecker.yml", ".woodpecker/*.yml")),
)

_RUNS_TESTS = re.compile(
    r"\b(?:pytest|tox|nox|unittest|hatch (?:run|test)|(?:npm|pnpm|yarn|bun)(?: run)? test|npx (?:jest|vitest)"
    r"|jest|vitest|mocha|cargo (?:test|nextest)|go test|gotestsum|mvn|gradlew?|rake|rspec|bundle exec"
    r"|dotnet test|make (?:test|check)|mix test|swift test|flutter test|dart test|phpunit|pest|composer test"
    r"|ctest|meson test|deno test|zig build test|stack test|cabal test|julia-runtest|Pkg\.test|xcodebuild test"
    r"|make ci)\b"
    # A tool behind a variable ("${{ env.CARGO }} test", "$PYTHON -m pytest") or a step/job named after tests.
    r"|(?:\}\}|\$\w+)\s+test\b|^\s*-?\s*name:[^\n]*\btests?\b|^\s{2}tests?:\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_REUSABLE_WORKFLOW = re.compile(r"uses:\s*\S*\.github/workflows/")


def check_ci(repo: Repo) -> Outcome:
    found, files = [], []
    for name, patterns in CI_SYSTEMS:
        matches = repo.glob(*patterns)
        if matches:
            found.append(f"{name} ({plural(len(matches), 'file')})")
            files += matches
    if not found:
        return Status.FAIL, "No continuous integration configuration found"
    text = "\n".join(repo.read_text(f, limit=300_000) for f in files)
    if not (_RUNS_TESTS.search(text) or _REUSABLE_WORKFLOW.search(text)):
        return Status.WARN, f"{', '.join(found)}, but no test command found in it"
    return Status.PASS, ", ".join(found)


# --------------------------------------------------------------------------- tests

_TEST_DIRS = frozenset({"test", "tests", "__tests__", "spec", "specs", "testing"})
_TEST_FILE = re.compile(
    r"(?:^test_.+\.py$|_tests?\.py$|_test\.go$|\.(?:test|spec)\.[cm]?[jt]sx?$|_(?:spec|test)\.rb$"
    r"|Tests?\.(?:java|kt|cs|swift|php)$|_test\.(?:exs|dart)$|Spec\.(?:scala|kt)$)"
)


def check_tests(repo: Repo) -> Outcome:
    count = 0
    for path in repo.files:
        parts = path.split("/")
        if any(part.lower() in _TEST_DIRS for part in parts[:-1]) or _TEST_FILE.search(parts[-1]):
            count += 1
    if count:
        return Status.PASS, plural(count, "test file")
    # Rust and Zig keep unit tests next to the code.
    for pattern, marker, language in (("*.rs", "#[cfg(test)]", "Rust"), ("*.zig", 'test "', "Zig")):
        for path in repo.glob(pattern)[:2000]:
            if marker in repo.read_text(path, limit=500_000):
                return Status.PASS, f"Inline {language} tests (e.g. {path})"
    return Status.FAIL, "No tests found"


# --------------------------------------------------------------------------- manifest


def check_manifest(repo: Repo) -> Outcome:
    if not repo.ecosystems:
        return Status.FAIL, "No package manifest found at the repository root"
    return Status.PASS, "; ".join(f"{d.name} ({', '.join(d.files)})" for d in repo.ecosystems)


# --------------------------------------------------------------------------- code style

_STYLE_FILES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("EditorConfig", (".editorconfig",)),
    ("pre-commit", (".pre-commit-config.yaml", ".pre-commit-config.yml")),
    ("Ruff", ("ruff.toml", ".ruff.toml")),
    ("Flake8", (".flake8",)),
    ("Pylint", (".pylintrc", "pylintrc")),
    ("Prettier", (".prettierrc", ".prettierrc.*", "prettier.config.*")),
    ("ESLint", (".eslintrc", ".eslintrc.*", "eslint.config.*")),
    ("Biome", ("biome.json", "biome.jsonc")),
    ("Stylelint", (".stylelintrc", ".stylelintrc.*", "stylelint.config.*")),
    ("rustfmt", ("rustfmt.toml", ".rustfmt.toml")),
    ("Clippy", ("clippy.toml", ".clippy.toml")),
    ("golangci-lint", (".golangci.yml", ".golangci.yaml", ".golangci.toml", ".golangci.json")),
    ("RuboCop", (".rubocop.yml",)),
    ("Standard", (".standard.yml",)),
    ("clang-format", (".clang-format",)),
    ("SwiftLint", (".swiftlint.yml",)),
    ("PHP CS Fixer", (".php-cs-fixer.php", ".php-cs-fixer.dist.php")),
    ("Checkstyle", ("checkstyle.xml",)),
    ("Spotless/ktlint", (".ktlint", ".editorconfig-ktlint")),
    ("scalafmt", (".scalafmt.conf",)),
    ("dotnet format", ("stylecop.json",)),
)
_PYPROJECT_TOOLS = re.compile(r"^\[tool\.(ruff|black|isort|flake8|pylint|yapf)\b", re.MULTILINE)
_PACKAGE_JSON_TOOLS = re.compile(r'"(prettier|eslintConfig|biome|standard|xo)"\s*:')
# Ecosystems whose official toolchain ships a formatter everyone uses by default.
_BUILTIN_FORMATTERS = {"go": "gofmt", "rust": "rustfmt", "deno": "deno fmt", "zig": "zig fmt", "dart": "dart format"}


def check_code_style(repo: Repo) -> Outcome:
    root_files = [f.lower() for f in repo.root_files()]
    found = [
        name for name, patterns in _STYLE_FILES if any(fnmatch.fnmatchcase(f, p) for f in root_files for p in patterns)
    ]
    pyproject = repo.get("pyproject.toml")
    if pyproject:
        found += [
            f"{tool.capitalize()} (pyproject.toml)" for tool in _PYPROJECT_TOOLS.findall(repo.read_text(pyproject))
        ]
    package_json = repo.get("package.json")
    if package_json:
        found += [f"{tool} (package.json)" for tool in _PACKAGE_JSON_TOOLS.findall(repo.read_text(package_json))]
    if found:
        return Status.PASS, ", ".join(dict.fromkeys(found))
    builtin = [_BUILTIN_FORMATTERS[d.key] for d in repo.ecosystems if d.key in _BUILTIN_FORMATTERS]
    if builtin:
        return Status.PASS, f"Uses the standard formatter ({', '.join(builtin)})"
    return Status.FAIL, "No formatter, linter or .editorconfig configuration found"


# --------------------------------------------------------------------------- releases

_VERSION_TAG = re.compile(r"^(?:[\w.\-]+[-/@])?v?(\d+(?:\.\d+){1,3})(?:[-+.][\w.\-]+)?$")
_MANIFEST_VERSION = re.compile(r'^\s*version\s*=\s*"(\d+\.\d+[^"]*)"', re.MULTILINE)


def _manifest_version(text: str, name: str) -> str | None:
    if name == "package.json":
        try:
            data = json.loads(text)
        except ValueError:
            return None
        version = data.get("version") if isinstance(data, dict) else None
        return version if isinstance(version, str) and re.match(r"\d+\.\d+", version) else None
    match = _MANIFEST_VERSION.search(text)
    return match.group(1) if match else None


def _version_key(version: str) -> tuple[int, ...]:
    match = re.match(r"\d+(?:\.\d+)*", version)
    return tuple(int(p) for p in match.group(0).split(".")) if match else ()


def check_releases(repo: Repo) -> Outcome:
    tags = repo.tags
    versions = [m.group(1) for m in map(_VERSION_TAG.match, tags or []) if m]
    if versions:
        latest = max(versions, key=_version_key)
        return Status.PASS, f"{plural(len(versions), 'version tag')} (latest {latest})"
    logged = changelog_versions(repo)
    if logged and tags is None:
        latest = max(logged, key=_version_key)
        return Status.PASS, f"Changelog lists {plural(len(logged), 'release')} (latest {latest})"
    if logged:
        return Status.WARN, f"Changelog lists {plural(len(logged), 'release')} but there are no git tags"
    for name in ("pyproject.toml", "package.json", "Cargo.toml"):
        path = repo.get(name)
        version = _manifest_version(repo.read_text(path), name) if path else None
        if version:
            missing = "no changelog entries (git tags unavailable)" if tags is None else "no version tags"
            return Status.WARN, f"Version {version} in {path}, but {missing}"
    return Status.FAIL, "No version tags or released versions found"


# --------------------------------------------------------------------------- hygiene


def check_gitignore(repo: Repo) -> Outcome:
    path = repo.get(".gitignore")
    if path:
        return Status.PASS, path
    return Status.FAIL, "No .gitignore found"


DEPENDENCY_BOTS = (
    ("Dependabot", (".github/dependabot.yml", ".github/dependabot.yaml")),
    (
        "Renovate",
        (
            "renovate.json",
            "renovate.json5",
            ".renovaterc",
            ".renovaterc.json",
            ".renovaterc.json5",
            ".github/renovate.json",
            ".github/renovate.json5",
            ".gitlab/renovate.json",
        ),
    ),
)


def check_dependency_updates(repo: Repo) -> Outcome:
    for name, paths in DEPENDENCY_BOTS:
        for path in paths:
            real = repo.get(path)
            if real:
                return Status.PASS, f"{name} ({real})"
    return Status.FAIL, "No Dependabot or Renovate configuration found"


_LARGE_WARN = 10 * 1024 * 1024
_LARGE_FAIL = 50 * 1024 * 1024  # GitHub warns on push above 50 MB and rejects files above 100 MB
_LFS_PATTERN = re.compile(r"^\s*(\S+)\s.*\bfilter=lfs\b", re.MULTILINE)


def _megabytes(size: int) -> str:
    return f"{size / (1024 * 1024):.0f} MB"


def check_large_files(repo: Repo) -> Outcome:
    attributes = repo.get(".gitattributes")
    lfs = _LFS_PATTERN.findall(repo.read_text(attributes)) if attributes else []
    big: list[tuple[str, int]] = []
    for path in repo.files:
        size = repo.size(path)
        if size < _LARGE_WARN:
            continue
        name = os.path.basename(path)
        if any(fnmatch.fnmatch(path, p.lstrip("/")) or fnmatch.fnmatch(name, p) for p in lfs):
            continue
        big.append((path, size))
    if not big:
        return Status.PASS, "No files over 10 MB" + (" outside Git LFS" if lfs else "")
    big.sort(key=lambda item: -item[1])
    listed = shorten([f"{p} ({_megabytes(s)})" for p, s in big])
    if big[0][1] >= _LARGE_FAIL:
        return Status.FAIL, f"Files too large for a git repository: {listed}"
    return Status.WARN, f"Large files in the repository: {listed}"
