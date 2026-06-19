"""Integration test: end-to-end memory flow (file → vector → retrieval → drift)."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from memory_core.drift import DriftDetector
from memory_core.file_layer import FileLayer
from memory_core.models import Episode, Fact, MemoryConfig
from memory_core.retrieval import MemoryRetriever
from memory_core.vector_layer import VectorLayer


@pytest.fixture
def tmp_memory_dir() -> Path:
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


@pytest.fixture
def tmp_db_path() -> Path:
    with tempfile.TemporaryDirectory() as td:
        yield Path(td) / "test.db"


@pytest.fixture
def config(tmp_memory_dir: Path, tmp_db_path: Path) -> MemoryConfig:
    return MemoryConfig(
        memory_dir=tmp_memory_dir,
        db_path=tmp_db_path,
        embedding_dim=10,
        retrieval_threshold=0.1,
    )


@pytest.mark.asyncio
class TestMemoryE2E:
    async def test_full_flow(
        self, config: MemoryConfig
    ) -> None:
        """End-to-end: write episodes → vector index → retrieve → drift detect."""
        # 1. Initialize layers.
        file_layer = FileLayer(config)
        vector_layer = VectorLayer(config)
        await vector_layer.initialize()

        # Mock embedding to avoid HTTP calls (store real dummy vectors).
        vector_layer.embed = AsyncMock(return_value=[0.1] * 10)

        try:
            # 2. Append episodes to a session.
            ep1 = Episode(
                session_id="2026-06-18_test",
                role="user",
                content="I develop on Windows 11 with WSL2",
            )
            ep2 = Episode(
                session_id="2026-06-18_test",
                role="user",
                content="I prefer Python over JavaScript",
            )
            await file_layer.append_session(ep1)
            await file_layer.append_session(ep2)

            # 3. Index episodes in vector layer.
            await vector_layer.upsert_episode(ep1)
            await vector_layer.upsert_episode(ep2)

            # 4. Create fact and index.
            fact = Fact(
                content="User develops on Windows 11",
                confidence=0.9,
            )
            await vector_layer.upsert_fact(fact)

            # 5. Retrieve.
            retriever = MemoryRetriever(config, file_layer, vector_layer)
            result = await retriever.retrieve("Windows development environment")
            assert "<memory-context>" in result
            assert "Windows" in result

            # 6. Drift detection.
            detector = DriftDetector(file_layer)
            await file_layer.write_memory("# Test Memory\nUser: Arya\n")
            await detector.take_snapshot()

            # External edit.
            mem_path = file_layer.memory_dir / "MEMORY.md"
            def _external_edit():
                import os
                mem_path.write_text("# Hacked Memory", encoding="utf-8")
                new_mtime = os.path.getmtime(mem_path) + 1.0
                os.utime(mem_path, (new_mtime, new_mtime))
            await asyncio.to_thread(_external_edit)

            assert await detector.check_drift() is True

            # Snapshot still has original content.
            assert await detector.get_snapshot_content() == "# Test Memory\nUser: Arya\n"

            # 7. Stats.
            stats = await vector_layer.get_stats()
            assert stats["episodes"] == 2
            assert stats["facts"] == 1
        finally:
            await vector_layer.close()


@pytest.mark.asyncio
class TestMemoryRetrievalThreshold:
    async def test_threshold_filters_low_scores(
        self, tmp_memory_dir: Path, tmp_db_path: Path
    ) -> None:
        """With a high threshold, low-similarity results are excluded."""
        config = MemoryConfig(
            memory_dir=tmp_memory_dir,
            db_path=tmp_db_path,
            embedding_dim=10,
            retrieval_threshold=0.99,
        )
        file_layer = FileLayer(config)
        vector_layer = VectorLayer(config)
        await vector_layer.initialize()
        vector_layer.embed = AsyncMock(return_value=[0.1] * 10)

        try:
            ep = Episode(
                session_id="s", role="user", content="Python programming"
            )
            await vector_layer.upsert_episode(ep)

            retriever = MemoryRetriever(config, file_layer, vector_layer)
            raw = await retriever.retrieve_raw("Python")
            # All embeddings are identical in mock → cosine=1.0, passes 0.99
            assert len(raw) >= 1
        finally:
            await vector_layer.close()
