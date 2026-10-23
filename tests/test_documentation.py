from __future__ import annotations

import pytest
from conftest import GOOD_README, MIT_TEXT, result, status

from ossready import Status
from ossready.checks.documentation import changelog_versions, relative_links
from ossready.licenses import BUNDLED, canonical_ids, identify_license, license_text, parse_expression
from ossready.repo import Repo

# ------------------------------------------------------------------ README


def test_readme_missing(make_repo):
    assert status(make_repo({}), "readme") is Status.FAIL


def test_readme_without_sections_warns(make_repo):
    text = "# demo\n\n" + "This project does many things and has a long description. " * 10
    r = result(make_repo({"README.md": text}), "readme")
    assert r.status is Status.WARN
    assert "installation or usage" in r.message


def test_readme_install_command_counts_as_install_section(make_repo):
    text = "# demo\n\n" + "Words. " * 40 + "\n\nRun `npm install demo` and then:\n\n```js\ndemo()\n```\n"
    assert status(make_repo({"README.md": text}), "readme") is Status.PASS


def test_readme_rst_headings(make_repo):
    text = "demo\n====\n\n" + "Words. " * 40 + "\n\nInstallation\n------------\n\nx\n\nUsage\n-----\n\ny\n"
    assert status(make_repo({"README.rst": text}), "readme") is Status.PASS


def test_readme_found_in_github_dir(make_repo):
    r = result(make_repo({".github/README.md": GOOD_README}), "readme")
    assert r.status is Status.PASS
    assert ".github/README.md" in r.message


# ------------------------------------------------------------------ README links


def test_relative_links_ignore_code_external_and_anchors():
    text = """
[ok](docs/guide.md) ![img](assets/logo.png "Logo") [web](https://example.com) [mail](mailto:a@b.c)
[anchor](#usage) `[code](not/a/link.md)`

```md
[fenced](also/not/a/link.md)
```

[ref]: ./CONTRIBUTING.md
<img src="assets/banner.svg" alt="banner"> <a href="//cdn.example.com/x">cdn</a>
"""
    assert relative_links(text) == ["docs/guide.md", "assets/logo.png", "./CONTRIBUTING.md", "assets/banner.svg"]


def test_readme_links_all_resolve(make_repo):
    files = {
        "README.md": "[guide](docs/guide.md#intro) [dir](docs/) [root](/LICENSE) [issues](../../issues) "
        "[space](my%20file.txt)\n",
        "docs/guide.md": "x",
        "LICENSE": MIT_TEXT,
        "my file.txt": "x",
    }
    r = result(make_repo(files), "readme-links")
    assert r.status is Status.PASS
    assert "4 relative links" in r.message


def test_readme_broken_links_fail(make_repo):
    files = {"README.md": "[a](docs/missing.md) ![b](img/nope.png) [c](CONTRIBUTING.md)\n", "CONTRIBUTING.md": "x"}
    r = result(make_repo(files), "readme-links")
    assert r.status is Status.FAIL
    assert "2 broken links" in r.message
    assert "docs/missing.md" in r.message and "img/nope.png" in r.message


def test_readme_links_relative_to_readme_location(make_repo):
    files = {".github/README.md": "[conduct](CODE_OF_CONDUCT.md) [up](../LICENSE)\n", ".github/CODE_OF_CONDUCT.md": "x"}
    r = result(make_repo({**files, "LICENSE": MIT_TEXT}), "readme-links")
    assert r.status is Status.PASS


def test_readme_links_skipped_without_readme(make_repo):
    assert status(make_repo({}), "readme-links") is Status.SKIP


# ------------------------------------------------------------------ license identification

APACHE_HEADER = (
    "                                 Apache License\n                           Version 2.0, January 2004\n"
)
GPL3_HEADER = "                    GNU GENERAL PUBLIC LICENSE\n                       Version 3, 29 June 2007\n"
BSD2 = "Redistributions in binary form must reproduce the above copyright notice"
BSD3 = BSD2 + "...\n3. Neither the name of the copyright holder nor the names of its contributors"


@pytest.mark.parametrize(
    ("text", "spdx"),
    [
        (MIT_TEXT, "MIT"),
        (APACHE_HEADER, "Apache-2.0"),
        (GPL3_HEADER, "GPL-3.0"),
        (BSD2, "BSD-2-Clause"),
        (BSD3, "BSD-3-Clause"),
        ("All rights reserved. Do not copy.", None),
    ],
)
def test_identify_license(text, spdx):
    assert identify_license(text) == spdx


