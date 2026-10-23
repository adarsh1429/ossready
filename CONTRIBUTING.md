# Contributing to ossready

Thanks for helping! Bug reports, new checks, support for more ecosystems and documentation fixes
are all welcome.

## Getting set up

You need Python 3.9 or newer and git.

```bash
git clone https://github.com/OWNER/ossready.git
cd ossready
python -m venv .venv
source .venv/bin/activate        # on Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Running the checks

```bash
pytest                      # unit tests
ruff check .                # lint
ruff format --check .       # formatting
ossready --fail-under 95    # ossready must keep an A on itself
```

CI runs all of these on Linux for Python 3.9 to 3.14, and on macOS and Windows, for every pull request.

## How the code is organised

| Path | What it does |
|------|--------------|
| `src/ossready/repo.py` | Lists a repository's files once (respecting `.gitignore`) and answers questions about them |
| `src/ossready/checks/` | The checks, one module per category, and the registry in `__init__.py` |
| `src/ossready/licenses.py` | License recognition, manifest license fields, and the bundled license texts |
| `src/ossready/ecosystems.py` | Detects languages from their manifests |
| `src/ossready/fix/` | `ossready fix`: templates, per-ecosystem toolchains, and planning |
| `src/ossready/remote.py` | Shallow clones for checking remote repositories |
| `src/ossready/report.py` | Text, JSON, Markdown and badge output |
| `src/ossready/cli.py` | The command-line interface |

## Adding a check

1. Write a function in the right module under `src/ossready/checks/` that takes a `Repo` and returns
   `(Status, message)`. Return `Status.SKIP` when the check doesn't apply. Keep it fast and offline:
   it may read files, but must not use the network.
2. Register it in `CHECKS` with a short kebab-case ID, a title, a category, a weight, a hint that
   says exactly how to fix a failure, and a rationale that explains why it matters.
3. Weights add up to 100. Explain in the pull request which weights you took points from and why.
4. Add tests covering pass, fail and, where they can happen, warn and skip.
5. Add a row to the table in `README.md` and a line under "Unreleased" in `CHANGELOG.md`.

## Adding a fixer or an ecosystem

- Fixers live in `src/ossready/fix/__init__.py` and are registered in `FIXERS`. They return the files
  to create, or a string explaining why they can't help. They must never modify existing files.
- To support a new language, add it to `ecosystems.py` and add a toolchain (setup, test and lint
  commands and a CI job) to `fix/toolchains.py`. Add its repository to `ECOSYSTEM_REPOS` in
  `tests/test_fix.py`, which checks that the generated files pass ossready's own checks.

## Submitting changes

- Open an issue first for large changes so we can agree on the approach.
- Keep pull requests focused on one thing.
- Write commit messages in the imperative mood ("Add Gradle detection").
- Make sure tests, lint and formatting pass.

## Reporting bugs

Use the bug report template and include the command you ran, the output, and what you expected.
For security problems, follow [SECURITY.md](SECURITY.md) instead of opening a public issue.
