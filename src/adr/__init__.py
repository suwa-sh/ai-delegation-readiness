"""ai-delegation-readiness CLI package."""

from importlib.metadata import PackageNotFoundError, version as _version

try:
    # Single source of truth: the installed package version (pyproject.toml).
    __version__ = _version("ai-delegation-readiness")
except PackageNotFoundError:  # running from a source checkout without install
    __version__ = "0.0.0.dev0"