@pytest.mark.parametrize("spdx", BUNDLED)
def test_every_bundled_license_is_recognised(spdx):
    text = license_text(spdx, 2026, "Ada Lovelace")
    assert identify_license(text) == spdx
    assert "[year]" not in text and "[fullname]" not in text


def test_license_text_fills_in_holder():
    assert "Copyright (c) 2026 Ada Lovelace" in license_text("MIT", 2026, "Ada Lovelace")


def test_license_missing(make_repo):
    assert status(make_repo({}), "license") is Status.FAIL


def test_unrecognised_license_warns(make_repo):
    assert status(make_repo({"LICENSE.txt": "Proprietary. All rights reserved.\n"}), "license") is Status.WARN


def test_dual_license(make_repo):
    r = result(make_repo({"LICENSE-MIT": MIT_TEXT, "LICENSE-APACHE": APACHE_HEADER}), "license")
    assert r.status is Status.PASS
    assert "MIT" in r.message and "Apache-2.0" in r.message


def test_reuse_licenses_folder(make_repo):
    assert status(make_repo({"LICENSES/MIT.txt": MIT_TEXT}), "license") is Status.PASS


def test_license_in_subdirectory_does_not_count(make_repo):
    assert status(make_repo({"vendor/lib/LICENSE": MIT_TEXT}), "license") is Status.FAIL


# ------------------------------------------------------------------ license names and expressions


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("MIT", {"MIT"}),
        ("MIT License", {"MIT"}),
        ("Apache License, Version 2.0", {"Apache-2.0"}),
        ("Apache Software License", {"Apache-2.0"}),
        ("License :: OSI Approved :: MIT License", {"MIT"}),
        ("GNU General Public License v3 (GPLv3)", {"GPL-3.0"}),
        ("GNU General Public License v3 or later (GPLv3+)", {"GPL-3.0"}),
        ("GPL-3.0-or-later", {"GPL-3.0"}),
        ("LGPL-2.1-only", {"LGPL-2.1"}),
        ("Mozilla Public License 2.0 (MPL 2.0)", {"MPL-2.0"}),
        ("BSD License", {"BSD-2-Clause", "BSD-3-Clause"}),
        ("The Unlicense (Unlicense)", {"Unlicense"}),
        ("Proprietary", None),
    ],
)
def test_canonical_ids(name, expected):
    found = canonical_ids(name)
    assert (set(found) if found else None) == expected


def test_parse_expression():
    assert parse_expression("MIT OR Apache-2.0") == ({"MIT", "Apache-2.0"}, [])
    assert parse_expression("(MIT OR Apache-2.0) AND Zlib") == ({"MIT", "Apache-2.0", "Zlib"}, [])
    assert parse_expression("Apache-2.0 WITH LLVM-exception") == ({"Apache-2.0"}, [])
    assert parse_expression("MIT/Apache-2.0") == ({"MIT", "Apache-2.0"}, [])
    ids, unknown = parse_expression("MIT OR Commercial")
    assert ids == {"MIT"} and unknown == ["Commercial"]


# ------------------------------------------------------------------ license consistency


@pytest.mark.parametrize(
    ("path", "content"),
    [
        ("pyproject.toml", '[project]\nname = "x"\nlicense = "MIT"\n'),
        ("pyproject.toml", '[project]\nname = "x"\nlicense = { text = "MIT License" }\n'),
        ("pyproject.toml", '[project]\nclassifiers = [\n  "License :: OSI Approved :: MIT License",\n]\n'),
        ("pyproject.toml", '[project]\nlicense = { file = "LICENSE" }\n'),
        ("package.json", '{"name": "x", "license": "MIT"}'),
        ("package.json", '{"name": "x", "license": "SEE LICENSE IN LICENSE"}'),
        ("Cargo.toml", '[package]\nname = "x"\nlicense = "MIT OR Apache-2.0"\n'),
        ("setup.cfg", "[metadata]\nname = x\nlicense = MIT\n"),
        ("setup.py", 'setup(name="x", license="MIT")\n'),
        ("composer.json", '{"license": ["MIT"]}'),
        ("demo.gemspec", 'spec.license = "MIT"\n'),
        ("App.csproj", "<PackageLicenseExpression>MIT</PackageLicenseExpression>"),
    ],
)
def test_license_metadata_matches(make_repo, path, content):
    assert status(make_repo({"LICENSE": MIT_TEXT, path: content}), "license-consistency") is Status.PASS


