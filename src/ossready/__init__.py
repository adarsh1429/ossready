"""ossready: check whether a repository is ready to be published and maintained as open source."""

__version__ = "0.2.0"

from .checks import CHECKS, run_checks  # noqa: E402
from .config import Config, ConfigError, load_config  # noqa: E402
from .fix import FixOptions, apply_plan, plan_fixes  # noqa: E402
from .model import Check, Report, Result, Status  # noqa: E402
from .repo import Repo  # noqa: E402

__all__ = [
    "CHECKS",
    "Check",
    "Config",
    "ConfigError",
    "FixOptions",
    "Repo",
    "Report",
    "Result",
    "Status",
    "__version__",
    "apply_plan",
    "load_config",
    "plan_fixes",
    "run_checks",
]
