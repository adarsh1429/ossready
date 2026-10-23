"""README, license and contributor documentation checks."""

from __future__ import annotations

import posixpath
import re
from urllib.parse import unquote

from ..licenses import declared_licenses, identified_licenses, license_files, parse_expression
from ..model import Outcome, Status
from ..repo import Repo
from ._util import plural, shorten

# --------------------------------------------------------------------------- README

_ATX_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", re.MULTILINE)
_UNDERLINED_HEADING = re.compile(r"^([^\n]*\S[^\n]*)\n([=\-~^*+#\"'`])\2{2,}\s*$", re.MULTILINE)
_INSTALL_COMMAND = re.compile(
    r"\b(?:pip|pipx|uv|poetry|npm|pnpm|yarn|bun|cargo|go|gem|brew|apt|apt-get|composer|dotnet|conda|dart pub)"
    r"\s+(?:install|add|get|require)\b",
    re.IGNORECASE,
)
_INSTALL_WORDS = ("install", "getting started", "get started", "setup", "set up", "quick start", "quickstart")
_USAGE_WORDS = ("usage", "example", "getting started", "quick start", "quickstart", "how to", "tutorial", "use")


def check_readme(repo: Repo) -> Outcome:
    path = repo.find_doc("readme")
    if path is None:
        return Status.FAIL, "No README found"
    text = repo.read_text(path)
    length = len(text.strip())
    if length < 200:
        return Status.WARN, f"{path} is very short ({length} characters)"
    headings = [h.lower() for h in _ATX_HEADING.findall(text)]
    headings += [h.lower() for h, _ in _UNDERLINED_HEADING.findall(text)]
    has_install = any(w in h for h in headings for w in _INSTALL_WORDS) or bool(_INSTALL_COMMAND.search(text))
    has_usage = any(w in h for h in headings for w in _USAGE_WORDS) or "```" in text or "::\n" in text
    missing = [name for name, ok in (("installation", has_install), ("usage", has_usage)) if not ok]
    if missing:
        return Status.WARN, f"{path} has no {' or '.join(missing)} section"
    return Status.PASS, f"{path} covers installation and usage"


# --------------------------------------------------------------------------- README links

