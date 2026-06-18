"""JalaAgent CLI — entry point for the `jala` command."""

from jala.main import app
from jala.setup import run_setup

__all__ = ["app", "run_setup"]
