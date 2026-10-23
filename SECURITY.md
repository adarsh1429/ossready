# Security Policy

## Supported versions

Security fixes are released for the latest minor version of ossready.

| Version | Supported |
|---------|-----------|
| 0.2.x   | Yes       |
| < 0.2   | No        |

## Reporting a vulnerability

Please do **not** open a public issue for security problems.

Report them privately through GitHub: open the repository's **Security** tab and choose
**Report a vulnerability**. Include what you found, how to reproduce it, and the impact you expect.

You can expect an acknowledgement within 3 working days and an assessment within 10. Once a fix
is released we will credit you in the changelog unless you prefer to stay anonymous.

## Scope

ossready reads files in the directory it is pointed at and runs `git` (`ls-files`, `tag`, and for
remote targets `clone --depth 1` and `ls-remote` into a temporary folder that is deleted afterwards).
It never executes project code. `ossready fix` only creates new files and never overwrites existing
ones.

Examples of issues in scope: reading or writing files outside the target repository, following
symlinks out of it, executing commands through crafted URLs or repository contents, secrets being
printed in reports, or crashes on crafted files.
