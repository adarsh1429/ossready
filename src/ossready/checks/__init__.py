"""The registry of readiness checks and the function that runs them."""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping

from ..licenses import identify_license
from ..model import Check, Report, Result, Status
from ..repo import Repo
from . import community, documentation, engineering, security
from ._util import doc_check

__all__ = ["CHECKS", "CHECK_IDS", "BY_ID", "identify_license", "run_checks"]

CHECKS: tuple[Check, ...] = (
    # ------------------------------------------------------------------ Documentation (36)
    Check(
        id="readme",
        title="README",
        category="Documentation",
        weight=9,
        hint="Add a README.md that says what the project does, how to install it and how to use it.",
        rationale="The README is the first thing every visitor reads. If it doesn't explain what the project is "
        "and how to start, most people leave before trying it.",
        run=documentation.check_readme,
    ),
    Check(
        id="readme-links",
        title="README links",
        category="Documentation",
        weight=3,
        hint="Fix or remove relative links and images in the README that point to files that don't exist.",
        rationale="Broken links and missing images in the README make a project look abandoned. Only links "
        "to files inside the repository are checked, so it works offline.",
        run=documentation.check_readme_links,
    ),
    Check(
        id="license",
        title="License",
        category="Documentation",
        weight=12,
        hint="Add a LICENSE file with an OSI-approved license (https://choosealicense.com). "
        "Without one, nobody may legally reuse your code. `ossready fix --license MIT` can create it.",
        rationale="Code without a license is all-rights-reserved by default: nobody may legally use, change or "
        "share it, and most companies forbid their engineers from touching it.",
        run=documentation.check_license,
    ),
    Check(
        id="license-consistency",
        title="License metadata",
        category="Documentation",
        weight=3,
        hint='Declare the same license in your package manifest (e.g. `license = "MIT"` in pyproject.toml or '
        '`"license": "MIT"` in package.json) as in the LICENSE file.',
        rationale="Package registries, dependency scanners and legal tooling read the license from the manifest, "
        "not the LICENSE file. A missing or different value there gets your package flagged or rejected.",
        run=documentation.check_license_consistency,
    ),
    Check(
        id="contributing",
        title="Contributing guide",
        category="Documentation",
        weight=6,
        hint="Add CONTRIBUTING.md explaining how to set up the project, run the tests and submit changes.",
        rationale="A contributing guide turns 'I'd like to help' into a merged pull request. GitHub links it "
        "from every new issue and pull request.",
        run=doc_check("contributing", what="CONTRIBUTING guide"),
    ),
    Check(
        id="changelog",
        title="Changelog",
        category="Documentation",
        weight=3,
        hint="Keep a CHANGELOG.md (see https://keepachangelog.com) so users can see what changed between releases.",
        rationale="Users need to know whether upgrading is safe. A changelog answers that without making them read "
        "commit history.",
        run=doc_check("changelog", "changes", "history", "news", what="CHANGELOG"),
    ),
    # ------------------------------------------------------------------ Community (18)
    Check(
        id="code-of-conduct",
        title="Code of conduct",
        category="Community",
        weight=4,
        hint="Add CODE_OF_CONDUCT.md, for example based on the Contributor Covenant, and say how to report problems.",
        rationale="A code of conduct sets expectations and tells people how to report abuse, which makes newcomers "
        "more willing to take part.",
        run=doc_check("code_of_conduct", what="code of conduct"),
    ),
    Check(
        id="security-policy",
        title="Security policy",
        category="Community",
        weight=6,
        hint="Add SECURITY.md telling people how to report vulnerabilities privately, and turn on private "
        "vulnerability reporting in the repository settings.",
        rationale="Without a private channel, people who find a vulnerability either report it in a public issue, "
        "exposing your users, or don't report it at all.",
        run=doc_check("security", what="SECURITY policy"),
    ),
    Check(
        id="issue-templates",
        title="Issue templates",
        category="Community",
        weight=3,
        hint="Add templates under .github/ISSUE_TEMPLATE/ so bug reports arrive with the details you need.",
        rationale="Templates collect versions, steps to reproduce and expected behaviour up front, which saves "
        "maintainers a round of follow-up questions on every report.",
        run=community.check_issue_templates,
    ),
    Check(
        id="pr-template",
        title="Pull request template",
        category="Community",
        weight=2,
        hint="Add .github/pull_request_template.md with a short checklist for contributors.",
        rationale="A checklist reminds contributors to add tests and docs before review instead of after.",
        run=community.check_pr_template,
    ),
    Check(
        id="codeowners",
        title="Code owners",
        category="Community",
        weight=2,
        hint="Add .github/CODEOWNERS so reviewers are requested automatically.",
        rationale="CODEOWNERS routes each pull request to the right reviewer automatically and can be required by "
        "branch protection, so changes don't sit unreviewed.",
        run=community.check_codeowners,
    ),
    Check(
        id="funding",
        title="Funding",
        category="Community",
        weight=1,
        hint="Add .github/FUNDING.yml (GitHub Sponsors, Open Collective, ...) to show a Sponsor button.",
        rationale="Maintenance is work. A Sponsor button gives users and companies who depend on the project an "
        "easy way to support it.",
        run=community.check_funding,
    ),
    # ------------------------------------------------------------------ Engineering (35)
    Check(
        id="ci",
        title="Continuous integration",
        category="Engineering",
        weight=9,
        hint="Run your tests on every pull request, for example with a workflow in .github/workflows/.",
        rationale="CI tells contributors within minutes whether their change works, so maintainers review code "
        "instead of running it by hand.",
        run=engineering.check_ci,
    ),
    Check(
        id="tests",
        title="Tests",
        category="Engineering",
        weight=9,
        hint="Add automated tests so contributors can check their changes don't break anything.",
        rationale="Tests are what make it safe to accept changes from strangers.",
        run=engineering.check_tests,
    ),
    Check(
        id="manifest",
        title="Package manifest",
        category="Engineering",
        weight=4,
        hint="Add a package manifest (pyproject.toml, package.json, Cargo.toml, go.mod, ...) so the project "
        "can be installed with standard tools.",
        rationale="A manifest makes the project installable with the tools people already use and declares its "
        "dependencies so they can be audited and updated.",
        run=engineering.check_manifest,
    ),
    Check(
        id="code-style",
        title="Code style",
        category="Engineering",
        weight=3,
        hint="Add a formatter or linter config (Ruff, Prettier, ESLint, golangci-lint, ...) or at least an "
        ".editorconfig.",
        rationale="An agreed, automated style ends formatting debates in review and keeps diffs focused on what "
        "changed.",
        run=engineering.check_code_style,
    ),
    Check(
        id="releases",
        title="Versioned releases",
        category="Engineering",
        weight=3,
        hint="Tag releases with semantic versions (git tag v1.0.0 && git push --tags) and list them in the changelog.",
        rationale="Version tags let users pin a known-good release, report bugs against a version and upgrade "
        "deliberately.",
        run=engineering.check_releases,
    ),
    Check(
        id="gitignore",
        title=".gitignore",
        category="Engineering",
        weight=2,
        hint="Add a .gitignore so build output and local files don't end up in commits.",
        rationale="A .gitignore keeps build output, editor files and local secrets such as .env out of commits.",
        run=engineering.check_gitignore,
    ),
    Check(
        id="dependency-updates",
        title="Dependency updates",
        category="Engineering",
        weight=3,
        hint="Enable Dependabot (.github/dependabot.yml) or Renovate to keep dependencies patched.",
        rationale="Most vulnerabilities reach projects through outdated dependencies. Automated update pull "
        "requests keep them patched with almost no maintainer effort.",
        run=engineering.check_dependency_updates,
    ),
    Check(
        id="large-files",
        title="No large files",
        category="Engineering",
        weight=2,
        hint="Move large binaries to Git LFS or release assets, and remove them from history.",
        rationale="Large binaries make every clone slow forever, because git keeps every version. GitHub rejects "
        "files over 100 MB.",
        run=engineering.check_large_files,
    ),
    # ------------------------------------------------------------------ Security (11)
    Check(
        id="secrets",
        title="No committed secrets",
        category="Security",
        weight=8,
        hint="Remove real credentials, rotate them, and purge them from git history (e.g. with git filter-repo). "
        "Dummy keys used only by tests can stay.",
        rationale="Publishing a repository publishes its secrets. Bots scrape public repositories for keys within "
        "minutes of a push.",
        run=security.check_secrets,
    ),
    Check(
        id="workflow-security",
        title="Workflow security",
        category="Security",
        weight=3,
        hint="Give every workflow a `permissions:` block, pass untrusted event data through `env:` instead of "
        "`${{ }}` in `run:`, and never check out pull request code in `pull_request_target` workflows.",
        rationale="Once a repository is public, anyone can open issues and pull requests. Workflows that "
        "interpolate their titles or run their code with write access let strangers take over your CI and "
        "publish releases.",
        run=security.check_workflow_security,
    ),
)

CHECK_IDS = tuple(c.id for c in CHECKS)
BY_ID = {c.id: c for c in CHECKS}


def run_checks(
    root: str | os.PathLike[str] | Repo = ".",
    ignore: Iterable[str] = (),
    weights: Mapping[str, int] | None = None,
) -> Report:
    """Run every check except those in ``ignore`` against a repository.

    ``root`` is a directory or an existing :class:`Repo`. ``weights`` overrides
    the weight of individual checks.
    """
    skipped = {i.strip().lower() for i in ignore if i.strip()}
    weights = dict(weights or {})
    unknown = (skipped | set(weights)) - set(CHECK_IDS)
    if unknown:
        raise ValueError(f"unknown check id(s): {', '.join(sorted(unknown))}")
    repo = root if isinstance(root, Repo) else Repo(root)
    results = []
    for check in CHECKS:
        if check.id in skipped:
            continue
        status, message = check.run(repo)
        results.append(
            Result(
                id=check.id,
                title=check.title,
                category=check.category,
                weight=weights.get(check.id, check.weight),
                status=status,
                message=message,
                hint=check.hint if status in (Status.WARN, Status.FAIL) else "",
            )
        )
    return Report(root=repo.display, results=tuple(results))
