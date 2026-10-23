"""Render reports as text, JSON, Markdown or a badge."""

from __future__ import annotations

import json
import textwrap
from urllib.parse import quote

from . import __version__
from .model import Report, Status

COLORS = {Status.PASS: "32", Status.WARN: "33", Status.FAIL: "31", Status.SKIP: "2"}
_UNICODE_SYMBOLS = {Status.PASS: "✓", Status.WARN: "!", Status.FAIL: "✗", Status.SKIP: "–"}
_ASCII_SYMBOLS = {Status.PASS: "+", Status.WARN: "!", Status.FAIL: "x", Status.SKIP: "-"}
_MD_SYMBOLS = {Status.PASS: "✅", Status.WARN: "⚠️", Status.FAIL: "❌", Status.SKIP: "➖"}


class Style:
    """Terminal styling that degrades to plain ASCII where needed."""

    def __init__(self, color: bool = False, encoding: str | None = "utf-8") -> None:
        self.color = color
        self.unicode = _supports(encoding, "✓✗→·—–")
        self.symbols = _UNICODE_SYMBOLS if self.unicode else _ASCII_SYMBOLS
        self.arrow, self.dot, self.dash = ("→", "·", "—") if self.unicode else ("->", "-", "-")

    def paint(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.color else text

    def bold(self, text: str) -> str:
        return self.paint("1", text)

    def dim(self, text: str) -> str:
        return self.paint("2", text)

    def symbol(self, status: Status) -> str:
        return self.paint(COLORS[status], self.symbols[status])


def _supports(encoding: str | None, sample: str) -> bool:
    try:
        sample.encode(encoding or "ascii")
    except (UnicodeEncodeError, LookupError):
        return False
    return True


def score_color(score: int) -> Status:
    return Status.PASS if score >= 75 else Status.WARN if score >= 60 else Status.FAIL


def summary_line(report: Report, style: Style) -> str:
    parts = [f"{report.count(Status.PASS)} passed"]
    warnings = report.count(Status.WARN)
    parts.append(f"{warnings} {'warning' if warnings == 1 else 'warnings'}")
    parts.append(f"{report.count(Status.FAIL)} failed")
    if report.count(Status.SKIP):
        parts.append(f"{report.count(Status.SKIP)} skipped")
    score = style.paint(COLORS[score_color(report.score)], f"{report.score}/100 ({report.grade})")
    return f"{style.bold('Score')}  {score}   {f' {style.dot} '.join(parts)}"


def render_text(report: Report, color: bool = False, encoding: str | None = "utf-8", width: int = 100) -> str:
    style = Style(color, encoding)
    title_width = max((len(r.title) for r in report.results), default=0) + 2
    indent = " " * (4 + title_width)
    lines = [style.bold(f"ossready {__version__} {style.dash} {report.root}"), ""]

    category = None
    for result in report.results:
        if result.category != category:
            if category is not None:
                lines.append("")
            category = result.category
            lines.append(style.bold(category))
        message = textwrap.fill(
            result.message,
            width=max(width, len(indent) + 30),
            initial_indent=indent,
            subsequent_indent=indent,
        )[len(indent) :]
        if result.status is Status.SKIP:
            message = style.dim(message)
        lines.append(f"  {style.symbol(result.status)} {result.title.ljust(title_width)}{message}")
        if result.hint:
            hint = textwrap.fill(
                f"{style.arrow} {result.hint}",
                width=max(width, len(indent) + 30),
                initial_indent=indent,
                subsequent_indent=indent + "  ",
            )
            lines.append(style.dim(hint))

    lines += ["", summary_line(report, style)]
    return "\n".join(lines) + "\n"


def render_json(report: Report) -> str:
    return json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n"


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render_markdown(report: Report) -> str:
    skipped = report.count(Status.SKIP)
    lines = [
        "## ossready report",
        "",
        f"{badge_markdown(report)}",
        "",
        f"**Score: {report.score}/100 ({report.grade})**: "
        f"{report.count(Status.PASS)} passed, {report.count(Status.WARN)} warnings, "
        f"{report.count(Status.FAIL)} failed" + (f", {skipped} skipped" if skipped else ""),
        "",
        "| | Check | Category | Details |",
        "|---|---|---|---|",
    ]
    for r in report.results:
        lines.append(f"| {_MD_SYMBOLS[r.status]} | {_cell(r.title)} | {r.category} | {_cell(r.message)} |")
    todo = sorted((r for r in report.results if r.hint), key=lambda r: r.points - r.weight)
    if todo:
        lines += ["", "### How to improve", ""]
        lines += [f"- **{r.title}** (+{r.weight - r.points:g} pts): {r.hint}" for r in todo]
    return "\n".join(lines) + "\n"


_BADGE_COLORS = ((90, "brightgreen"), (75, "green"), (60, "yellow"), (40, "orange"))


def badge_url(report: Report) -> str:
    """A shields.io static badge showing the score and grade."""
    color = next((c for floor, c in _BADGE_COLORS if report.score >= floor), "red")
    message = quote(f"{report.score}/100 {report.grade}", safe="").replace("-", "--")
    return f"https://img.shields.io/badge/ossready-{message}-{color}"


def badge_markdown(report: Report) -> str:
    return f"![ossready {report.score}/100]({badge_url(report)})"


def render_badge(report: Report) -> str:
    return badge_markdown(report) + "\n"


RENDERERS = {"text": render_text, "json": render_json, "markdown": render_markdown, "badge": render_badge}
