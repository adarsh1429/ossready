"""A read-only view of the files in a repository."""

from __future__ import annotations

import fnmatch
import os
import shutil
import subprocess
from functools import cached_property
from pathlib import Path

from .ecosystems import Detected, detect

# Directories that never hold project files worth checking.
SKIP_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".tox",
        ".nox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".eggs",
        "dist",
        "build",
        "target",
        ".idea",
        ".vscode",
    }
)

# Where community health files usually live, in GitHub's lookup order.
DOC_DIRS = ("", ".github", "docs")

MAX_FILES = 50_000


def run_git(*args: str, cwd: str | os.PathLike[str] | None = None, timeout: int = 30) -> str | None:
    """Run git and return its stdout, or None if git is missing or the command fails."""
    if shutil.which("git") is None:
        return None
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, timeout=timeout, check=False, env=env)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", errors="surrogateescape")


class Repo:
    """Lists a repository's files once and answers questions about them.

    Paths are relative, use forward slashes and keep their original case.
    Inside a git work tree only tracked and not-ignored files are listed, so
    anything covered by ``.gitignore`` is treated as not part of the project.
    """

    def __init__(self, root: str | os.PathLike[str], display: str | None = None) -> None:
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise NotADirectoryError(f"not a directory: {self.root}")
        self.display = display or str(self.root)
        self.uses_git = False
        self.files: list[str] = sorted(self._list_files())
        self._by_lower = {path.lower(): path for path in self.files}
        self._tags: list[str] | None = None
        self._tags_loaded = False

    # ------------------------------------------------------------------ listing

    def _list_files(self) -> list[str]:
        listed = self._git_files()
        # An empty listing usually means the folder is ignored by an enclosing repository.
        if listed:
            self.uses_git = True
            return listed
        return self._walk()

    def _git_files(self) -> list[str] | None:
        out = run_git("-C", str(self.root), "ls-files", "-z", "--cached", "--others", "--exclude-standard")
        if out is None:
            return None
        files = []
        for rel in out.split("\0"):
            if rel and self._inside(rel):
                files.append(rel)
                if len(files) >= MAX_FILES:
                    break
        return files

    def _walk(self) -> list[str]:
        files: list[str] = []
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
            rel_dir = os.path.relpath(dirpath, self.root)
            for name in sorted(filenames):
                rel = (name if rel_dir == "." else f"{rel_dir}/{name}").replace(os.sep, "/")
                if self._inside(rel):
                    files.append(rel)
                if len(files) >= MAX_FILES:
                    return files
        return files

    def _inside(self, rel: str) -> bool:
        """A regular file whose real location is inside the repository (symlinks may not escape it)."""
        path = self.root / rel
        if not path.is_file():
            return False
        if path.is_symlink():
            try:
                path.resolve().relative_to(self.root)
            except (OSError, ValueError):
                return False
        return True

    # ------------------------------------------------------------------ git metadata

    @property
    def tags(self) -> list[str] | None:
        """Git tags, or None when unknown (not a git repository)."""
        if not self._tags_loaded:
            self._tags_loaded = True
            if self.uses_git:
                out = run_git("-C", str(self.root), "tag", "--list")
                self._tags = out.split() if out is not None else None
                # A shallow clone (the CI default) usually has no tags even when the project does.
                if not self._tags and self.git("rev-parse", "--is-shallow-repository") == "true":
                    self._tags = None
        return self._tags

    @tags.setter
    def tags(self, value: list[str] | None) -> None:
        self._tags, self._tags_loaded = value, True

    def git(self, *args: str) -> str | None:
        """Run a git command in the repository (None outside a git work tree or on error)."""
        if not self.uses_git:
            return None
        out = run_git("-C", str(self.root), *args)
        return out.strip() if out is not None else None

    @cached_property
    def ecosystems(self) -> tuple[Detected, ...]:
        return detect(self)

    # ------------------------------------------------------------------ queries

    def has(self, path: str) -> bool:
        """True if ``path`` exists (case-insensitive)."""
        return path.lower() in self._by_lower

    def get(self, path: str) -> str | None:
        """Return the real spelling of ``path`` if it exists (case-insensitive)."""
        return self._by_lower.get(path.lower())

    def glob(self, *patterns: str) -> list[str]:
        """Files matching any of the case-insensitive glob ``patterns``."""
        lowered = [p.lower() for p in patterns]
        return [f for f in self.files if any(fnmatch.fnmatchcase(f.lower(), p) for p in lowered)]

    def under(self, directory: str) -> list[str]:
        """Files anywhere below ``directory`` (case-insensitive)."""
        prefix = directory.lower().rstrip("/") + "/"
        return [f for f in self.files if f.lower().startswith(prefix)]

    def root_files(self) -> list[str]:
        return [f for f in self.files if "/" not in f]

    def find_doc(self, *stems: str, dirs: tuple[str, ...] = DOC_DIRS) -> str | None:
        """Find a document such as ``README.md`` or ``docs/CONTRIBUTING.rst``.

        ``stems`` are compared with the file name up to its first dot, ignoring
        case and treating ``-`` like ``_``. Earlier ``dirs`` and earlier
        ``stems`` win.
        """
        wanted = [s.lower().replace("-", "_") for s in stems]
        best: tuple[tuple[int, int, int], str] | None = None
        for path in self.files:
            parent, _, base = path.rpartition("/")
            parent = parent.lower()
            if parent not in dirs:
                continue
            stem = base.lower().split(".", 1)[0].replace("-", "_")
            if stem not in wanted:
                continue
            rank = (dirs.index(parent), wanted.index(stem), len(path))
            if best is None or rank < best[0]:
                best = (rank, path)
        return best[1] if best else None

    def read_text(self, path: str, limit: int = 1_000_000) -> str:
        """Read up to ``limit`` bytes of ``path`` as text, replacing bad bytes."""
        try:
            with open(self.root / path, "rb") as handle:
                data = handle.read(limit)
        except OSError:
            return ""
        return data.decode("utf-8", errors="replace")

    def size(self, path: str) -> int:
        try:
            return (self.root / path).stat().st_size
        except OSError:
            return 0
