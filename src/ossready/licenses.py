"""Recognise license texts, read the license a package declares, and render bundled license texts."""

from __future__ import annotations

import fnmatch
import json
import re
from importlib import resources
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .repo import Repo

# --------------------------------------------------------------------------- recognising LICENSE files

# Order matters: AGPL and LGPL texts mention the GPL, and BSD-3 contains BSD-2.
_SIGNATURES: tuple[tuple[str, str], ...] = (
    ("AGPL-3.0", r"gnu affero general public license version 3"),
    ("LGPL-3.0", r"gnu lesser general public license version 3"),
    ("LGPL-2.1", r"gnu lesser general public license version 2\.1"),
    ("GPL-3.0", r"gnu general public license version 3"),
    ("GPL-2.0", r"gnu general public license version 2"),
    ("Apache-2.0", r"apache license,? version 2\.0"),
    ("MPL-2.0", r"mozilla public license,? (?:version|v\.?) ?2\.0"),
    ("EPL-2.0", r"eclipse public license - v ?2\.0"),
    ("BSL-1.0", r"boost software license"),
    ("BSD-3-Clause", r"redistributions in binary form must reproduce.*neither the name of"),
    ("BSD-2-Clause", r"redistributions in binary form must reproduce"),
    ("ISC", r"permission to use, copy, modify, and/or distribute this software for any purpose"),
    ("MIT", r"permission is hereby granted, free of charge"),
    ("Unlicense", r"this is free and unencumbered software released into the public domain"),
    ("CC0-1.0", r"cc0 1\.0 universal"),
    ("Zlib", r"this software is provided 'as-is', without any express or implied warranty"),
)

KNOWN_IDS = tuple(spdx for spdx, _ in _SIGNATURES)

_LICENSE_FILE = re.compile(r"^(?:licen[cs]e|copying|unlicense)(?:[.\-_].*)?$", re.IGNORECASE)


def identify_license(text: str) -> str | None:
    """Return the SPDX id of a common license text, or None."""
    normalized = " ".join(text.lower().split())
    for spdx, pattern in _SIGNATURES:
        if re.search(pattern, normalized):
            return spdx
    return None


def license_files(repo: Repo) -> list[str]:
    """LICENSE-like files at the root, plus files in a REUSE-style LICENSES/ folder."""
    files = [f for f in repo.files if "/" not in f and _LICENSE_FILE.match(f)]
    files += [f for f in repo.under("LICENSES") if f.count("/") == 1]
    return files


def identified_licenses(repo: Repo) -> dict[str, str]:
    """Map each license file to the SPDX id of its text (unrecognised files are left out)."""
    found = {}
    for path in license_files(repo):
        spdx = identify_license(repo.read_text(path, limit=200_000))
        if spdx:
            found[path] = spdx
    return found


# --------------------------------------------------------------------------- licenses declared in manifests

# Manifests that have a license field. Their absence of a declaration is worth a warning.
LICENSE_FIELD_MANIFESTS = (
    "pyproject.toml",
    "setup.cfg",
    "setup.py",
    "package.json",
    "cargo.toml",
    "composer.json",
    "*.gemspec",
    "mix.exs",
    "*.csproj",
    "pom.xml",
)

_TOML_LICENSE = re.compile(r'^\s*license\s*=\s*"([^"]+)"', re.MULTILINE)
_TOML_LICENSE_TEXT = re.compile(r'^\s*license\s*=\s*\{[^}\n]*\btext\s*=\s*"([^"]+)"', re.MULTILINE)
_TOML_LICENSE_FILE = re.compile(r"^\s*license(?:-files?|\s*=\s*\{[^}\n]*\bfile)\b", re.MULTILINE)
_CLASSIFIER = re.compile(r"License :: (?:OSI Approved :: )?([^\"'\n]+?)\s*[\"']")
_CFG_LICENSE = re.compile(r"^\s*license\s*=\s*(.+?)\s*$", re.MULTILINE)
_PY_LICENSE = re.compile(r"""\blicense\s*=\s*["']([^"']+)["']""")
_GEMSPEC_LICENSE = re.compile(r"""\.licenses?\s*=\s*\[?\s*["']([^"']+)["']""")
_MIX_LICENSE = re.compile(r"""licenses:\s*\[\s*["']([^"']+)["']""")
_CSPROJ_LICENSE = re.compile(r"<PackageLicenseExpression>\s*([^<]+?)\s*</PackageLicenseExpression>")
_POM_LICENSE = re.compile(r"<license>\s*<name>\s*([^<]+?)\s*</name>")


