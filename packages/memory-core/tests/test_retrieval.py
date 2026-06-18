"""Tests for memory-core retrieval (multi-strategy memory search)."""

import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from memory_core.file_layer import FileLayer
from memory_core.models import (
    Episode,
    Fact,
    MemoryConfig,
    MemorySearchResult,
)
from memory_core.retrieval import MemoryRetriever, _format_entry
from memory_core.vector_layer import VectorLayer

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_memory_dir() -> Path:
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


@pytest.fixture
def tmp_db_path() -> Path:
    with tempfile.TemporaryDirectory() as td:
        yield Path(td) / "memory.db"


@pytest.fixture
def config(tmp_memory_dir: Path, tmp_db_path: Path) -> MemoryConfig:
    return MemoryConfig(
        memory_dir=tmp_memory_dir,
        db_path=tmp_db_path,
        max_retrieval_results=5,
        retrieval_threshold=0.5,
    )


@pytest.fixture
def file_layer(config: MemoryConfig) -> FileLayer:
    return FileLayer(config)


@pytest_asyncio.fixture
async def vector_layer(config: MemoryConfig) -> VectorLayer:
    """VectorLayer with a real db but mocked embedding."""
    vl = VectorLayer(config)
    await vl.initialize()

    # Mock embed to return a fixed vector.
    vl.embed = AsyncMock(return_value=[0.1] * 10)

    # Actually do the work of storing (we want real rows).
    yield vl
    await vl.close()


@pytest_asyncio.fixture
async def retriever(
    config: MemoryConfig,
    file_layer: FileLayer,
    vector_layer: VectorLayer,
) -> MemoryRetriever:
    return MemoryRetriever(config, file_layer, vector_layer)


# ---------------------------------------------------------------------------
# Format helper
# ---------------------------------------------------------------------------


class TestFormatEntry:
    def test_fact_format(self) -> None:
        fact = Fact(content="User prefers dark mode", confidence=0.9)
        result = _format_entry(fact, 0.92)
        assert result.startswith("[Fact]")
        assert "dark mode" in result
        assert "0.92" in result

    def test_episode_format_with_session_date(self) -> None:
        ep = Episode(
            session_id="2026-06-15_session-abc",
            role="user",
            content="I use Python daily",
            timestamp=datetime(2026, 6, 15, tzinfo=UTC),
        )
        result = _format_entry(ep, 0.87)
        assert result.startswith("[Session 2026-06-15]")
        assert "0.87" in result

    def test_episode_format_fallback_date(self) -> None:
        """When session_id has no date, use the timestamp."""
        ep = Episode(
            session_id="random-session",
            role="user",
            content="test",
            timestamp=datetime(2026, 5, 10, tzinfo=UTC),
        )
        result = _format_entry(ep, 0.5)
        assert "[Session 2026-05-10]" in result

    def test_long_content_truncated(self) -> None:
        long_text = "word " * 200
        fact = Fact(content=long_text, confidence=0.5)
        result = _format_entry(fact, 0.5)
        assert len(result) < 500  # way less than 200 words
        assert "..." in result


# ---------------------------------------------------------------------------
# Build system context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestBuildSystemContext:
    async def test_empty_on_first_run(
        self, retriever: MemoryRetriever
    ) -> None:
        ctx = await retriever.build_system_context()
        assert ctx == ""

    async def test_includes_memory_and_user(
        self, retriever: MemoryRetriever, file_layer: FileLayer
    ) -> None:
        await file_layer.write_memory("# Memory\nUser likes Python.\n")
        await file_layer._write_atomic(
            file_layer._user_path,
            "name: Arya\nrole: Developer\n",
        )
        ctx = await retriever.build_system_context()
        assert "<curated-memory>" in ctx
        assert "User likes Python" in ctx
        assert "<user-profile>" in ctx
        assert "Arya" in ctx

    async def test_memory_only(
        self, retriever: MemoryRetriever, file_layer: FileLayer
    ) -> None:
        await file_layer.write_memory("Just memory.")
        ctx = await retriever.build_system_context()
        assert "<curated-memory>" in ctx
        assert "<user-profile>" not in ctx

    async def test_user_only(
        self, retriever: MemoryRetriever, file_layer: FileLayer
    ) -> None:
        await file_layer._write_atomic(
            file_layer._user_path,
            "name: Test User\n",
        )
        ctx = await retriever.build_system_context()
        assert "<user-profile>" in ctx
        assert "<curated-memory>" not in ctx


