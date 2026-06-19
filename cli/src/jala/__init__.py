"""JalaAgent CLI — entry point for the `jala` command."""

__version__ = "2026.6.18"

from jala.main import app
from jala.setup import run_setup

__all__ = ["app", "run_setup", "__version__"]