def declared_licenses(repo: Repo) -> tuple[list[tuple[str, str]], list[str], list[str]]:
    """Return ([(manifest, declared license)], [manifests that declare none], [manifests that point at a file]).

    Manifests that can't carry a license (a pyproject.toml that only configures tools, a Cargo
    workspace root, a private package.json) are ignored, and so is a silent manifest when another
    manifest of the same ecosystem declares the license (e.g. a setup.py shim next to pyproject.toml).
    """
    declared: list[tuple[str, str]] = []
    silent: list[str] = []
    pointing: list[str] = []
    for path in [f for f in repo.files if "/" not in f]:
        lower = path.lower()
        if not any(_glob(lower, pattern) for pattern in LICENSE_FIELD_MANIFESTS):
            continue
        text = repo.read_text(path, limit=500_000)
        if not _can_declare(lower, text):
            continue
        values, points_to_file = _extract(lower, text)
        if values:
            declared.extend((path, v) for v in values)
        elif points_to_file:
            pointing.append(path)
        else:
            silent.append(path)
    covered = {_family(p) for p, _ in declared} | {_family(p) for p in pointing}
    silent = [p for p in silent if _family(p) not in covered]
    return declared, silent, pointing


def _family(path: str) -> str:
    name = path.lower()
    if name in ("pyproject.toml", "setup.cfg", "setup.py"):
        return "python"
    return name.rsplit(".", 1)[-1] if name.endswith((".gemspec", ".csproj")) else name


def _can_declare(name: str, text: str) -> bool:
    if name == "pyproject.toml":
        return bool(re.search(r"^\[(?:project|tool\.poetry)\]", text, re.MULTILINE))
    if name == "cargo.toml":
        return bool(re.search(r"^\[package\]", text, re.MULTILINE))
    if name == "package.json":
        try:
            data = json.loads(text)
        except ValueError:
            return False
        return isinstance(data, dict) and data.get("private") is not True
    return True


def _glob(name: str, pattern: str) -> bool:
    return fnmatch.fnmatchcase(name, pattern)


def _extract(name: str, text: str) -> tuple[list[str], bool]:
    """Licenses declared in one manifest, and whether it simply points at a license file."""
    if name in ("pyproject.toml", "cargo.toml"):
        values = _TOML_LICENSE.findall(text) + _TOML_LICENSE_TEXT.findall(text)
        if name == "pyproject.toml" and not values:
            values = _CLASSIFIER.findall(text)
        return values[:1], bool(_TOML_LICENSE_FILE.search(text))
    if name == "setup.cfg":
        match = _CFG_LICENSE.search(text)
        values = [match.group(1)] if match and not match.group(1).startswith("file:") else []
        return values or _CLASSIFIER.findall(text)[:1], bool(match and match.group(1).startswith("file:"))
    if name == "setup.py":
        return (_PY_LICENSE.findall(text) or _CLASSIFIER.findall(text))[:1], False
    if name in ("package.json", "composer.json"):
        try:
            data = json.loads(text)
        except ValueError:
            return [], False
        if not isinstance(data, dict):
            return [], False
        value = data.get("license") or data.get("licenses")
        if isinstance(value, dict):
            value = value.get("type")
        if isinstance(value, list):
            value = [v.get("type") if isinstance(v, dict) else v for v in value]
            value = " OR ".join(v for v in value if isinstance(v, str))
        if isinstance(value, str) and value.upper().startswith("SEE LICENSE IN"):
            return [], True
        return ([value] if isinstance(value, str) and value else []), False
    if name.endswith(".gemspec"):
        return _GEMSPEC_LICENSE.findall(text)[:1], False
    if name == "mix.exs":
        return _MIX_LICENSE.findall(text)[:1], False
    if name.endswith(".csproj"):
        return _CSPROJ_LICENSE.findall(text)[:1], "<PackageLicenseFile>" in text
    if name == "pom.xml":
        return _POM_LICENSE.findall(text)[:1], False
    return [], False


# --------------------------------------------------------------------------- normalising license names

