"""Small helpers shared by the check modules."""

from __future__ import annotations

from typing import Callable

from ..model import Outcome, Status
from ..repo import Repo


def plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def shorten(items: list[str], limit: int = 5) -> str:
    extra = f" and {len(items) - limit} more" if len(items) > limit else ""
    return ", ".join(items[:limit]) + extra


def doc_check(*stems: str, what: str) -> Callable[[Repo], Outcome]:
    """A check that passes when a document with one of ``stems`` exists in the usual places."""

    def run(repo: Repo) -> Outcome:
        path = repo.find_doc(*stems)
        if path is None:
            return Status.FAIL, f"No {what} found"
        if repo.size(path) == 0:
            return Status.WARN, f"{path} is empty"
        return Status.PASS, path

    return run
