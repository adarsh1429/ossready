"""Check repositories that live on GitHub, GitLab and other git hosts without cloning them by hand."""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .repo import Repo

_URL = re.compile(r"^(?:https?://|ssh://|git@|file://)", re.IGNORECASE)
_HOST_SHORTHAND = re.compile(
    r"^(?:www\.)?(?:github\.com|gitlab\.com|codeberg\.org|bitbucket\.org)/[\w.\-]+/[\w.\-]+(?:\.git)?/?$",
    re.IGNORECASE,
)
_GH_SHORTHAND = re.compile(r"^gh:([\w.\-]+/[\w.\-]+)$", re.IGNORECASE)


class RemoteError(RuntimeError):
    pass


def is_remote(target: str) -> bool:
    """True for URLs and host shorthands such as ``github.com/owner/repo`` or ``gh:owner/repo``."""
    return bool(_URL.match(target) or _HOST_SHORTHAND.match(target) or _GH_SHORTHAND.match(target))


def normalize_url(target: str) -> str:
    shorthand = _GH_SHORTHAND.match(target)
    if shorthand:
        return f"https://github.com/{shorthand.group(1)}"
    if _HOST_SHORTHAND.match(target):
        return "https://" + target.rstrip("/")
    return target


def _git(*args: str, timeout: int = 300) -> str:
    if shutil.which("git") is None:
        raise RemoteError("checking a remote repository needs git installed")
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        proc = subprocess.run(["git", *args], capture_output=True, timeout=timeout, check=False, env=env)
    except subprocess.TimeoutExpired as exc:
        raise RemoteError(f"git {args[0]} timed out after {timeout} seconds") from exc
    if proc.returncode != 0:
        message = proc.stderr.decode("utf-8", errors="replace").strip().splitlines()
        raise RemoteError(message[-1] if message else f"git {args[0]} failed")
    return proc.stdout.decode("utf-8", errors="replace")


def remote_tags(url: str) -> list[str]:
    out = _git("ls-remote", "--tags", "--refs", url, timeout=120)
    return [line.split("refs/tags/", 1)[1] for line in out.splitlines() if "refs/tags/" in line]


def _force_remove(func, path, _exc):  # pragma: no cover - Windows read-only git objects
    os.chmod(path, stat.S_IWRITE)
    func(path)


def _rmtree(path: str) -> None:
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_force_remove)
    else:  # pragma: no cover
        shutil.rmtree(path, onerror=_force_remove)


@contextmanager
def checkout(target: str) -> Iterator[Repo]:
    """Shallow-clone ``target`` into a temporary folder and yield it as a :class:`Repo`."""
    url = normalize_url(target)
    tmp = tempfile.mkdtemp(prefix="ossready-")
    try:
        dest = Path(tmp) / "repo"
        try:
            _git("clone", "--depth", "1", "--quiet", "--", url, str(dest))
        except RemoteError as exc:
            if re.search(r"could not read username|repository not found|not found", str(exc), re.IGNORECASE):
                raise RemoteError(f"could not clone {url}: the repository doesn't exist or is private") from exc
            raise RemoteError(f"could not clone {url}: {exc}") from exc
        repo = Repo(dest, display=url)
        repo.tags = remote_tags(url)
        yield repo
    finally:
        _rmtree(tmp)