_ALIASES: dict[str, tuple[str, ...]] = {
    "MIT": ("mit", "expat", "mitx11"),
    "Apache-2.0": ("apache20", "apache2", "apachev2", "apache", "asl20", "asl2", "apl20"),
    "BSD-2-Clause": ("bsd2clause", "bsd2", "simplifiedbsd", "freebsd", "bsd2clausesimplified"),
    "BSD-3-Clause": ("bsd3clause", "bsd3", "newbsd", "revisedbsd", "modifiedbsd", "bsd3clausenewbsd"),
    "ISC": ("isc", "isclicense"),
    "MPL-2.0": ("mpl20", "mpl2", "mozillapublic20", "mozillapublicv2", "mozillapublic"),
    "GPL-3.0": ("gpl30", "gplv3", "gpl3", "gnugplv3", "gnugpl3", "gnugeneralpublicv3", "gnugeneralpublic3"),
    "GPL-2.0": ("gpl20", "gplv2", "gpl2", "gnugplv2", "gnugpl2", "gnugeneralpublicv2", "gnugeneralpublic2"),
    "LGPL-3.0": ("lgpl30", "lgplv3", "lgpl3", "gnulgplv3", "gnulessergeneralpublicv3", "gnulessergeneralpublic3"),
    "LGPL-2.1": ("lgpl21", "lgplv21", "lgplv2", "gnulessergeneralpublicv21", "gnulessergeneralpublicv2"),
    "AGPL-3.0": ("agpl30", "agplv3", "agpl3", "gnuagplv3", "gnuafferogeneralpublicv3", "gnuafferogeneralpublic3"),
    "Unlicense": ("unlicense",),
    "CC0-1.0": ("cc010", "cc0", "cc0universal", "cc010universal"),
    "BSL-1.0": ("bsl10", "boost", "boost10"),
    "Zlib": ("zlib",),
    "EPL-2.0": ("epl20", "eclipsepublic20", "eclipsepublicv20"),
}
# Names that could mean more than one license.
_AMBIGUOUS: dict[str, frozenset[str]] = {
    "bsd": frozenset({"BSD-2-Clause", "BSD-3-Clause"}),
    "gpl": frozenset({"GPL-2.0", "GPL-3.0"}),
    "gnugeneralpublic": frozenset({"GPL-2.0", "GPL-3.0"}),
    "lgpl": frozenset({"LGPL-2.1", "LGPL-3.0"}),
    "gnulessergeneralpublic": frozenset({"LGPL-2.1", "LGPL-3.0"}),
}
_LOOKUP: dict[str, frozenset[str]] = {
    alias: frozenset({spdx}) for spdx, aliases in _ALIASES.items() for alias in aliases
} | _AMBIGUOUS

_NOISE = re.compile(r"\b(?:the|licen[cs]e|version|software|osi|approved)\b|-only\b|-or-later\b|\+")
_SPLIT = re.compile(r"\s+(?:or|and)\s+|[/,;]", re.IGNORECASE)
_EXCEPTION = re.compile(r"\s+with\s+[\w.\-]+", re.IGNORECASE)


def _compact(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _NOISE.sub(" ", name.lower()))


def canonical_ids(name: str) -> frozenset[str] | None:
    """Map one license name ("Apache License 2.0", "GPLv3+", "MIT License") to SPDX ids, or None."""
    name = name.split("::")[-1].strip()
    candidates = [name, re.sub(r"\([^)]*\)", " ", name)] + re.findall(r"\(([^)]*)\)", name)
    for candidate in candidates:
        ids = _LOOKUP.get(_compact(candidate))
        if ids:
            return ids
    return None


def parse_expression(expression: str) -> tuple[frozenset[str], list[str]]:
    """Split a license expression into (recognised SPDX ids, unrecognised parts)."""
    expression = _EXCEPTION.sub("", expression)
    whole = canonical_ids(expression)
    if whole:
        return whole, []
    ids: set[str] = set()
    unknown: list[str] = []
    for part in _SPLIT.split(expression.replace("(", " ").replace(")", " ")):
        part = part.strip()
        if not part:
            continue
        found = canonical_ids(part)
        if found:
            ids |= found
        else:
            unknown.append(part)
    return frozenset(ids), unknown


# --------------------------------------------------------------------------- bundled license texts

# Texts come from https://github.com/github/choosealicense.com, the same ones GitHub offers when you
# create a repository, so GitHub recognises them.
BUNDLED = (
    "MIT",
    "Apache-2.0",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "ISC",
    "MPL-2.0",
    "GPL-3.0",
    "LGPL-3.0",
    "AGPL-3.0",
    "Unlicense",
)


def bundled_id(name: str) -> str | None:
    """Resolve a user-supplied license name to one of the BUNDLED ids."""
    for spdx in BUNDLED:
        if spdx.lower() == name.strip().lower():
            return spdx
    ids = canonical_ids(name)
    if ids and len(ids) == 1:
        (spdx,) = ids
        return spdx if spdx in BUNDLED else None
    return None


def license_text(spdx: str, year: int | str, holder: str) -> str:
    """The full text of a bundled license with the year and copyright holder filled in."""
    if spdx not in BUNDLED:
        raise ValueError(f"no bundled text for {spdx}; choose one of: {', '.join(BUNDLED)}")
    text = resources.files("ossready").joinpath("licenses").joinpath(f"{spdx}.txt").read_text(encoding="utf-8")
    return text.replace("[year]", str(year)).replace("[fullname]", holder)
