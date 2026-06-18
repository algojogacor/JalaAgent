"""Tests for memory-core file_layer (Layer 1 — raw file storage)."""

import asyncio
import tempfile
from pathlib import Path

import pytest
from memory_core.file_layer import FileLayer, _lock_file, _unlock_file
from memory_core.models import Episode, MemoryConfig

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
def layer(config: MemoryConfig) -> FileLayer:
    return FileLayer(config)


def make_episode(
    session_id: str = "sess-001",
    role: str = "user",  # type: ignore[assignment]
    content: str = "Hello world",
    **kwargs: object,
) -> Episode:
    return Episode(session_id=session_id, role=role, content=content, **kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# First-run empty state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestFirstRun:
    """Behaviour when no files exist yet (clean install)."""

    async def test_read_memory_empty(self, layer: FileLayer) -> None:
        assert await layer.read_memory() == ""

    async def test_read_user_empty(self, layer: FileLayer) -> None:
        assert await layer.read_user() == ""

    async def test_get_memory_mtime_zero(self, layer: FileLayer) -> None:
        assert await layer.get_memory_mtime() == 0.0

    async def test_list_sessions_empty(self, layer: FileLayer) -> None:
        assert await layer.list_sessions() == []

    async def test_read_session_empty(self, layer: FileLayer) -> None:
        assert await layer.read_session("nonexistent") == []

    async def test_snapshot_empty(self, layer: FileLayer) -> None:
        content = await layer.snapshot_memory()
        assert content == ""
        assert layer.snapshot_mtime == 0.0


# ---------------------------------------------------------------------------
# MEMORY.md read / write
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestMemoryFile:
    """MEMORY.md read-write round-trip and atomicity."""

    async def test_write_then_read(self, layer: FileLayer) -> None:
        content = "# JalaAgent Memory\n\nThe user prefers dark mode.\n"
        await layer.write_memory(content)
        assert await layer.read_memory() == content

    async def test_overwrite(self, layer: FileLayer) -> None:
        await layer.write_memory("first")
        await layer.write_memory("second")
        assert await layer.read_memory() == "second"

    async def test_write_empty_string(self, layer: FileLayer) -> None:
        await layer.write_memory("")
        assert await layer.read_memory() == ""

    async def test_unicode_content(self, layer: FileLayer) -> None:
        content = "Emoji test: 🐙🔥 日本語テスト नमस्ते\n"
        await layer.write_memory(content)
        assert await layer.read_memory() == content

    async def test_no_tmp_leftover(self, layer: FileLayer) -> None:
        await layer.write_memory("test")
        # No lingering .tmp files after atomic write completes.
        tmp_files = list(layer._memory_path.parent.glob("*.tmp"))
        assert len(tmp_files) == 0


# ---------------------------------------------------------------------------
# USER.md
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestUserFile:
    """USER.md operations."""

    async def test_first_run_empty(self, layer: FileLayer) -> None:
        assert await layer.read_user() == ""

    async def test_write_user_indirectly(self, layer: FileLayer) -> None:
        # USER.md is just another file; write via the same atomic helper.
        content = "name: Arya\nrole: developer\n"
        await layer._write_atomic(layer._user_path, content)
        assert await layer.read_user() == content


# ---------------------------------------------------------------------------
# Session append & read
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSessions:
    """Session JSONL append, read, and listing."""

    async def test_append_session_creates_file(self, layer: FileLayer) -> None:
        ep = make_episode("sess-append")
        await layer.append_session(ep)
        path = layer._sessions_dir / "sess-append.jsonl"
        assert path.exists()

    async def test_append_and_read_roundtrip(self, layer: FileLayer) -> None:
        ep1 = make_episode("sess-rnd", role="user", content="hello")
        ep2 = make_episode(
            "sess-rnd",
            role="assistant",
            content="Hi there!",
            tool_name=None,
            metadata={"tokens": 15},
        )
        await layer.append_session(ep1)
        await layer.append_session(ep2)

        episodes = await layer.read_session("sess-rnd")
        assert len(episodes) == 2
        assert episodes[0].role == "user"
        assert episodes[0].content == "hello"
        assert episodes[1].role == "assistant"
        assert episodes[1].metadata["tokens"] == 15

    async def test_read_session_preserves_uuids(self, layer: FileLayer) -> None:
        ep = make_episode("sess-uuid")
        await layer.append_session(ep)
        results = await layer.read_session("sess-uuid")
        assert len(results) == 1
        assert results[0].id == ep.id

    async def test_read_session_handles_empty_lines(self, layer: FileLayer) -> None:
        ep = make_episode("sess-blank")
        await layer.append_session(ep)
        # Manually add some blank lines
        path = layer._sessions_dir / "sess-blank.jsonl"
        async def _add_blanks() -> None:
            text = path.read_text() + "\n\n"  # extra blank lines
            path.write_text(text)
        await asyncio.to_thread(_add_blanks)
        results = await layer.read_session("sess-blank")
        assert len(results) == 1

    async def test_read_session_skips_invalid_json(self, layer: FileLayer) -> None:
        ep = make_episode("sess-junk")
        await layer.append_session(ep)
        path = layer._sessions_dir / "sess-junk.jsonl"
        async def _add_junk() -> None:
            text = path.read_text() + "this is not json\n"
            path.write_text(text)
        await asyncio.to_thread(_add_junk)
        results = await layer.read_session("sess-junk")
        assert len(results) == 1  # junk line skipped

    async def test_list_sessions(self, layer: FileLayer) -> None:
        await layer.append_session(make_episode("alpha"))
        await layer.append_session(make_episode("beta"))
        await layer.append_session(make_episode("gamma"))
        sessions = await layer.list_sessions()
        assert sessions == ["alpha", "beta", "gamma"]


# ---------------------------------------------------------------------------
# mtime tracking
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestMtime:
    """get_memory_mtime behaviour."""

    async def test_mtime_after_write(self, layer: FileLayer) -> None:
        before = await layer.get_memory_mtime()
        assert before == 0.0
        await layer.write_memory("hello")
        after = await layer.get_memory_mtime()
        assert after > 0.0

    async def test_mtime_unchanged_without_write(self, layer: FileLayer) -> None:
        await layer.write_memory("test")
        t1 = await layer.get_memory_mtime()
        t2 = await layer.get_memory_mtime()
        assert t1 == t2


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSnapshot:
    """snapshot_memory atomically reads content + records mtime."""

    async def test_snapshot_content(self, layer: FileLayer) -> None:
        await layer.write_memory("# Snapshot Test")
        content = await layer.snapshot_memory()
        assert content == "# Snapshot Test"

    async def test_snapshot_mtime_matches(self, layer: FileLayer) -> None:
        await layer.write_memory("mtime test")
        _ = await layer.snapshot_memory()
        mtime = await layer.get_memory_mtime()
        assert layer.snapshot_mtime == mtime

    async def test_snapshot_before_any_write(self, layer: FileLayer) -> None:
        content = await layer.snapshot_memory()
        assert content == ""
        assert layer.snapshot_mtime == 0.0


# ---------------------------------------------------------------------------
# Concurrent write safety
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestConcurrent:
    """Race-condition safety for concurrent writes."""

    async def test_concurrent_writes_do_not_corrupt(self, layer: FileLayer) -> None:
        """Run many concurrent writes and verify the final content is intact."""

        async def writer(i: int) -> None:
            # Each writer writes 10 times; the final state is whatever lands last.
            for _ in range(10):
                await layer.write_memory(f"writer-{i}")

        tasks = [writer(i) for i in range(5)]
        await asyncio.gather(*tasks)

        result = await layer.read_memory()
        # The file should contain exactly one complete write (the last one
        # that landed), not a corrupted mix of partial writes.
        assert result.startswith("writer-")
        assert len(result) == len("writer-X")  # 8 chars

    async def test_concurrent_append_different_sessions(self, layer: FileLayer) -> None:
        """Appending to different sessions in parallel is safe."""

        async def appender(session_id: str) -> None:
            for i in range(10):
                await layer.append_session(
                    make_episode(session_id, content=f"msg-{i}")
                )

        await asyncio.gather(
            appender("par-sess-A"),
            appender("par-sess-B"),
            appender("par-sess-C"),
        )

        for sid in ("par-sess-A", "par-sess-B", "par-sess-C"):
            episodes = await layer.read_session(sid)
            assert len(episodes) == 10

    async def test_snapshot_and_write_serialised(self, layer: FileLayer) -> None:
        """Snapshot should see a consistent state even when racing a write."""
        await layer.write_memory("initial")

        async def slow_snapshot() -> str:
            content = await layer.snapshot_memory()
            await asyncio.sleep(0.05)
            return content

        async def fast_write() -> None:
            await layer.write_memory("racing-write")

        snap_result, _ = await asyncio.gather(slow_snapshot(), fast_write())
        # The snapshot must have captured either "initial" or "racing-write"
        # — never a partial or empty string (given the file already existed).
        assert snap_result in ("initial", "racing-write")


# ---------------------------------------------------------------------------
# Lock helpers
# ---------------------------------------------------------------------------


class TestLockHelpers:
    """Low-level lock / unlock functions."""

    def test_lock_unlock_roundtrip(self, tmp_memory_dir: Path) -> None:
        lock_path = tmp_memory_dir / "test.lock"
        lock_path.touch()
        with lock_path.open("r+") as f:
            _lock_file(f.fileno())
            _unlock_file(f.fileno())


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestProperties:
    """FileLayer property access."""

    def test_memory_dir(self, config: MemoryConfig, layer: FileLayer) -> None:
        assert layer.memory_dir == config.memory_dir

    def test_sessions_dir(self, config: MemoryConfig, layer: FileLayer) -> None:
        assert layer.sessions_dir == config.memory_dir / "sessions"
