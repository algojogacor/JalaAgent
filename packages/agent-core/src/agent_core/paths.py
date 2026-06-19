"""Ensure all JalaAgent package src/ directories are importable.

Call setup_import_paths() once at startup in every entry point
(main.py, server.py, any script that imports JalaAgent packages).
"""
import sys
from pathlib import Path


def setup_import_paths() -> None:
    """Add all JalaAgent src/ dirs to sys.path so provider/skill/channel
    imports work from any entry point.

    Safe to call multiple times — paths are only prepended once.
    """
    root = Path(__file__).resolve().parents[4]  # jalaagent/ repo root

    for top in ["packages", "extensions", "cli"]:
        top_dir = root / top
        if not top_dir.is_dir():
            continue
        # First level: extensions/providers/deepseek/src
        for src in top_dir.glob("*/src"):
            p = str(src)
            if p not in sys.path:
                sys.path.insert(0, p)
        # Second level: extensions/channels/cli/src
        for src in top_dir.glob("*/*/src"):
            p = str(src)
            if p not in sys.path:
                sys.path.insert(0, p)
