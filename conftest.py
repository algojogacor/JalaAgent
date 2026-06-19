"""Root conftest for pytest — adds workspace src/ directories to sys.path.

This enables test collection from the repo root, fixing the 20+ collection
errors that would silently pass in CI (pytest collects 0 tests when it
cannot find modules).

Each workspace member (packages/*, extensions/*, cli/) with a src/ layout
gets its src/ directory added to sys.path before test collection begins.
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent

# Discover all workspace member src/ directories.
# Structure: packages/*/src/, extensions/*/src/, cli/src/
for top in ["packages", "extensions", "cli"]:
    top_dir = _ROOT / top
    if not top_dir.is_dir():
        continue
    # Direct src/ (e.g. cli/src/).
    if (top_dir / "src").is_dir():
        sys.path.insert(0, str(top_dir / "src"))
    # Nested src/ (e.g. packages/agent-core/src/).
    for member in top_dir.glob("*/src"):
        if member.is_dir():
            sys.path.insert(0, str(member))
    # Doubly-nested (e.g. extensions/providers/openai/src/).
    for member in top_dir.glob("*/*/src"):
        if member.is_dir():
            sys.path.insert(0, str(member))
