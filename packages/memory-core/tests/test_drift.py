"""Tests for memory-core drift detection (frozen snapshot pattern)."""

import asyncio
import tempfile
from pathlib import Path

import pytest
from memory_core.drift import DriftDetector
from memory_core.file_layer import FileLayer
from memory_core.models import MemoryConfig

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_memory_dir() -> Path:
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


@pytest.fixture
def config(tmp_memory_dir: Path) -> MemoryConfig:
    return MemoryConfig(memory_dir=tmp_memory_dir)


@pytest.fixture
def file_layer(config: MemoryConfig) -> FileLayer:
    return FileLayer(config)


@pytest.fixture
def detector(file_layer: FileLayer) -> DriftDetector:
    return DriftDetector(file_layer)


# ---------------------------------------------------------------------------
# No drift
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestNoDrift:
    """When MEMORY.md is unchanged, check_drift returns False."""

    async def test_no_drift_after_snapshot(
        self, detector: DriftDetector
    ) -> None:
        content = await detector.take_snapshot()
        assert content == ""
        drifted = await detector.check_drift()
        assert drifted is False

    async def test_no_drift_after_write_through_file_layer(
        self, detector: DriftDetector, file_layer: FileLayer
    ) -> None:
        """Writing via FileLayer updates the file but we snapshot AFTER,
        so no drift because the snapshot sees the latest state."""
        await file_layer.write_memory("written via file layer")
        content = await detector.take_snapshot()
        assert content == "written via file layer"
        drifted = await detector.check_drift()
        assert drifted is False

    async def test_no_drift_on_nonexistent_file(
        self, detector: DriftDetector
    ) -> None:
        """On first run with no MEMORY.md, snapshot returns '' and mtime 0."""
        content = await detector.take_snapshot()
        assert content == ""
        assert detector.snapshot_mtime == 0.0
        drifted = await detector.check_drift()
        assert drifted is False


# ---------------------------------------------------------------------------
# Drift detected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestDriftDetected:
    """When MEMORY.md is modified externally, check_drift returns True."""

    async def test_drift_after_external_edit(
        self, detector: DriftDetector, file_layer: FileLayer
    ) -> None:
        # Write something first so the file exists
        await file_layer.write_memory("original content")
        # Take a snapshot
        content = await detector.take_snapshot()
        assert content == "original content"

        # Simulate external edit — write directly to the file path,
        # bypassing the FileLayer (and the lock).
        memory_path = file_layer.memory_dir / "MEMORY.md"

        def _external_edit() -> None:
            memory_path.write_text("externally modified!", encoding="utf-8")
            import os as _os
            # Ensure mtime is visibly different from snapshot.
            new_mtime = _os.path.getmtime(memory_path) + 1.0
            _os.utime(memory_path, (new_mtime, new_mtime))

        await asyncio.to_thread(_external_edit)

        # Drift should now be detected
        drifted = await detector.check_drift()
        assert drifted is True

    async def test_drift_after_file_deleted(
        self, detector: DriftDetector, file_layer: FileLayer
    ) -> None:
        await file_layer.write_memory("content")
        await detector.take_snapshot()

        # Delete the file externally
        memory_path = file_layer.memory_dir / "MEMORY.md"

        def _external_delete() -> None:
            memory_path.unlink()

        await asyncio.to_thread(_external_delete)

        # mtime will be 0.0 (file missing), snapshot_mtime > 0 → drift
        drifted = await detector.check_drift()
        assert drifted is True


# ---------------------------------------------------------------------------
# Snapshot content
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSnapshotContent:
    """get_snapshot_content returns the content captured at snapshot time."""

    async def test_content_preserved(
        self, detector: DriftDetector, file_layer: FileLayer
    ) -> None:
        await file_layer.write_memory("# JalaAgent Memory\n\nUser: Arya\n")
        content = await detector.take_snapshot()
        assert content == "# JalaAgent Memory\n\nUser: Arya\n"
        assert await detector.get_snapshot_content() == content

    async def test_content_unchanged_after_external_edit(
        self, detector: DriftDetector, file_layer: FileLayer
    ) -> None:
        await file_layer.write_memory("version 1")
        await detector.take_snapshot()

        # External edit
        memory_path = file_layer.memory_dir / "MEMORY.md"

        def _external_edit() -> None:
            memory_path.write_text("version 2 — external", encoding="utf-8")
            import os as _os
            new_mtime = _os.path.getmtime(memory_path) + 1.0
            _os.utime(memory_path, (new_mtime, new_mtime))

        await asyncio.to_thread(_external_edit)

        # Snapshot content should still be the OLD version
        assert await detector.get_snapshot_content() == "version 1"
        # But drift should be detected
        assert await detector.check_drift() is True

    async def test_content_before_snapshot_is_empty(
        self, detector: DriftDetector
    ) -> None:
        assert await detector.get_snapshot_content() == ""


# ---------------------------------------------------------------------------
# Multiple snapshots
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestMultipleSnapshots:
    """Subsequent take_snapshot() calls overwrite the previous snapshot."""

    async def test_resnapshot_updates(
        self, detector: DriftDetector, file_layer: FileLayer
    ) -> None:
        await file_layer.write_memory("first")
        c1 = await detector.take_snapshot()
        assert c1 == "first"

        await file_layer.write_memory("second")
        c2 = await detector.take_snapshot()
        assert c2 == "second"
        assert await detector.get_snapshot_content() == "second"
        # After re-snapshot, no drift (we just captured the latest)
        assert await detector.check_drift() is False


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestEdgeCases:
    """Boundary behaviour."""

    async def test_check_drift_before_snapshot(
        self, detector: DriftDetector
    ) -> None:
        """Calling check_drift before take_snapshot returns False (no-op)."""
        assert not detector.has_snapshot
        drifted = await detector.check_drift()
        assert drifted is False

    async def test_has_snapshot_flag(
        self, detector: DriftDetector
    ) -> None:
        assert detector.has_snapshot is False
        await detector.take_snapshot()
        assert detector.has_snapshot is True

    async def test_unicode_content_snapshot(
        self, detector: DriftDetector, file_layer: FileLayer
    ) -> None:
        content = "🐙 JalaAgent — 日本語テスト — नमस्ते\n"
        await file_layer.write_memory(content)
        snap = await detector.take_snapshot()
        assert snap == content

    async def test_concurrent_sessions_scenario(
        self, detector: DriftDetector, file_layer: FileLayer
    ) -> None:
        """Simulate two "sessions" — one writes, the other detects drift."""
        # Session A: writes and snapshots
        await file_layer.write_memory("Session A data")
        await detector.take_snapshot()

        # Session B: externally modifies
        memory_path = file_layer.memory_dir / "MEMORY.md"

        def _session_b_edit() -> None:
            memory_path.write_text("Session B data", encoding="utf-8")
            import os as _os
            new_mtime = _os.path.getmtime(memory_path) + 1.0
            _os.utime(memory_path, (new_mtime, new_mtime))

        await asyncio.to_thread(_session_b_edit)

        # Session A detects drift
        assert await detector.check_drift() is True
        # But Session A's snapshot still has its own data
        assert await detector.get_snapshot_content() == "Session A data"


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestProperties:
    """DriftDetector property access."""

    async def test_snapshot_mtime_after_take(
        self, detector: DriftDetector, file_layer: FileLayer
    ) -> None:
        await file_layer.write_memory("test")
        await detector.take_snapshot()
        assert detector.snapshot_mtime > 0.0

    async def test_snapshot_mtime_before_take(
        self, detector: DriftDetector
    ) -> None:
        assert detector.snapshot_mtime == 0.0
