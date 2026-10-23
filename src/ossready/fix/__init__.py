"""``ossready fix``: create the missing files a repository needs, tailored to its ecosystem.

Existing files are never modified or overwritten.
"""

from __future__ import annotations

import datetime
import json
import os
import re
from dataclasses import dataclass, field
from typing import Callable, Union

from ..checks import BY_ID, run_checks
from ..licenses import (
    BUNDLED,
    bundled_id,
    canonical_ids,
    declared_licenses,
    identify_license,
    license_files,
    license_text,
)
from ..model import Report, Status
from ..repo import Repo
from . import templates as t
from .toolchains import Toolchain, toolchains

__all__ = ["FIXABLE", "FixOptions", "NewFile", "Manual", "Plan", "plan_fixes", "apply_plan"]


@dataclass(frozen=True)
class FixOptions:
    license: str | None = None  # default: what the manifest declares, else MIT
    owner: str | None = None  # GitHub user or organization, e.g. for CODEOWNERS
    author: str | None = None  # copyright holder
    email: str | None = None  # contact for conduct reports and security issues
    only: tuple[str, ...] = ()  # limit fixing to these check IDs


@dataclass(frozen=True)
class NewFile:
    path: str
    content: str
    check_id: str
    summary: str = ""  # shown next to the file name, e.g. "MIT, Copyright (c) 2026 Ada"
    review: str = ""  # something the maintainer should fill in or confirm


@dataclass(frozen=True)
class Manual:
    check_id: str
    title: str
    status: Status
    reason: str


@dataclass
class Plan:
    before: Report
    files: list[NewFile] = field(default_factory=list)
    manual: list[Manual] = field(default_factory=list)


@dataclass
class Context:
    repo: Repo
    name: str
    description: str | None
    slug: str | None  # "owner/repo" on GitHub
    owner: str | None
    author: str
    email: str | None
    licenses: tuple[str, ...]  # one, or several for dual licensing ("MIT OR Apache-2.0")
    declared: tuple[str, ...]  # bundled licenses the package manifest declares
    year: int
    branch: str
    tools: list[tuple[str, Toolchain]]
    will_exist: set[str]  # lower-case paths that exist or are about to be created

    def exists(self, path: str) -> bool:
        return path.lower() in self.will_exist


Fixer = Callable[[Context], Union[list[NewFile], str]]

# --------------------------------------------------------------------------- context

_GITHUB_REMOTE = re.compile(r"github\.com[:/]([\w.\-]+)/([\w.\-]+?)(?:\.git)?/?$")


def _toml_value(text: str, table: str, key: str) -> str | None:
    section = re.search(rf"^\[{re.escape(table)}\]\s*$(.*?)(?=^\[|\Z)", text, re.M | re.S)
    if not section:
        return None
    match = re.search(rf'^\s*{re.escape(key)}\s*=\s*"([^"]*)"', section.group(1), re.M)
    return match.group(1) if match else None


def _metadata(repo: Repo) -> tuple[str | None, str | None]:
    """(package name, one-line description) from the first manifest that has them."""
    for path, table in (("pyproject.toml", "project"), ("pyproject.toml", "tool.poetry"), ("Cargo.toml", "package")):
        real = repo.get(path)
        if real:
            text = repo.read_text(real)
            name = _toml_value(text, table, "name")
            if name:
                return name, _toml_value(text, table, "description")
    for path in ("package.json", "composer.json"):
        real = repo.get(path)
        if real:
            try:
                data = json.loads(repo.read_text(real))
            except ValueError:
                continue
            if isinstance(data, dict) and isinstance(data.get("name"), str):
                description = data.get("description")
                return data["name"], description if isinstance(description, str) else None
    gomod = repo.get("go.mod")
    if gomod:
        match = re.search(r"^module\s+(\S+)", repo.read_text(gomod), re.M)
        if match:
            return match.group(1), None
    return None, None