def test_license_metadata_mismatch(make_repo):
    r = result(make_repo({"LICENSE": MIT_TEXT, "package.json": '{"license": "ISC"}'}), "license-consistency")
    assert r.status is Status.FAIL
    assert "LICENSE is MIT" in r.message and "ISC" in r.message


def test_license_metadata_missing_suggests_the_field(make_repo):
    r = result(make_repo({"LICENSE": MIT_TEXT, "pyproject.toml": '[project]\nname = "x"\n'}), "license-consistency")
    assert r.status is Status.WARN
    assert 'add license = "MIT" under [project]' in r.message


def test_license_metadata_ambiguous_name_is_accepted(make_repo):
    files = {"LICENSE": "Redistributions in binary form must reproduce", "setup.py": 'setup(license="BSD")'}
    assert status(make_repo(files), "license-consistency") is Status.PASS


def test_license_metadata_unknown_value_warns(make_repo):
    r = result(make_repo({"LICENSE": MIT_TEXT, "package.json": '{"license": "UNLICENSED"}'}), "license-consistency")
    assert r.status is Status.WARN
    assert "Could not interpret" in r.message


@pytest.mark.parametrize(
    "files",
    [
        {"pyproject.toml": "[tool.ruff]\nline-length = 100\n"},
        {"Cargo.toml": '[workspace]\nmembers = ["crates/*"]\n'},
        {"package.json": '{"private": true, "scripts": {}}'},
    ],
)
def test_license_metadata_ignores_manifests_that_cannot_declare_one(make_repo, files):
    assert status(make_repo({"LICENSE": MIT_TEXT, **files}), "license-consistency") is Status.SKIP


def test_license_metadata_shim_next_to_declaring_manifest(make_repo):
    files = {"LICENSE": MIT_TEXT, "pyproject.toml": '[project]\nlicense = "MIT"\n', "setup.py": "setup()\n"}
    assert status(make_repo(files), "license-consistency") is Status.PASS


def test_license_metadata_skips_without_manifest(make_repo):
    assert status(make_repo({"LICENSE": MIT_TEXT, "go.mod": "module x\n"}), "license-consistency") is Status.SKIP


# ------------------------------------------------------------------ community docs


@pytest.mark.parametrize(
    ("check_id", "path"),
    [
        ("contributing", "docs/CONTRIBUTING.md"),
        ("contributing", ".github/contributing.rst"),
        ("code-of-conduct", "CODE-OF-CONDUCT.md"),
        ("security-policy", ".github/SECURITY.md"),
        ("changelog", "HISTORY.rst"),
        ("changelog", "NEWS"),
        ("issue-templates", ".github/ISSUE_TEMPLATE/bug.md"),
        ("issue-templates", ".github/issue_template.md"),
        ("pr-template", "docs/PULL_REQUEST_TEMPLATE.md"),
        ("pr-template", ".github/PULL_REQUEST_TEMPLATE/feature.md"),
        ("codeowners", "CODEOWNERS"),
        ("funding", ".github/FUNDING.yml"),
    ],
)
def test_community_files_found(make_repo, check_id, path):
    assert status(make_repo({path: "content\n"}), check_id) is Status.PASS


def test_doc_in_unrelated_directory_does_not_count(make_repo):
    assert status(make_repo({"src/CONTRIBUTING.md": "x\n"}), "contributing") is Status.FAIL


def test_empty_doc_warns(make_repo):
    assert status(make_repo({"SECURITY.md": ""}), "security-policy") is Status.WARN


def test_issue_template_config_alone_is_not_a_template(make_repo):
    files = {".github/ISSUE_TEMPLATE/config.yml": "blank_issues_enabled: false\n"}
    assert status(make_repo(files), "issue-templates") is Status.FAIL


def test_changelog_versions(make_repo):
    text = "# Changelog\n\n## [Unreleased]\n\n## [2.1.0] - 2026-05-01\n\n## v2.0 (2026-01-01)\n\n1.9.3\n-----\n"
    repo = Repo(make_repo({"CHANGELOG.md": text}))
    assert changelog_versions(repo) == ["2.1.0", "2.0", "1.9.3"]
