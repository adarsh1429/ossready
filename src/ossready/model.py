"""Data types shared by the checks, the report renderers and the fixer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from .repo import Repo


class Status(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"  # the check does not apply to this repository and is left out of the score


# Share of a check's weight that each status earns. Skipped checks are not scored at all.
CREDIT = {Status.PASS: 1.0, Status.WARN: 0.5, Status.FAIL: 0.0, Status.SKIP: 0.0}

# What every check function returns: its status and a one-line explanation.
Outcome = tuple[Status, str]

GRADES = ((90, "A"), (75, "B"), (60, "C"), (40, "D"))


def grade_for(score: int) -> str:
    for floor, letter in GRADES:
        if score >= floor:
            return letter
    return "F"


@dataclass(frozen=True)
class Check:
    id: str
    title: str
    category: str
    weight: int
    hint: str  # how to fix a failure, shown next to it
    rationale: str  # why the check matters, shown by `ossready explain`
    run: Callable[[Repo], Outcome]


@dataclass(frozen=True)
class Result:
    id: str
    title: str
    category: str
    weight: int
    status: Status
    message: str
    hint: str

    @property
    def scored(self) -> bool:
        return self.status is not Status.SKIP

    @property
    def points(self) -> float:
        return self.weight * CREDIT[self.status]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "weight": self.weight,
            "status": self.status.value,
            "message": self.message,
            "hint": self.hint,
        }


@dataclass(frozen=True)
class Report:
    root: str
    results: tuple[Result, ...]

    @property
    def score(self) -> int:
        total = sum(r.weight for r in self.results if r.scored)
        if total == 0:
            return 100
        return round(100 * sum(r.points for r in self.results if r.scored) / total)

    @property
    def grade(self) -> str:
        return grade_for(self.score)

    def count(self, status: Status) -> int:
        return sum(1 for r in self.results if r.status is status)

    def get(self, check_id: str) -> Result | None:
        return next((r for r in self.results if r.id == check_id), None)

    def to_dict(self) -> dict:
        from . import __version__

        return {
            "tool": "ossready",
            "version": __version__,
            "path": self.root,
            "score": self.score,
            "grade": self.grade,
            "summary": {s.value: self.count(s) for s in Status},
            "checks": [r.to_dict() for r in self.results],
        }