def _declared_bundled(repo: Repo) -> tuple[str, ...]:
    """Bundled licenses declared by the first manifest that declares any, in the order written."""
    declared, _, _ = declared_licenses(repo)
    for _, expression in declared:
        whole = canonical_ids(expression)
        if whole is not None and len(whole) > 1:
            return ()  # ambiguous, e.g. just "BSD"
        found = []
        for part in re.split(r"\s+(?:or|and)\s+|[/,;()]", expression, flags=re.IGNORECASE):
            spdx = bundled_id(part) if part.strip() else None
            if spdx and spdx not in found:
                found.append(spdx)
        if found:
            return tuple(found)
    return ()


def build_context(repo: Repo, options: FixOptions) -> Context:
    declared = _declared_bundled(repo)
    if options.license:
        spdx = bundled_id(options.license)
        if spdx is None:
            raise ValueError(f"unknown license {options.license!r}; choose one of: {', '.join(BUNDLED)}")
        licenses: tuple[str, ...] = (spdx,)
    else:
        licenses = declared or ("MIT",)
    name, description = _metadata(repo)
    remote = repo.git("remote", "get-url", "origin") or ""
    match = _GITHUB_REMOTE.search(remote)
    slug = f"{match.group(1)}/{match.group(2)}" if match else None
    owner = options.owner or (match.group(1) if match else None)
    if options.owner and not slug:
        slug = f"{options.owner}/{repo.root.name}"
    short_name = (name or repo.root.name).rsplit("/", 1)[-1]
    author = options.author or repo.git("config", "user.name") or owner or f"The {short_name} authors"
    email = options.email or repo.git("config", "user.email") or None
    branch = repo.git("symbolic-ref", "--short", "HEAD") or "main"
    return Context(
        repo=repo,
        name=name or repo.root.name,
        description=description,
        slug=slug,
        owner=owner,
        author=author,
        email=email,
        licenses=licenses,
        declared=declared,
        year=datetime.date.today().year,
        branch=branch,
        tools=toolchains(repo),
        will_exist={f.lower() for f in repo.files},
    )


# --------------------------------------------------------------------------- fixers


# Licenses whose text names the copyright holder.
_NAMES_HOLDER = frozenset({"MIT", "ISC", "BSD-2-Clause", "BSD-3-Clause"})


_DUAL_SUFFIX = {"Apache-2.0": "APACHE", "MIT": "MIT"}


def license_paths(ctx: Context) -> list[tuple[str, str]]:
    """(path, SPDX id) of the license files to create; Rust-style LICENSE-MIT/LICENSE-APACHE when dual."""
    if len(ctx.licenses) == 1:
        return [("LICENSE", ctx.licenses[0])]
    return [(f"LICENSE-{_DUAL_SUFFIX.get(spdx, spdx.upper())}", spdx) for spdx in ctx.licenses]


def fix_license(ctx: Context) -> list[NewFile]:
    files = []
    for path, spdx in license_paths(ctx):
        summary = f"{spdx}, Copyright (c) {ctx.year} {ctx.author}" if spdx in _NAMES_HOLDER else spdx
        notes = []
        if spdx == "LGPL-3.0":
            notes.append("LGPL-3.0 builds on the GPL: also add the GPL-3.0 text as COPYING")
        if ctx.declared and spdx not in ctx.declared:
            notes.append(f"your package manifest declares {' OR '.join(ctx.declared)}; make them match")
        files.append(NewFile(path, license_text(spdx, ctx.year, ctx.author), "license", summary, "; ".join(notes)))
    return files


def fix_code_of_conduct(ctx: Context) -> list[NewFile]:
    if ctx.email:
        contact, review = f"contact the maintainers privately at {ctx.email}", ""
    else:
        contact = "contact a project maintainer privately"
        review = "add an email address people can use to report conduct problems"
    content = t.fill(t.CODE_OF_CONDUCT, name=ctx.name, contact=contact)
    return [NewFile("CODE_OF_CONDUCT.md", content, "code-of-conduct", review=review)]


def fix_security_policy(ctx: Context) -> list[NewFile]:
    channels = []
    if ctx.slug:
        url = f"https://github.com/{ctx.slug}/security/advisories/new"
        channels.append(f'through GitHub\'s ["Report a vulnerability"]({url}) form')
    if ctx.email:
        channels.append(f"by email to {ctx.email}")
    if not channels:
        channels.append("by contacting a maintainer directly")
    review = (
        "turn on private vulnerability reporting in the repository's Security settings"
        if ctx.slug
        else ("say where to send reports (GitHub private reporting or an email address)")
    )
    content = t.fill(t.SECURITY, channel=" or ".join(channels))
    return [NewFile("SECURITY.md", content, "security-policy", review=review)]