_FENCED_CODE = re.compile(r"^\s{0,3}(`{3,}|~{3,}).*?^\s{0,3}\1\s*$", re.MULTILINE | re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`\n]+`")
_MD_LINK = re.compile(r"\]\(\s*<?([^)\s>]+)>?(?:\s+[\"'(][^)]*[\"')])?\s*\)")
_REF_LINK = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*<?(\S+?)>?(?:\s+.*)?$", re.MULTILINE)
_HTML_LINK = re.compile(r"""<(?:a|img|source|video)\b[^>]*?\s(?:href|src)\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
_SCHEME = re.compile(r"^[a-z][a-z0-9+.\-]*:", re.IGNORECASE)


def relative_links(text: str) -> list[str]:
    """Relative link and image targets in Markdown/HTML, ignoring code blocks."""
    text = _INLINE_CODE.sub("", _FENCED_CODE.sub("", text))
    targets = _MD_LINK.findall(text) + _REF_LINK.findall(text) + _HTML_LINK.findall(text)
    return [t for t in targets if not (_SCHEME.match(t) or t.startswith(("#", "//", "{{")))]


def broken_links(repo: Repo, source: str) -> tuple[int, list[str]]:
    """Return (number of relative links checked, targets that don't exist) for one document."""
    base = posixpath.dirname(source)
    files = set(repo.files)
    directories = {posixpath.dirname(f) for f in files}
    directories |= {d for f in directories for d in _parents(f)}
    checked, broken = 0, []
    for target in relative_links(repo.read_text(source)):
        path = unquote(target.split("#", 1)[0].split("?", 1)[0])
        if not path:
            continue
        resolved = posixpath.normpath(path.lstrip("/") if path.startswith("/") else posixpath.join(base, path))
        if resolved.startswith("..") or resolved == ".":
            continue  # points outside the repository, e.g. ../../issues on GitHub
        checked += 1
        if resolved not in files and resolved.rstrip("/") not in directories:
            broken.append(target)
    return checked, broken


def _parents(path: str) -> list[str]:
    parts = path.split("/")
    return ["/".join(parts[:i]) for i in range(1, len(parts))]


def check_readme_links(repo: Repo) -> Outcome:
    path = repo.find_doc("readme")
    if path is None:
        return Status.SKIP, "No README to check"
    checked, broken = broken_links(repo, path)
    if broken:
        return Status.FAIL, f"{plural(len(broken), 'broken link')} in {path}: {shorten(broken)}"
    if not checked:
        return Status.PASS, f"No relative links in {path}"
    return Status.PASS, f"All {plural(checked, 'relative link')} in {path} resolve"


# --------------------------------------------------------------------------- license


def check_license(repo: Repo) -> Outcome:
    candidates = license_files(repo)
    if not candidates:
        return Status.FAIL, "No LICENSE file found"
    found = identified_licenses(repo)
    if not found:
        return Status.WARN, f"Could not recognise the license in {', '.join(candidates)}"
    return Status.PASS, ", ".join(f"{spdx} ({path})" for path, spdx in found.items())


def check_license_consistency(repo: Repo) -> Outcome:
    in_files = set(identified_licenses(repo).values())
    if not in_files:
        return Status.SKIP, "No recognised LICENSE file to compare against"
    declared, silent, pointing = declared_licenses(repo)
    if not declared and not silent:
        if pointing:
            return Status.PASS, f"{', '.join(pointing)} refer{'s' if len(pointing) == 1 else ''} to the license file"
        return Status.SKIP, "No package manifest with a license field"
    mismatches, unclear = [], []
    for manifest, expression in declared:
        ids, unknown = parse_expression(expression)
        if ids and not ids & in_files:
            mismatches.append(f"{manifest} says {expression!r}")
        elif not ids:
            unclear.append(f"{manifest} ({expression!r})")
    license_names = "/".join(sorted(in_files))
    if mismatches:
        return Status.FAIL, f"LICENSE is {license_names} but {', '.join(mismatches)}"
    problems = []
    if silent:
        spdx = sorted(in_files)[0]
        suggestions = [f"{path} ({_license_field(path, spdx)})" for path in silent]
        problems.append(f"No license declared in {', '.join(suggestions)}")
    if unclear:
        problems.append(f"Could not interpret the license in {', '.join(unclear)}")
    if problems:
        return Status.WARN, "; ".join(problems)
    return Status.PASS, f"{license_names} in LICENSE and {', '.join(m for m, _ in declared)}"


def _license_field(path: str, spdx: str) -> str:
    """How to declare ``spdx`` in the manifest at ``path``."""
    name = path.lower()
    if name in ("pyproject.toml", "cargo.toml"):
        table = "[project]" if name == "pyproject.toml" else "[package]"
        return f'add license = "{spdx}" under {table}'
    if name in ("package.json", "composer.json"):
        return f'add "license": "{spdx}"'
    if name == "setup.cfg":
        return f"add license = {spdx} under [metadata]"
    if name == "setup.py":
        return f'pass license="{spdx}" to setup()'
    if name.endswith(".gemspec"):
        return f'add spec.license = "{spdx}"'
    if name == "mix.exs":
        return f'add licenses: ["{spdx}"] to package'
    if name.endswith(".csproj"):
        return f"add <PackageLicenseExpression>{spdx}</PackageLicenseExpression>"
    return f"declare {spdx}"


# --------------------------------------------------------------------------- changelog

_CHANGELOG_STEMS = ("changelog", "changes", "history", "news")
_VERSION_HEADING = re.compile(
    r"^\s{0,3}#{1,3}\s*(?:version\s+)?\[?v?(\d+\.\d+(?:\.\d+)?(?:[-+.][\w.]+)?)\]?", re.MULTILINE | re.IGNORECASE
)
_RST_VERSION_HEADING = re.compile(
    r"^(?:version\s+)?v?(\d+\.\d+(?:\.\d+)?)\b[^\n]*\n[=\-~^]{3,}\s*$", re.MULTILINE | re.IGNORECASE
)


def changelog_versions(repo: Repo) -> list[str]:
    """Released versions listed in the changelog, newest first as written."""
    path = repo.find_doc(*_CHANGELOG_STEMS)
    if path is None:
        return []
    text = repo.read_text(path)
    return _VERSION_HEADING.findall(text) + _RST_VERSION_HEADING.findall(text)
