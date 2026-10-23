"""How to set up, test and run CI for each ecosystem ``ossready fix`` knows about."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from ..repo import Repo
from .templates import fill


@dataclass(frozen=True)
class Toolchain:
    setup: tuple[str, ...]
    test: tuple[str, ...]
    lint: tuple[str, ...] = ()
    ci_job: str | None = None  # a GitHub Actions job, indented for the `jobs:` mapping
    notes: tuple[str, ...] = field(default=())  # things the maintainer should double-check


def _package_json(repo: Repo) -> dict:
    path = repo.get("package.json")
    if not path:
        return {}
    try:
        data = json.loads(repo.read_text(path))
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


LATEST_PYTHON_MINOR = 14


def _python_versions(pyproject: str) -> list[str]:
    """Supported CPython versions from requires-python, skipping ones past end of life."""
    match = re.search(r'requires-python\s*=\s*["\']\s*>=?\s*3\.(\d+)', pyproject)
    low = max(int(match.group(1)) if match else 10, 10)
    return [f"3.{minor}" for minor in range(low, LATEST_PYTHON_MINOR + 1)] or [f"3.{LATEST_PYTHON_MINOR}"]


def python(repo: Repo) -> Toolchain:
    pyproject = repo.read_text(repo.get("pyproject.toml")) if repo.get("pyproject.toml") else ""
    extras = re.search(r"^\[project\.optional-dependencies\]\s*$(.*?)(?=^\[|\Z)", pyproject, re.M | re.S)
    has_dev_extra = bool(extras and re.search(r"^\s*dev\s*=", extras.group(1), re.M))
    if has_dev_extra:
        install = 'pip install -e ".[dev]"'
    elif repo.get("requirements-dev.txt"):
        install = "pip install -e . -r requirements-dev.txt"
    else:
        install = "pip install -e . pytest"
    versions = ", ".join(f'"{v}"' for v in _python_versions(pyproject))
    job = fill(
        """\
  test-python:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: [[[versions]]]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: python -m pip install --upgrade pip
      - run: [[install]]
      - run: pytest
""",
        versions=versions,
        install=install,
    )
    lint = ("ruff check .", "ruff format --check .") if "[tool.ruff" in pyproject else ()
    return Toolchain(
        setup=("python -m venv .venv", "source .venv/bin/activate    # on Windows: .venv\\Scripts\\activate", install),
        test=("pytest",),
        lint=lint,
        ci_job=job,
    )


def node(repo: Repo) -> Toolchain:
    data = _package_json(repo)
    scripts = data.get("scripts") if isinstance(data.get("scripts"), dict) else {}
    if repo.get("pnpm-lock.yaml"):
        pm, install, ci_install = "pnpm", "pnpm install", "pnpm install --frozen-lockfile"
    elif repo.get("yarn.lock"):
        pm, install, ci_install = "yarn", "yarn install", "yarn install --immutable"
    elif repo.get("bun.lockb") or repo.get("bun.lock"):
        pm, install, ci_install = "bun", "bun install", "bun install --frozen-lockfile"
    else:
        pm, install = "npm", "npm install"
        ci_install = "npm ci" if repo.get("package-lock.json") else "npm install"
    steps = ["      - uses: actions/checkout@v4"]
    if pm == "bun":
        steps.append("      - uses: oven-sh/setup-bun@v2")
    else:
        steps += [
            "      - uses: actions/setup-node@v4",
            "        with:",
            "          node-version: ${{ matrix.node-version }}",
        ]
        if pm in ("pnpm", "yarn"):
            steps.append("      - run: corepack enable")
    steps.append(f"      - run: {ci_install}")
    notes = []
    if "build" in scripts:
        steps.append(f"      - run: {pm} run build")
    if "test" in scripts:
        steps.append(f"      - run: {pm} test")
    else:
        notes.append('package.json has no "test" script, so CI only installs and builds')
    matrix = "" if pm == "bun" else "    strategy:\n      matrix:\n        node-version: [22, 24]\n"
    job = f"  test-node:\n    runs-on: ubuntu-latest\n{matrix}    steps:\n" + "\n".join(steps) + "\n"
    lint = (f"{pm} run lint",) if "lint" in scripts else ()
    return Toolchain(setup=(install,), test=(f"{pm} test",), lint=lint, ci_job=job, notes=tuple(notes))


def rust(repo: Repo) -> Toolchain:
    job = """\
  test-rust:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: cargo build --verbose
      - run: cargo test --verbose
"""
    return Toolchain(
        setup=("cargo build",),
        test=("cargo test",),
        lint=("cargo fmt --all --check", "cargo clippy --all-targets"),
        ci_job=job,
    )


def go(repo: Repo) -> Toolchain:
    job = """\
  test-go:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with:
          go-version-file: go.mod
      - run: go build ./...
      - run: go test ./...
"""
    return Toolchain(
        setup=("go build ./...",), test=("go test ./...",), lint=("go vet ./...", "gofmt -l ."), ci_job=job
    )


def _java_steps(cache: str) -> str:
    return f"""\
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: 21
          cache: {cache}
