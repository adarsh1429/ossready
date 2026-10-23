"""Detect which language ecosystems a repository belongs to."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .repo import Repo


@dataclass(frozen=True)
class Ecosystem:
    key: str
    name: str
    manifests: tuple[str, ...]  # lower-case glob patterns matched against root-level file names
    dependabot: str | None = None  # Dependabot's package-ecosystem value, if it supports this one


ECOSYSTEMS: tuple[Ecosystem, ...] = (
    Ecosystem("python", "Python", ("pyproject.toml", "setup.py", "setup.cfg"), "pip"),
    Ecosystem("node", "Node.js", ("package.json",), "npm"),
    Ecosystem("deno", "Deno", ("deno.json", "deno.jsonc")),
    Ecosystem("rust", "Rust", ("cargo.toml",), "cargo"),
    Ecosystem("go", "Go", ("go.mod",), "gomod"),
    Ecosystem("maven", "Java (Maven)", ("pom.xml",), "maven"),
    Ecosystem("gradle", "Java/Kotlin (Gradle)", ("build.gradle", "build.gradle.kts"), "gradle"),
    Ecosystem("ruby", "Ruby", ("gemfile", "*.gemspec"), "bundler"),
    Ecosystem("php", "PHP", ("composer.json",), "composer"),
    Ecosystem("elixir", "Elixir", ("mix.exs",), "mix"),
    Ecosystem("swift", "Swift", ("package.swift",), "swift"),
    Ecosystem("dotnet", ".NET", ("*.csproj", "*.fsproj", "*.sln"), "nuget"),
    Ecosystem("dart", "Dart", ("pubspec.yaml",), "pub"),
    Ecosystem("haskell", "Haskell", ("*.cabal", "stack.yaml")),
    Ecosystem("julia", "Julia", ("project.toml",)),
    Ecosystem("zig", "Zig", ("build.zig",)),
    Ecosystem("cpp", "C/C++", ("cmakelists.txt", "meson.build", "configure.ac")),
)

BY_KEY = {e.key: e for e in ECOSYSTEMS}


@dataclass(frozen=True)
class Detected:
    ecosystem: Ecosystem
    files: tuple[str, ...]

    @property
    def key(self) -> str:
        return self.ecosystem.key

    @property
    def name(self) -> str:
        return self.ecosystem.name


def detect(repo: Repo) -> tuple[Detected, ...]:
    """Ecosystems whose manifest sits at the repository root, in ECOSYSTEMS order."""
    root_files = [f for f in repo.files if "/" not in f]
    found = []
    for eco in ECOSYSTEMS:
        matches = tuple(f for f in root_files if any(fnmatch.fnmatchcase(f.lower(), p) for p in eco.manifests))
        if matches:
            found.append(Detected(eco, matches))
    return tuple(found)
