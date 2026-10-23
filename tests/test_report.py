from __future__ import annotations

from ossready.model import Report, Result, Status
from ossready.report import badge_url, render_markdown, render_text


def make_report(*statuses: Status, weight: int = 10) -> Report:
    results = tuple(
        Result(
            f"c{i}",
            f"Check {i}",
            "Docs",
            weight,
            s,
            f"message {i}",
            "do this" if s in (Status.WARN, Status.FAIL) else "",
        )
        for i, s in enumerate(statuses)
    )
    return Report("/repo", results)


def test_ascii_fallback():
    out = render_text(make_report(Status.PASS, Status.FAIL, Status.SKIP), encoding="ascii")
    out.encode("ascii")
    assert "  + Check 0" in out and "  x Check 1" in out and "  - Check 2" in out


def test_unicode_symbols():
    out = render_text(make_report(Status.PASS, Status.WARN, Status.FAIL, Status.SKIP))
    assert "✓ Check 0" in out and "! Check 1" in out and "✗ Check 2" in out and "– Check 3" in out
    assert "1 skipped" in out


def test_long_messages_wrap_under_the_title_column():
    report = Report("/r", (Result("x", "Title", "Docs", 1, Status.FAIL, "word " * 40, "hint " * 40),))
    lines = render_text(report, width=60).splitlines()
    assert all(len(line) <= 60 for line in lines)


def test_markdown_escapes_pipes():
    report = Report("/r", (Result("x", "A|B", "Docs", 1, Status.PASS, "x | y", ""),))
    assert "A\\|B" in render_markdown(report) and "x \\| y" in render_markdown(report)


def test_markdown_lists_biggest_wins_first():
    report = Report(
        "/r",
        (
            Result("small", "Small", "Docs", 2, Status.FAIL, "m", "fix small"),
            Result("big", "Big", "Docs", 12, Status.FAIL, "m", "fix big"),
        ),
    )
    out = render_markdown(report)
    assert out.index("**Big**") < out.index("**Small**")


def test_badge_colors():
    assert badge_url(make_report(Status.PASS)).endswith("100%2F100%20A-brightgreen")
    assert badge_url(make_report(Status.FAIL)).endswith("0%2F100%20F-red")
    assert badge_url(make_report(Status.PASS, Status.WARN, Status.FAIL, Status.FAIL)).endswith("38%2F100%20F-red")
    assert badge_url(make_report(Status.PASS, Status.PASS, Status.WARN, Status.FAIL)).endswith("62%2F100%20C-yellow")
