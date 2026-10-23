"""Per-project settings from ``.ossready.toml`` or ``[tool.ossready]`` in ``pyproject.toml``.

Example::

    # .ossready.toml
    ignore = ["funding", "codeowners"]
    fail-under = 85

    [weights]
    tests = 15
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised on Python 3.9 and 3.10
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

CONFIG_FILE = ".ossready.toml"
_KEYS = {"ignore", "fail-under", "weights"}


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Config:
    ignore: tuple[str, ...] = ()
    fail_under: int | None = None
    weights: dict[str, int] = field(default_factory=dict)
    source: str | None = None


def _load_toml(path: Path) -> dict[str, Any]:
    if tomllib is None:
        raise ConfigError(f"reading {path.name} needs Python 3.11+ or the 'tomli' package")
    try:
        with open(path, "rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"{path.name}: {exc}") from exc


def load_config(root: str | Path, known_ids: tuple[str, ...] = ()) -> Config:
    """Read settings for the repository at ``root``; returns defaults when there are none."""
    root = Path(root)
    dedicated = root / CONFIG_FILE
    if dedicated.is_file():
        return _parse(_load_toml(dedicated), CONFIG_FILE, known_ids)
    pyproject = root / "pyproject.toml"
    if pyproject.is_file() and b"[tool.ossready" in pyproject.read_bytes():
        table = _load_toml(pyproject).get("tool", {}).get("ossready", {})
        return _parse(table, "pyproject.toml [tool.ossready]", known_ids)
    return Config()


def _parse(data: dict[str, Any], source: str, known_ids: tuple[str, ...]) -> Config:
    unknown_keys = set(data) - _KEYS
    if unknown_keys:
        raise ConfigError(f"{source}: unknown setting(s): {', '.join(sorted(unknown_keys))}")

    ignore = data.get("ignore", [])
    if not isinstance(ignore, list) or not all(isinstance(i, str) for i in ignore):
        raise ConfigError(f"{source}: 'ignore' must be a list of check IDs")

    fail_under = data.get("fail-under")
    if fail_under is not None and (isinstance(fail_under, bool) or not isinstance(fail_under, int)):
        raise ConfigError(f"{source}: 'fail-under' must be a whole number")
    if fail_under is not None and not 0 <= fail_under <= 100:
        raise ConfigError(f"{source}: 'fail-under' must be between 0 and 100")

    weights = data.get("weights", {})
    if not isinstance(weights, dict) or not all(
        isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in weights.values()
    ):
        raise ConfigError(f"{source}: 'weights' must map check IDs to whole numbers of 0 or more")

    if known_ids:
        unknown_ids = (set(ignore) | set(weights)) - set(known_ids)
        if unknown_ids:
            raise ConfigError(f"{source}: unknown check id(s): {', '.join(sorted(unknown_ids))}")

    return Config(ignore=tuple(ignore), fail_under=fail_under, weights=dict(weights), source=source)