"""


def maven(repo: Repo) -> Toolchain:
    job = (
        "  test-maven:\n    runs-on: ubuntu-latest\n    steps:\n"
        + _java_steps("maven")
        + "      - run: mvn -B verify\n"
    )
    return Toolchain(setup=("mvn -B install -DskipTests",), test=("mvn -B test",), ci_job=job)


def gradle(repo: Repo) -> Toolchain:
    wrapper = repo.get("gradlew") is not None
    cmd = "./gradlew" if wrapper else "gradle"
    setup_gradle = "      - uses: gradle/actions/setup-gradle@v4\n"
    if not wrapper:
        setup_gradle += "        with:\n          gradle-version: current\n"
    job = (
        "  test-gradle:\n    runs-on: ubuntu-latest\n    steps:\n"
        + _java_steps("gradle")
        + setup_gradle
        + f"      - run: {cmd} build\n"
    )
    return Toolchain(setup=(f"{cmd} build -x test",), test=(f"{cmd} test",), ci_job=job)


def ruby(repo: Repo) -> Toolchain:
    if repo.under("spec"):
        test = "bundle exec rspec"
    elif repo.get("Rakefile"):
        test = "bundle exec rake"
    else:
        test = "bundle exec rake test"
    version = "" if repo.get(".ruby-version") else "          ruby-version: '3.4'\n"
    job = (
        "  test-ruby:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - uses: actions/checkout@v4\n"
        "      - uses: ruby/setup-ruby@v1\n"
        "        with:\n"
        f"{version}"
        "          bundler-cache: true\n"
        f"      - run: {test}\n"
    )
    return Toolchain(setup=("bundle install",), test=(test,), ci_job=job)


def dotnet(repo: Repo) -> Toolchain:
    version = (
        "          global-json-file: global.json\n" if repo.get("global.json") else "          dotnet-version: 10.0.x\n"
    )
    job = (
        "  test-dotnet:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - uses: actions/checkout@v4\n"
        "      - uses: actions/setup-dotnet@v4\n"
        "        with:\n"
        f"{version}"
        "      - run: dotnet restore\n"
        "      - run: dotnet build --no-restore\n"
        "      - run: dotnet test --no-build\n"
    )
    return Toolchain(
        setup=("dotnet restore",), test=("dotnet test",), lint=("dotnet format --verify-no-changes",), ci_job=job
    )


def php(repo: Repo) -> Toolchain:
    composer = repo.get("composer.json")
    data = {}
    if composer:
        try:
            data = json.loads(repo.read_text(composer))
        except ValueError:
            data = {}
    scripts = data.get("scripts") if isinstance(data, dict) and isinstance(data.get("scripts"), dict) else {}
    if "test" in scripts:
        test = "composer test"
    elif repo.get("phpunit.xml") or repo.get("phpunit.xml.dist"):
        test = "vendor/bin/phpunit"
    else:
        test = ""
    job = (
        "  test-php:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - uses: actions/checkout@v4\n"
        "      - uses: shivammathur/setup-php@v2\n"
        "        with:\n"
        "          php-version: '8.4'\n"
        "      - run: composer install --prefer-dist --no-progress\n" + (f"      - run: {test}\n" if test else "")
    )
    notes = () if test else ("no PHPUnit config or composer test script found, so CI only installs dependencies",)
    return Toolchain(setup=("composer install",), test=(test or "vendor/bin/phpunit",), ci_job=job, notes=notes)


def dart(repo: Repo) -> Toolchain:
    pubspec = repo.read_text(repo.get("pubspec.yaml")) if repo.get("pubspec.yaml") else ""
    if re.search(r"^\s*flutter:", pubspec, re.MULTILINE):
        return Toolchain(setup=("flutter pub get",), test=("flutter test",))
    job = """\
  test-dart:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: dart-lang/setup-dart@v1
      - run: dart pub get
      - run: dart analyze
      - run: dart test
"""
    return Toolchain(setup=("dart pub get",), test=("dart test",), lint=("dart analyze",), ci_job=job)


def elixir(repo: Repo) -> Toolchain:
    return Toolchain(setup=("mix deps.get",), test=("mix test",), lint=("mix format --check-formatted",))


def swift(repo: Repo) -> Toolchain:
    return Toolchain(setup=("swift build",), test=("swift test",))


def deno(repo: Repo) -> Toolchain:
    job = """\
  test-deno:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: denoland/setup-deno@v2
      - run: deno fmt --check
      - run: deno lint
      - run: deno test
"""
    return Toolchain(setup=(), test=("deno test",), lint=("deno fmt --check", "deno lint"), ci_job=job)


TOOLCHAINS = {
    "python": python,
    "node": node,
    "deno": deno,
    "rust": rust,
    "go": go,
    "maven": maven,
    "gradle": gradle,
    "ruby": ruby,
    "php": php,
    "elixir": elixir,
    "swift": swift,
    "dotnet": dotnet,
    "dart": dart,
}


def toolchains(repo: Repo) -> list[tuple[str, Toolchain]]:
    """(ecosystem name, toolchain) for every detected ecosystem ossready knows how to build."""
    return [(d.name, TOOLCHAINS[d.key](repo)) for d in repo.ecosystems if d.key in TOOLCHAINS]
