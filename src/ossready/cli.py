"""Command-line interface.

ossready [check] [PATH | URL] [options]   score a repository (the default command)
ossready fix [PATH] [options]             create the files it is missing
ossready explain CHECK                    what a check looks for and why
ossready list                             every check with its weight
"""

from __future__ import annotations

import argparse
import contextlib
import os
import shutil
import sys
import textwrap
from collections.abc import Iterator, Sequence

from . import __version__
from .checks import BY_ID, CHECK_IDS, CHECKS, run_checks
from .config import Config, ConfigError, load_config
from .fix import FIXABLE, FixOptions, apply_plan, plan_fixes
from .licenses import BUNDLED
from .model import Report, Status
from .remote import RemoteError, checkout, is_remote
from .repo import Repo
from .report import (
    COLORS,
    Style,
    render_badge,
    render_json,
    render_markdown,
    render_text,
    score_color,
    summary_line,
)

EXIT_OK = 0
EXIT_BELOW_THRESHOLD = 1
EXIT_USAGE = 2

COMMANDS = ("check", "fix", "explain", "list")


# --------------------------------------------------------------------------- parser


def _ids(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ossready",
        description="Check whether a repository is ready to be published and maintained as open source, "
        "and create the files it is missing.",
        epilog="Run 'ossready COMMAND --help' for details. Without a command, 'check' is assumed.",
    )
    parser.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", metavar="COMMAND")

    check = commands.add_parser("check", help="score a repository (default)", description="Score a repository.")
    check.add_argument(
        "target",
        nargs="?",
        default=".",
        metavar="PATH|URL",
        help="directory, or a git URL such as github.com/owner/repo (default: current directory)",
    )
    check.add_argument(
        "-f",
        "--format",
        choices=("text", "json", "markdown", "badge"),
        default="text",
        help="output format (default: text)",
    )
    check.add_argument(
        "--fail-under", type=int, metavar="SCORE", help="exit with status 1 when the score is below SCORE"
    )
    check.add_argument("--ignore", type=_ids, default=[], metavar="IDS", help="comma-separated check IDs to skip")
    check.add_argument("--no-config", action="store_true", help="ignore .ossready.toml and [tool.ossready]")
    check.add_argument("--list-checks", action="store_true", help=argparse.SUPPRESS)
    check.add_argument("--no-color", action="store_true", help="disable colored output")

    fix = commands.add_parser(
        "fix",
        help="create missing files (LICENSE, CONTRIBUTING.md, CI, ...)",
        description="Create the files a repository is missing, tailored to its language. "
        "Existing files are never changed.",
    )
    fix.add_argument("path", nargs="?", default=".", help="repository to fix (default: current directory)")
    fix.add_argument("-n", "--dry-run", action="store_true", help="show what would be created without writing")
    fix.add_argument("--only", type=_ids, default=[], metavar="IDS", help="only fix these check IDs")
    fix.add_argument(
        "--license",
        metavar="SPDX",
        help=f"license to add if missing: {', '.join(BUNDLED)} "
        "(default: whatever your package manifest declares, otherwise MIT)",
    )
    fix.add_argument("--owner", help="GitHub user or organization (default: from the origin remote)")
    fix.add_argument("--author", help="copyright holder (default: git user.name)")
    fix.add_argument("--email", help="contact for conduct and security reports (default: git user.email)")
    fix.add_argument("--no-color", action="store_true", help="disable colored output")

    explain = commands.add_parser("explain", help="explain what a check looks for and why")
    explain.add_argument("check_id", metavar="CHECK", choices=CHECK_IDS, help="a check ID, see 'ossready list'")

    commands.add_parser("list", help="list every check with its ID and weight")
    return parser


def _normalize_argv(argv: list[str]) -> list[str]:
    """Make 'check' the default command so 'ossready .' and 'ossready --format json' keep working."""
    if not argv:
        return ["check"]
    if argv[0] in COMMANDS or argv[0] in ("-h", "--help", "-V", "--version"):
        return argv
    return ["check", *argv]


def _use_color(no_color: bool) -> bool:
    if no_color or os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return sys.stdout.isatty()


def _width() -> int:
    return min(shutil.get_terminal_size((100, 20)).columns, 120)


def _error(message: str) -> int:
    print(f"ossready: error: {message}", file=sys.stderr)
    return EXIT_USAGE


# --------------------------------------------------------------------------- commands


def _list_checks() -> str:
    width = max(len(c.id) for c in CHECKS) + 2
    lines = [f"{'ID'.ljust(width)}{'WEIGHT':<8}{'FIX':<5}{'CATEGORY':<15}TITLE"]
    for c in CHECKS:
        fixable = "yes" if c.id in FIXABLE else ""
        lines.append(f"{c.id.ljust(width)}{c.weight:<8}{fixable:<5}{c.category:<15}{c.title}")
    lines += ["", "FIX: 'ossready fix' can create the missing files for this check."]
    return "\n".join(lines) + "\n"


def _explain(check_id: str) -> str:
    check = BY_ID[check_id]
    wrap = textwrap.TextWrapper(width=88)
    lines = [
        f"{check.title} ({check.id})",
        f"Category: {check.category} · Weight: {check.weight} of 100",
        "",
        "Why it matters",
        *wrap.wrap(check.rationale),
        "",
        "How to pass",
        *wrap.wrap(check.hint),
    ]
    if check.id in FIXABLE:
        lines += ["", f"Automatic fix: run 'ossready fix --only {check.id}'."]
    return "\n".join(lines) + "\n"


@contextlib.contextmanager
def _open_target(target: str) -> Iterator[Repo]:
    if is_remote(target):
        with checkout(target) as repo:
            yield repo
    else:
        yield Repo(target)


