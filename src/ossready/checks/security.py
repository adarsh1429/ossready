"""Leaked credentials and risky GitHub Actions workflows."""

from __future__ import annotations

import os
import re

from ..model import Outcome, Status
from ..repo import Repo
from ._util import plural, shorten

# --------------------------------------------------------------------------- secrets

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private key", re.compile(r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY(?: BLOCK)?-----")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{82})\b")),
    ("GitLab token", re.compile(r"\bglpat-[A-Za-z0-9_\-]{20}\b")),
    ("Slack token", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}")),
    ("Slack webhook", re.compile(r"https://hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/[A-Za-z0-9]{20,}")),
    ("Stripe live key", re.compile(r"\b[rs]k_live_[A-Za-z0-9]{24,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("npm token", re.compile(r"\bnpm_[A-Za-z0-9]{36}\b")),
    ("PyPI token", re.compile(r"\bpypi-AgEIcHlwaS5vcmc[A-Za-z0-9_\-]{50,}")),
    ("AI provider API key", re.compile(r"\bsk-(?:proj-|ant-[a-z0-9]+-)?[A-Za-z0-9_\-]{32,}")),
    ("Hugging Face token", re.compile(r"\bhf_[A-Za-z0-9]{34,}\b")),
    ("SendGrid key", re.compile(r"\bSG\.[A-Za-z0-9_\-]{22}\.[A-Za-z0-9_\-]{43}\b")),
    ("Twilio key", re.compile(r"\bSK[0-9a-f]{32}\b")),
)

_SENSITIVE_NAMES = re.compile(
    r"^(?:\.env(?:\.(?!example$|sample$|template$|dist$|defaults$|schema$)[^/]+)?"
    r"|id_(?:rsa|dsa|ecdsa|ed25519)|\.pypirc|\.netrc|\.htpasswd|credentials\.json|service[-_]account.*\.json"
    r"|.+\.(?:p12|pfx|jks|keystore|ppk|kdbx))$",
    re.IGNORECASE,
)

BINARY_EXTENSIONS = frozenset(
    ".png .jpg .jpeg .gif .webp .ico .bmp .tiff .svgz .pdf .zip .gz .tgz .bz2 .xz .7z .rar .jar .war "
    ".whl .egg .so .dylib .dll .exe .bin .o .a .class .pyc .woff .woff2 .ttf .otf .eot .mp3 .mp4 .mov "
    ".avi .webm .wav .flac .ogg .psd .sqlite .db .parquet .npy .npz .pt .onnx .h5 .lock".split()
)
_MAX_SCAN_BYTES = 512_000
_MAX_SCAN_FILES = 10_000
# Test suites ship dummy keys and docs show example ones, so findings there only warn.
_LOW_RISK_DIRS = frozenset(
    {"test", "tests", "testing", "testdata", "fixtures", "__fixtures__", "__tests__", "spec", "docs", "doc", "examples"}
)
_DOC_EXTENSIONS = frozenset({".md", ".mdx", ".rst", ".adoc"})
# A real PEM key has long base64 lines right after its header; examples usually show "..." instead.
_KEY_BODY = re.compile(r"[A-Za-z0-9+/=]{40,}")


def _low_risk(path: str) -> bool:
    parts = path.split("/")
    return any(part.lower() in _LOW_RISK_DIRS for part in parts[:-1]) or (
        os.path.splitext(parts[-1])[1].lower() in _DOC_EXTENSIONS
    )


def _in_fixture_dir(path: str) -> bool:
    return any(part.lower() in _LOW_RISK_DIRS for part in path.split("/")[:-1])


def find_secrets(repo: Repo) -> tuple[list[tuple[str, int, str]], list[str]]:
    """Return (leaks as (path, line, kind), files whose names suggest credentials)."""
    sensitive = [f for f in repo.files if _SENSITIVE_NAMES.match(f.rpartition("/")[2])]
    leaks: list[tuple[str, int, str]] = []
    scanned = 0
    for path in repo.files:
        if scanned >= _MAX_SCAN_FILES:
            break
        if os.path.splitext(path)[1].lower() in BINARY_EXTENSIONS or repo.size(path) > _MAX_SCAN_BYTES:
            continue
        try:
            raw = (repo.root / path).read_bytes()
        except OSError:
            continue
        if b"\0" in raw[:8192]:
            continue
        scanned += 1
        text = raw.decode("utf-8", errors="replace")
        for kind, pattern in SECRET_PATTERNS:
            for match in pattern.finditer(text):
                if match.group(0).endswith("EXAMPLE"):
                    continue  # documentation placeholders such as AWS's sample keys
                if kind == "private key" and not _KEY_BODY.search(text, match.end(), match.end() + 400):
                    continue  # a header without key material, e.g. in an explanation
                line = text.count("\n", 0, match.start()) + 1
                leaks.append((path, line, kind))
    return leaks, sensitive


def check_secrets(repo: Repo) -> Outcome:
    leaks, sensitive = find_secrets(repo)
    real = [f"{p}:{n} ({k})" for p, n, k in leaks if not _low_risk(p)]
    if real:
        return Status.FAIL, f"Possible secrets committed: {shorten(real)}"
    notes = []
    examples = [f"{p}:{n} ({k})" for p, n, k in leaks]
    if examples:
        notes.append(f"Keys or tokens in tests or docs, check they are dummies: {shorten(examples)}")
    sensitive = [f for f in sensitive if not _in_fixture_dir(f)]
    if sensitive:
        notes.append(f"Files that often hold credentials: {shorten(sensitive)}")
    if notes:
        return Status.WARN, "; ".join(notes)
    return Status.PASS, "No secrets or credential files detected"


# --------------------------------------------------------------------------- workflow security

# Event fields an attacker controls (title, body, branch name, ...). Interpolating them straight into a
# shell script lets anyone who opens an issue or PR run commands in your CI.
# See https://securitylab.github.com/resources/github-actions-untrusted-input/
_UNTRUSTED = re.compile(
    r"\$\{\{[^}]*\b(?:github\.event\.(?:issue\.(?:title|body)|pull_request\.(?:title|body|head\.ref|head\.label"
    r"|head\.repo\.default_branch)|comment\.body|review\.body|review_comment\.body|discussion\.(?:title|body)"
    r"|pages\.[^}]*\.page_name|commits\.[^}]*\.(?:message|author\.(?:email|name))"
    r"|head_commit\.(?:message|author\.(?:email|name)))|github\.head_ref)\b[^}]*\}\}"
)
_RUN_KEY = re.compile(r"^(\s*)(?:-\s+)?run:\s*(.*)$")
_PR_TARGET = re.compile(r"\bpull_request_target\b")
_CHECKOUT_PR_HEAD = re.compile(
    r"ref:\s*\$\{\{\s*(?:github\.event\.pull_request\.head\.(?:sha|ref)|github\.head_ref)\s*\}\}"
)
_PERMISSIONS = re.compile(r"^\s*permissions:", re.MULTILINE)


def injection_lines(text: str) -> list[int]:
    """Line numbers where untrusted event data is interpolated into a ``run:`` script."""
    found = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        match = _RUN_KEY.match(lines[i])
        if not match:
            i += 1
            continue
        indent, inline = len(match.group(1)), match.group(2)
        if _UNTRUSTED.search(inline):
            found.append(i + 1)
        i += 1
        if inline.strip()[:1] in ("|", ">"):
            # A block scalar: every following line indented deeper belongs to the script.
            while i < len(lines) and (not lines[i].strip() or len(lines[i]) - len(lines[i].lstrip()) > indent):
                if _UNTRUSTED.search(lines[i]):
                    found.append(i + 1)
                i += 1
    return found


def check_workflow_security(repo: Repo) -> Outcome:
    workflows = repo.glob(".github/workflows/*.yml", ".github/workflows/*.yaml")
    if not workflows:
        return Status.SKIP, "No GitHub Actions workflows"
    critical, unscoped = [], []
    for path in workflows:
        text = repo.read_text(path, limit=300_000)
        critical += [f"{path}:{line} (untrusted input in run)" for line in injection_lines(text)]
        if _PR_TARGET.search(text) and _CHECKOUT_PR_HEAD.search(text):
            critical.append(f"{path} (pull_request_target checks out PR code)")
        if not _PERMISSIONS.search(text):
            unscoped.append(path)
    if critical:
        return Status.FAIL, f"Exploitable workflow patterns: {shorten(critical)}"
    if unscoped:
        return Status.WARN, f"No `permissions:` block, so the token gets default rights: {shorten(unscoped)}"
    return Status.PASS, f"{plural(len(workflows), 'workflow')} with scoped permissions and no risky patterns"