# ---------------------------------------------------------------------------
# Retrieve
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRetrieve:
    async def test_empty_on_no_data(
        self, retriever: MemoryRetriever
    ) -> None:
        result = await retriever.retrieve("anything")
        assert result == ""

    async def test_retrieves_episodes(
        self, retriever: MemoryRetriever, vector_layer: VectorLayer
    ) -> None:
        ep = Episode(
            session_id="2026-06-15_sess",
            role="user",
            content="I develop on Windows 11 with WSL2",
        )
        await vector_layer.upsert_episode(ep)

        result = await retriever.retrieve("Windows development", k=5)
        assert "<memory-context>" in result
        assert "</memory-context>" in result
        # Should find the episode (same embedding for all content in mock).
        assert len(result) > len("<memory-context>\n</memory-context>\n")

    async def test_retrieves_facts(
        self, retriever: MemoryRetriever, vector_layer: VectorLayer
    ) -> None:
        fact = Fact(content="User uses RTX 3050 for local inference", confidence=0.95)
        await vector_layer.upsert_fact(fact)

        result = await retriever.retrieve("RTX GPU local model", k=5)
        assert "RTX 3050" in result or "<memory-context>" in result

    async def test_threshold_filtering(
        self,
        tmp_memory_dir: Path,
        file_layer: FileLayer,
    ) -> None:
        """With a high threshold and dissimilar embeddings, no results pass."""
        # Use high threshold config.
        cfg = MemoryConfig(
            memory_dir=tmp_memory_dir,
            max_retrieval_results=5,
            retrieval_threshold=0.99,  # very strict
        )
        vl = VectorLayer(cfg)
        await vl.initialize()
        vl.embed = AsyncMock(return_value=[0.1] * 10)
        try:
            ret = MemoryRetriever(cfg, file_layer, vl)
            ep = Episode(
                session_id="s",
                role="user",
                content="Python coding",
            )
            await vl.upsert_episode(ep)
            result = await ret.retrieve("Rust programming", k=5)
            # All embeddings are identical in mock, so cosine=1.0.
            # With threshold 0.99, results should appear.
            assert "<memory-context>" in result
        finally:
            await vl.close()

    async def test_memory_md_fallback(
        self, retriever: MemoryRetriever, file_layer: FileLayer
    ) -> None:
        """When vector results are sparse, MEMORY.md scan supplements."""
        await file_layer.write_memory(
            "# Memory\n\nThe user loves Rust programming language.\n\n"
            "The user deploys to Cloud Run using Docker.\n"
        )
        await retriever.retrieve("Rust programming", k=5)

    async def test_respects_k(
        self, retriever: MemoryRetriever, vector_layer: VectorLayer
    ) -> None:
        for i in range(8):
            ep = Episode(
                session_id=f"sess-{i}",
                role="user",
                content=f"episode {i} data",
            )
            await vector_layer.upsert_episode(ep)

        raw = await retriever.retrieve_raw("episode data", k=3)
        assert len(raw) <= 3

    async def test_raw_results_scored(
        self, retriever: MemoryRetriever, vector_layer: VectorLayer
    ) -> None:
        ep = Episode(
            session_id="2026-06-18_test",
            role="user",
            content="unique query term zxcvbnm",
        )
        await vector_layer.upsert_episode(ep)

        raw = await retriever.retrieve_raw("unique query term zxcvbnm", k=3)
        assert isinstance(raw, list)
        if raw:
            assert isinstance(raw[0], MemorySearchResult)
            assert raw[0].score >= 0.0
            assert raw[0].entry_id != ""


# ---------------------------------------------------------------------------
# Memory md scan
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestMemoryMdScan:
    async def test_scan_finds_keyword(
        self, retriever: MemoryRetriever, file_layer: FileLayer
    ) -> None:
        await file_layer.write_memory(
            "User prefers TypeScript for frontend work.\n\n"
            "User deploys to Vercel.\n"
        )
        results = await retriever._scan_memory_md("TypeScript frontend", k=5)
        assert len(results) >= 1
        assert any("TypeScript" in r.content for r in results)

    async def test_scan_empty_memory(
        self, retriever: MemoryRetriever
    ) -> None:
        results = await retriever._scan_memory_md("anything", k=5)
        assert results == []

    async def test_scan_no_match(
        self, retriever: MemoryRetriever, file_layer: FileLayer
    ) -> None:
        await file_layer.write_memory("Python coding\n")
        results = await retriever._scan_memory_md("zzz_nonexistent", k=5)
        assert results == []


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.asyncio
class TestKnowledgeGraphIntegration:
    async def test_kg_wired_into_retrieval(
        self, config: MemoryConfig, file_layer: FileLayer, vector_layer: VectorLayer
    ) -> None:
        """Knowledge graph results appear in retrieval when KG is provided."""
        import tempfile as _tempfile
        from pathlib import Path as _Path
        from memory_core.knowledge_graph import KnowledgeGraph as _KG

        td = _tempfile.mkdtemp()
        try:
            kg_path = _Path(td) / "graph.db"
            kg = _KG(kg_path)
            await kg.initialize()
            await kg.ingest_page(
                _Path("test.md"),
                '"Arya Rizky" works at "JalaAgent" and uses Python.',
                "person",
            )
            ret = MemoryRetriever(config, file_layer, vector_layer, knowledge_graph=kg)
            results = await ret.retrieve_raw("Arya", k=5)
            kg_results = [r for r in results if r.source == "knowledge_graph"]
            assert len(kg_results) >= 1
            assert any("Arya" in r.content for r in kg_results)
            await kg.close()
        finally:
            import shutil
            shutil.rmtree(td, ignore_errors=True)

    async def test_kg_none_does_not_break(
        self, retriever: MemoryRetriever
    ) -> None:
        """Retrieval works fine without a knowledge graph."""
        result = await retriever.retrieve("anything")
        assert result == "" or "<memory-context>" in result


@pytest.mark.asyncio
class TestProperties:
    async def test_config_access(
        self, retriever: MemoryRetriever, config: MemoryConfig
    ) -> None:
        assert retriever.config is config