def _check(args: argparse.Namespace) -> int:
    if args.list_checks:
        sys.stdout.write(_list_checks())
        return EXIT_OK
    if args.fail_under is not None and not 0 <= args.fail_under <= 100:
        return _error("--fail-under must be between 0 and 100")
    remote = is_remote(args.target)
    if not remote and not os.path.isdir(args.target):
        return _error(f"not a directory: {args.target}")

    try:
        with _open_target(args.target) as repo:
            config = Config() if args.no_config else load_config(repo.root, CHECK_IDS)
            report = run_checks(repo, ignore=[*config.ignore, *args.ignore], weights=config.weights)
    except (ConfigError, ValueError, RemoteError) as exc:
        return _error(str(exc))

    color = _use_color(args.no_color)
    if args.format == "json":
        output = render_json(report)
    elif args.format == "markdown":
        output = render_markdown(report)
    elif args.format == "badge":
        output = render_badge(report)
    else:
        output = render_text(report, color=color, encoding=sys.stdout.encoding, width=_width())
        output += _fix_tip(report, remote, Style(color, sys.stdout.encoding))
    sys.stdout.write(output)

    fail_under = args.fail_under if args.fail_under is not None else config.fail_under
    if fail_under is not None and report.score < fail_under:
        print(f"ossready: score {report.score} is below the minimum of {fail_under}", file=sys.stderr)
        return EXIT_BELOW_THRESHOLD
    return EXIT_OK


def _fix_tip(report: Report, remote: bool, style: Style) -> str:
    fixable = [r for r in report.results if r.status is Status.FAIL and r.id in FIXABLE]
    if remote or not fixable:
        return ""
    gain = sum(r.weight for r in fixable)
    return (
        "\n"
        + style.dim(
            f"Tip: 'ossready fix' can create the missing files for {len(fixable)} of these checks "
            f"(up to {gain} points). Add --dry-run to preview."
        )
        + "\n"
    )


def _fix(args: argparse.Namespace) -> int:
    if is_remote(args.path):
        return _error("'fix' works on a local checkout; clone the repository first")
    if not os.path.isdir(args.path):
        return _error(f"not a directory: {args.path}")
    options = FixOptions(
        license=args.license, owner=args.owner, author=args.author, email=args.email, only=tuple(args.only)
    )
    try:
        plan = plan_fixes(args.path, options)
    except ValueError as exc:
        return _error(str(exc))

    style = Style(_use_color(args.no_color), sys.stdout.encoding)
    written = plan.files if args.dry_run else apply_plan(plan, args.path)
    out = [style.bold(f"ossready fix {style.dash} {plan.before.root}"), ""]

    if written:
        out.append(style.bold("Would create" if args.dry_run else "Created"))
        width = max(len(f.path) for f in written) + 2
        for new in written:
            plus = style.paint("32", "+")
            out.append(f"  {plus} {new.path.ljust(width)}{style.dim(new.summary)}".rstrip())
        out.append("")
    else:
        out += ["Nothing to create: no fixable checks are failing.", ""]

    reviews = [f for f in written if f.review]
    if reviews:
        out.append(style.bold("Please review"))
        out += [f"  {style.dot} {f.path}: {f.review}" for f in reviews]
        out.append("")

    # After a real run, re-check so the to-do list reflects the new state (e.g. a LICENSE that now
    # needs declaring in the manifest). A dry run can only report what the plan knows.
    after = None if args.dry_run else run_checks(args.path)
    # Fixers explain why they couldn't act (e.g. "needs a GitHub username"); prefer that over the generic hint.
    reasons = {m.check_id: m.reason for m in plan.manual if m.reason != BY_ID[m.check_id].hint}
    if after is None:
        todo = [(m.title, m.status, m.reason, "") for m in plan.manual]
    else:
        todo = []
        for r in after.results:
            if r.status not in (Status.FAIL, Status.WARN) or (args.only and r.id not in args.only):
                continue
            if r.id in reasons:
                todo.append((r.title, r.status, reasons[r.id], ""))
            elif r.status is Status.WARN:
                todo.append((r.title, r.status, r.message, r.hint))
            else:
                todo.append((r.title, r.status, r.hint, ""))
    if todo:
        out.append(style.bold("Still to do by hand"))
        wrap = textwrap.TextWrapper(width=_width() - 4, subsequent_indent="    ")
        for title, status, reason, detail in todo:
            out.append(f"  {style.symbol(status)} {wrap.fill(f'{title}: {reason}')}")
            if detail:
                out.append(
                    style.dim(
                        textwrap.fill(
                            f"{style.arrow} {detail}", _width(), initial_indent="    ", subsequent_indent="      "
                        )
                    )
                )
        out.append("")

    if after is None:
        out.append(summary_line(plan.before, style))
        if plan.files:
            out.append(style.dim("Dry run: nothing was written. Run without --dry-run to create these files."))
    else:
        before = plan.before
        arrow = style.paint(COLORS[score_color(after.score)], f"{after.score}/100 ({after.grade})")
        out.append(f"{style.bold('Score')}  {before.score}/100 ({before.grade}) {style.arrow} {arrow}")
    sys.stdout.write("\n".join(out) + "\n")
    return EXIT_OK


# --------------------------------------------------------------------------- entry point


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(_normalize_argv(list(sys.argv[1:] if argv is None else argv)))
    if args.command == "list":
        sys.stdout.write(_list_checks())
        return EXIT_OK
    if args.command == "explain":
        sys.stdout.write(_explain(args.check_id))
        return EXIT_OK
    if args.command == "fix":
        return _fix(args)
    return _check(args)
