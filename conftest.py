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


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

import tempfile

import pytest


@pytest.fixture
def temp_dir():
    """Create a temporary directory that auto-cleans after the test."""
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


@pytest.fixture
def test_config(temp_dir):
    """MemoryConfig pointed at a temporary directory."""
    from memory_core.models import MemoryConfig
    return MemoryConfig(memory_dir=temp_dir / "memories")


@pytest.fixture
def mock_llm():
    """DreamingLLMAdapter that returns predictable, high-confidence facts."""

    class MockLLM:
        async def generate(self, prompt: str) -> str:
            return '[{"content": "Test fact from mock LLM", "confidence": 0.95}]'

    return MockLLM()