def fix_changelog(ctx: Context) -> list[NewFile]:
    return [NewFile("CHANGELOG.md", t.CHANGELOG, "changelog")]


def fix_issue_templates(ctx: Context) -> list[NewFile]:
    files = [
        NewFile(".github/ISSUE_TEMPLATE/bug_report.yml", t.fill(t.BUG_REPORT, name=ctx.name), "issue-templates"),
        NewFile(".github/ISSUE_TEMPLATE/feature_request.yml", t.FEATURE_REQUEST, "issue-templates"),
    ]
    if ctx.slug:
        files.append(
            NewFile(".github/ISSUE_TEMPLATE/config.yml", t.fill(t.ISSUE_CONFIG, slug=ctx.slug), "issue-templates")
        )
    return files


def fix_pr_template(ctx: Context) -> list[NewFile]:
    commands = [c for _, tool in ctx.tools for c in (*tool.test, *tool.lint)]
    checks = "".join(f"- [ ] `{c}` passes\n" for c in commands)
    if ctx.exists("CHANGELOG.md"):
        checks += '- [ ] Entry added under "Unreleased" in `CHANGELOG.md`\n'
    content = t.fill(t.PULL_REQUEST, checks=checks)
    return [NewFile(".github/pull_request_template.md", content, "pr-template")]


def fix_codeowners(ctx: Context) -> list[NewFile] | str:
    if not ctx.owner:
        return "needs a GitHub username: pass --owner or add a GitHub `origin` remote"
    return [NewFile(".github/CODEOWNERS", t.fill(t.CODEOWNERS, owner=ctx.owner), "codeowners", summary=f"@{ctx.owner}")]


def fix_ci(ctx: Context) -> list[NewFile] | str:
    jobs = [(name, tool) for name, tool in ctx.tools if tool.ci_job]
    if not jobs:
        known = ", ".join(name for name, _ in ctx.tools)
        if known:
            return f"no CI template for {known} yet; add a workflow that builds and tests the project"
        return "couldn't tell how to build this project; add a workflow that runs its tests"
    content = t.fill(t.CI_HEADER, branch=ctx.branch) + "\n".join(tool.ci_job for _, tool in jobs)
    notes = "; ".join(note for _, tool in jobs for note in tool.notes)
    return [
        NewFile(
            ".github/workflows/ci.yml",
            content,
            "ci",
            summary=", ".join(name for name, _ in jobs),
            review=notes,
        )
    ]


def fix_dependency_updates(ctx: Context) -> list[NewFile] | str:
    ecosystems = [d.ecosystem.dependabot for d in ctx.repo.ecosystems if d.ecosystem.dependabot]
    if ctx.repo.get("Dockerfile"):
        ecosystems.append("docker")
    if ctx.repo.glob(".github/workflows/*.yml", ".github/workflows/*.yaml") or ctx.exists(".github/workflows/ci.yml"):
        ecosystems.append("github-actions")
    ecosystems = list(dict.fromkeys(ecosystems))
    if not ecosystems:
        return "no dependency manifests Dependabot understands"
    content = t.DEPENDABOT_HEADER + "".join(t.fill(t.DEPENDABOT_ENTRY, ecosystem=e) for e in ecosystems)
    return [NewFile(".github/dependabot.yml", content, "dependency-updates", summary=", ".join(ecosystems))]


def fix_gitignore(ctx: Context) -> list[NewFile]:
    sections = [t.GITIGNORE[d.key] for d in ctx.repo.ecosystems if d.key in t.GITIGNORE]
    content = "\n".join([*dict.fromkeys(sections), t.GITIGNORE_COMMON])
    names = [d.name for d in ctx.repo.ecosystems if d.key in t.GITIGNORE]
    return [NewFile(".gitignore", content, "gitignore", summary=", ".join(names))]


def fix_code_style(ctx: Context) -> list[NewFile]:
    return [NewFile(".editorconfig", t.EDITORCONFIG, "code-style")]


