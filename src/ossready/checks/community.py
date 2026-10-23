"""Issue and pull request templates, ownership and funding."""

from __future__ import annotations

from ..model import Outcome, Status
from ..repo import DOC_DIRS, Repo
from ._util import plural


def check_issue_templates(repo: Repo) -> Outcome:
    templates = [f for f in repo.under(".github/ISSUE_TEMPLATE") if f.rpartition("/")[2].lower() != "config.yml"]
    if templates:
        return Status.PASS, plural(len(templates), "issue template")
    single = repo.find_doc("issue_template")
    if single:
        return Status.PASS, single
    return Status.FAIL, "No issue templates found"


def check_pr_template(repo: Repo) -> Outcome:
    path = repo.find_doc("pull_request_template")
    if path:
        return Status.PASS, path
    folder = repo.under(".github/PULL_REQUEST_TEMPLATE")
    if folder:
        return Status.PASS, plural(len(folder), "pull request template")
    return Status.FAIL, "No pull request template found"


def check_codeowners(repo: Repo) -> Outcome:
    for directory in DOC_DIRS:
        path = repo.get(f"{directory}/CODEOWNERS" if directory else "CODEOWNERS")
        if path:
            return Status.PASS, path
    return Status.FAIL, "No CODEOWNERS file found"


def check_funding(repo: Repo) -> Outcome:
    path = repo.get(".github/FUNDING.yml") or repo.get(".github/FUNDING.yaml")
    if path:
        return Status.PASS, path
    return Status.FAIL, "No .github/FUNDING.yml found"