def _code_block(lines: list[str], lang: str = "bash") -> str:
    return f"```{lang}\n" + "\n".join(lines) + "\n```"


def fix_contributing(ctx: Context) -> list[NewFile]:
    clone = f"https://github.com/{ctx.slug}.git" if ctx.slug else "<repository-url>"
    folder = ctx.slug.split("/")[1] if ctx.slug else ctx.repo.root.name
    issues = f"[opening an issue](https://github.com/{ctx.slug}/issues)" if ctx.slug else "opening an issue"
    setup = [f"git clone {clone}", f"cd {folder}"] + [c for _, tool in ctx.tools for c in tool.setup]
    tests = [c for _, tool in ctx.tools for c in tool.test]
    lint = [c for _, tool in ctx.tools for c in tool.lint]
    parts = [
        f"# Contributing to {ctx.name}",
        f"Thanks for your interest in improving {ctx.name}! This guide explains how to get set up and how to "
        "propose changes.",
        "## Ways to contribute",
        f"- Report bugs and suggest features by {issues}.\n"
        "- Improve the documentation.\n"
        "- Fix bugs or build features. For anything large, please open an issue first so we can agree on the "
        "approach before you spend time on it.",
        "## Development setup",
        _code_block(setup),
    ]
    review = ""
    if tests:
        parts += ["## Running the tests", _code_block(tests)]
    else:
        review = "describe how to build and test the project"
        parts += ["## Running the tests", "Describe how to run the test suite here."]
    if lint:
        parts += ["## Linting and formatting", _code_block(lint)]
    parts += [
        "## Submitting a pull request",
        f"1. Fork the repository and create a branch from `{ctx.branch}`.\n"
        "2. Make your change, with tests for any new behaviour.\n"
        "3. Make sure the tests pass.\n"
        "4. Open a pull request that explains what you changed and why.",
    ]
    if ctx.exists("SECURITY.md"):
        parts += [
            "## Reporting security issues",
            "Please don't report security vulnerabilities in public issues. Follow [SECURITY.md](SECURITY.md) instead.",
        ]
    if ctx.exists("CODE_OF_CONDUCT.md"):
        parts += [
            "## Code of conduct",
            "This project follows a [Code of Conduct](CODE_OF_CONDUCT.md). By taking part you agree to abide by it.",
        ]
    if not ctx.slug:
        review = "; ".join(filter(None, [review, "replace <repository-url> with the clone URL"]))
    return [NewFile("CONTRIBUTING.md", "\n\n".join(parts) + "\n", "contributing", review=review)]


_INSTALL = {
    "python": "pip install {name}",
    "node": "npm install {name}",
    "rust": "cargo add {name}",
    "go": "go get {name}",
    "ruby": "gem install {name}",
    "php": "composer require {name}",
    "dotnet": "dotnet add package {name}",
    "dart": "dart pub add {name}",
}
_USAGE = {
    "python": ("python", "import {module}\n\n# Show the smallest useful example here."),
    "node": ("js", 'import {module} from "{name}";\n\n// Show the smallest useful example here.'),
    "rust": ("rust", "use {module};\n\n// Show the smallest useful example here."),
    "go": ("go", 'import "{name}"\n\n// Show the smallest useful example here.'),
}


def fix_readme(ctx: Context) -> list[NewFile]:
    keys = [d.key for d in ctx.repo.ecosystems]
    key = next((k for k in keys if k in _INSTALL), None)
    module = re.sub(r"[^\w]", "_", ctx.name.rsplit("/", 1)[-1])
    lines = [f"# {ctx.name.rsplit('/', 1)[-1]}", ""]
    if ctx.slug and ctx.exists(".github/workflows/ci.yml"):
        badge = f"https://github.com/{ctx.slug}/actions/workflows/ci.yml"
        lines += [f"[![CI]({badge}/badge.svg)]({badge})", ""]
    lines += [ctx.description or "One or two sentences about what this project does and who it is for.", ""]
    lines += ["## Installation", ""]
    if key:
        lines.append(_code_block([_INSTALL[key].format(name=ctx.name)]))
    elif ctx.slug:
        lines.append(_code_block([f"git clone https://github.com/{ctx.slug}.git"]))
    else:
        lines.append("Explain how to install or build the project.")
    lines += ["", "## Usage", ""]
    usage_key = next((k for k in keys if k in _USAGE), None)
    if usage_key:
        lang, example = _USAGE[usage_key]
        lines.append(_code_block([example.format(name=ctx.name, module=module)], lang))
    else:
        lines.append("Show the smallest useful example of using the project.")
    lines += ["", "## Contributing", ""]
    if ctx.exists("CONTRIBUTING.md"):
        lines.append("Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) to get started.")
    else:
        lines.append("Contributions are welcome! Please open an issue to discuss what you'd like to change.")
    existing = license_files(ctx.repo)
    planned = [(p, spdx) for p, spdx in license_paths(ctx) if ctx.exists(p)]
    if existing:
        label = identify_license(ctx.repo.read_text(existing[0]))
        links = [f"[{label}]({existing[0]})"] if label else []
    else:
        links = [f"[{spdx}]({p})" for p, spdx in planned]
    if existing or planned:
        lines += ["", "## License", ""]
        if links:
            lines.append(f"Released under the {' or '.join(links)} license{'s' if len(links) > 1 else ''}.")
        else:
            lines.append(f"See [{existing[0]}]({existing[0]}).")
    review = "write the description and a real usage example" if not ctx.description else "add a real usage example"
    return [NewFile("README.md", "\n".join(lines) + "\n", "readme", review=review)]


# Order matters: files that others link to (LICENSE, SECURITY.md, ...) are planned first, and the
# README last so it only links to files that will exist.
FIXERS: dict[str, Fixer] = {
    "license": fix_license,
    "code-of-conduct": fix_code_of_conduct,
    "security-policy": fix_security_policy,
    "changelog": fix_changelog,
    "gitignore": fix_gitignore,
    "code-style": fix_code_style,
    "ci": fix_ci,
    "dependency-updates": fix_dependency_updates,
    "issue-templates": fix_issue_templates,
    "pr-template": fix_pr_template,
    "codeowners": fix_codeowners,
    "contributing": fix_contributing,
    "readme": fix_readme,
}
FIXABLE = frozenset(FIXERS)


# --------------------------------------------------------------------------- planning and applying


def plan_fixes(root: str | os.PathLike[str] | Repo, options: FixOptions | None = None) -> Plan:
    """Work out which files to create, without touching the disk."""
    options = options or FixOptions()
    only = {i.strip().lower() for i in options.only if i.strip()}
    unknown = only - set(BY_ID)
    if unknown:
        raise ValueError(f"unknown check id(s): {', '.join(sorted(unknown))}")
    repo = root if isinstance(root, Repo) else Repo(root)
    report = run_checks(repo)
    ctx = build_context(repo, options)
    plan = Plan(before=report)

    failing = {r.id for r in report.results if r.status is Status.FAIL and (not only or r.id in only)}
    for check_id, fixer in FIXERS.items():
        if check_id not in failing:
            continue
        outcome = fixer(ctx)
        if isinstance(outcome, str):
            plan.manual.append(Manual(check_id, BY_ID[check_id].title, Status.FAIL, outcome))
            continue
        for new in outcome:
            if not ctx.exists(new.path):
                plan.files.append(new)
                ctx.will_exist.add(new.path.lower())

    handled = set(FIXERS) & failing
    for result in report.results:
        if result.status in (Status.FAIL, Status.WARN) and result.id not in handled and (not only or result.id in only):
            plan.manual.append(Manual(result.id, result.title, result.status, result.hint))
    order = {c: i for i, c in enumerate(BY_ID)}
    plan.manual.sort(key=lambda m: order[m.check_id])
    return plan


def apply_plan(plan: Plan, root: str | os.PathLike[str]) -> list[NewFile]:
    """Write the planned files. Files that appeared in the meantime are left alone."""
    written = []
    for new in plan.files:
        path = os.path.join(root, *new.path.split("/"))
        if os.path.exists(path):
            continue
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "x", encoding="utf-8", newline="\n") as handle:
            handle.write(new.content)
        written.append(new)
    return written
