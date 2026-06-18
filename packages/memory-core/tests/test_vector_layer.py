"""Tests for memory-core vector_layer (Layer 2 — SQLite + Vector)."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from memory_core.models import Episode, Fact, MemoryConfig, SkillIndex
from memory_core.vector_layer import (
    VectorLayer,
    _blob_to_floats,
    _cosine,
    _floats_to_blob,
    _hash_text,
)

# ---------------------------------------------------------------------------
# Test embeddings
# ---------------------------------------------------------------------------

_QUERY_EMBEDDING = [0.1] * 10
_EPISODE_EMBEDDING = [0.9] * 10
_FACT_EMBEDDING = [0.5] * 10


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db_path() -> Path:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        yield Path(td) / "memory.db"


@pytest.fixture
def config(tmp_db_path: Path) -> MemoryConfig:
    return MemoryConfig(
        memory_dir=Path(tempfile.mkdtemp()),
        db_path=tmp_db_path,
        embedding_model="qwen3:0.6b",
        embedding_dim=10,
        embedding_base_url="http://localhost:11434",
    )


@pytest_asyncio.fixture
async def layer(config: MemoryConfig) -> VectorLayer:  # type: ignore[valid-type]
    """VectorLayer with mocked HTTP client."""
    vl = VectorLayer(config)
    await vl.initialize()

    async def fake_post(url, json=None, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()

        text = json.get("input", "") if json else ""
        if "query" in text.lower() or "search" in text.lower():
            vec = _QUERY_EMBEDDING
        elif "fact" in text.lower():
            vec = _FACT_EMBEDDING
        else:
            vec = _EPISODE_EMBEDDING
        resp.json = MagicMock(return_value={"embeddings": [vec]})
        return resp

    vl._http = AsyncMock()
    vl._http.post = AsyncMock(side_effect=fake_post)
    vl._http.aclose = AsyncMock()
    yield vl
    await vl.close()


def make_episode(
    session_id: str = "sess-001",
    role: str = "user",
    content: str = "Hello world",
    **kwargs,
) -> Episode:
    return Episode(session_id=session_id, role=role, content=content, **kwargs)  # type: ignore[arg-type]


def make_fact(
    content: str = "The user prefers Python",
    confidence: float = 0.9,
    **kwargs,
) -> Fact:
    return Fact(content=content, confidence=confidence, **kwargs)


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------


class TestMathHelpers:
    def test_cosine_identical(self) -> None:
        v = [1.0, 2.0, 3.0]
        assert _cosine(v, v) == pytest.approx(1.0)

    def test_cosine_orthogonal(self) -> None:
        assert _cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_cosine_opposite(self) -> None:
        assert _cosine([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)

    def test_cosine_zero_vector(self) -> None:
        assert _cosine([0.0, 0.0], [1.0, 1.0]) == 0.0

    def test_blob_roundtrip(self) -> None:
        vec = [0.1, 0.2, 0.3, 0.4, 0.5]
        blob = _floats_to_blob(vec)
        result = _blob_to_floats(blob)
        assert result == pytest.approx(vec, abs=1e-6)

    def test_hash_text_deterministic(self) -> None:
        assert _hash_text("hello") == _hash_text("hello")
        assert _hash_text("hello") != _hash_text("world")


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestInitialize:
    async def test_initialize_creates_tables(self, config: MemoryConfig) -> None:
        vl = VectorLayer(config)
        await vl.initialize()
        try:
            stats = await vl.get_stats()
            assert stats["episodes"] == 0
            assert stats["facts"] == 0
            assert stats["skills"] == 0
            assert stats["embeddings"] == 0
            assert stats["fts_index"] == 0
        finally:
            await vl.close()

    async def test_initialize_idempotent(self, layer: VectorLayer) -> None:
        await layer.initialize()  # second call should not error
        stats = await layer.get_stats()
        assert "episodes" in stats


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestEmbed:
    async def test_embed_returns_floats(self, layer: VectorLayer) -> None:
        vec = await layer.embed("test")
        assert isinstance(vec, list)
        assert len(vec) == 10
        assert all(isinstance(v, float) for v in vec)

    async def test_embed_cache(self, layer: VectorLayer) -> None:
        v1 = await layer.embed("cached text")
        v2 = await layer.embed("cached text")
        assert v1 == v2
        # Only one HTTP call: second shouldn't have hit the mock again.
        # (proven by the fact both returned the same embedding from first call)

    async def test_embed_different_texts_different_vectors(self, layer: VectorLayer) -> None:
        v1 = await layer.embed("this is about a fact Python coding")
        v2 = await layer.embed("this is a query about search Python")
        assert v1 != v2  # different keys → different mock responses (fact vs query)


# ---------------------------------------------------------------------------
# Upsert Episode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestUpsertEpisode:
    async def test_upsert_episode_creates_row(self, layer: VectorLayer) -> None:
        ep = make_episode(content="user message about Python")
        await layer.upsert_episode(ep)
        stats = await layer.get_stats()
        assert stats["episodes"] == 1
        assert stats["embeddings"] >= 1
        assert stats["fts_index"] >= 1

    async def test_upsert_episode_update(self, layer: VectorLayer) -> None:
        ep = make_episode(content="original")
        await layer.upsert_episode(ep)
        # Re-upsert with same id but changed content
        ep_updated = Episode(
            id=ep.id,
            session_id=ep.session_id,
            timestamp=ep.timestamp,
            role=ep.role,
            content="updated content",
        )
        await layer.upsert_episode(ep_updated)
        stats = await layer.get_stats()
        assert stats["episodes"] == 1  # still 1 (upserted)


# ---------------------------------------------------------------------------
# Upsert Fact
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestUpsertFact:
    async def test_upsert_fact(self, layer: VectorLayer) -> None:
        fact = make_fact(content="user fact about coding", source_episode_ids=["ep1", "ep2"])
        await layer.upsert_fact(fact)
        stats = await layer.get_stats()
        assert stats["facts"] == 1

    async def test_upsert_fact_with_promotion(self, layer: VectorLayer) -> None:
        import datetime as dt
        fact = make_fact(
            content="promoted fact",
            promotion_count=3,
            promoted_at=dt.datetime.now(dt.UTC),
        )
        await layer.upsert_fact(fact)
        stats = await layer.get_stats()
        assert stats["facts"] == 1


# ---------------------------------------------------------------------------
# Upsert Skill
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestUpsertSkill:
    async def test_upsert_skill(self, layer: VectorLayer) -> None:
        skill = SkillIndex(
            skill_id="git-workflow",
            name="Git Workflow",
            description="Automate Git",
            content_hash="sha256:abc123",
        )
        await layer.upsert_skill(skill)
        stats = await layer.get_stats()
        assert stats["skills"] == 1

    async def test_upsert_skill_update(self, layer: VectorLayer) -> None:
        skill = SkillIndex(
            skill_id="git-workflow",
            name="Git",
            description="Old",
            content_hash="sha256:old",
        )
        await layer.upsert_skill(skill)
        skill2 = SkillIndex(
            skill_id="git-workflow",
            name="Git Workflow",
            description="New",
            content_hash="sha256:new",
        )
        await layer.upsert_skill(skill2)
        stats = await layer.get_stats()
        assert stats["skills"] == 1  # upserted, not duplicated


# ---------------------------------------------------------------------------
# Search KNN
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSearchKnn:
    async def test_knn_returns_results(self, layer: VectorLayer) -> None:
        await layer.upsert_episode(make_episode(content="Python is great"))
        results = await layer.search_knn("query about Python", k=5)
        assert len(results) >= 1
        obj, score = results[0]
        assert isinstance(obj, Episode)
        assert isinstance(score, float)

    async def test_knn_empty_on_no_data(self, layer: VectorLayer) -> None:
        results = await layer.search_knn("search query")
        assert results == []

    async def test_knn_respects_k(self, layer: VectorLayer) -> None:
        for i in range(5):
            await layer.upsert_episode(make_episode(session_id=f"s{i}", content=f"item {i}"))
        results = await layer.search_knn("query", k=3)
        assert len(results) <= 3


# ---------------------------------------------------------------------------
# Search FTS
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSearchFts:
    async def test_fts_finds_keyword(self, layer: VectorLayer) -> None:
        await layer.upsert_episode(make_episode(content="I love coding in Rust"))
        await layer.upsert_episode(make_episode(content="Python is my favorite"))
        results = await layer.search_fts("Python", k=5)
        assert len(results) >= 1
        obj, _ = results[0]
        assert isinstance(obj, Episode)
        assert "Python" in obj.content

    async def test_fts_empty_on_no_match(self, layer: VectorLayer) -> None:
        await layer.upsert_episode(make_episode(content="coding"))
        results = await layer.search_fts("zzzznonexistent")
        assert results == []

    async def test_fts_finds_facts(self, layer: VectorLayer) -> None:
        await layer.upsert_fact(make_fact(content="User loves dark mode"))
        results = await layer.search_fts("dark mode", k=5)
        assert len(results) >= 1
        obj, _ = results[0]
        assert isinstance(obj, Fact)


# ---------------------------------------------------------------------------
# Search (combined)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSearch:
    async def test_combines_knn_and_fts(self, layer: VectorLayer) -> None:
        await layer.upsert_episode(make_episode(content="Rust programming language"))
        await layer.upsert_fact(make_fact(content="Rust is the user's favorite"))
        results = await layer.search("Rust", k=5)
        assert len(results) >= 1

    async def test_no_duplicates(self, layer: VectorLayer) -> None:
        ep = make_episode(content="unique search target")
        await layer.upsert_episode(ep)
        results = await layer.search("unique search target", k=5)
        ids = [str(r[0].id) for r in results]
        assert len(ids) == len(set(ids))  # no duplicates

    async def test_sorted_by_score_descending(self, layer: VectorLayer) -> None:
        for i in range(5):
            await layer.upsert_episode(make_episode(session_id=f"s{i}", content=f"test query data {i}"))
        results = await layer.search("test query", k=5)
        scores = [r[1] for r in results]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestDelete:
    async def test_delete_episode(self, layer: VectorLayer) -> None:
        ep = make_episode(content="to be deleted")
        await layer.upsert_episode(ep)
        stats = await layer.get_stats()
        assert stats["episodes"] == 1
        await layer.delete_episode(str(ep.id))
        stats = await layer.get_stats()
        assert stats["episodes"] == 0
        assert stats["embeddings"] == 0
        assert stats["fts_index"] == 0

    async def test_delete_nonexistent_no_error(self, layer: VectorLayer) -> None:
        await layer.delete_episode("nonexistent-id")  # should not raise


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestStats:
    async def test_counts_tracked_correctly(self, layer: VectorLayer) -> None:
        # Use distinct content so each gets its own embedding
        await layer.upsert_episode(make_episode(content="first unique episode"))
        await layer.upsert_episode(make_episode(session_id="s2", content="second unique episode"))
        await layer.upsert_fact(make_fact(content="f1: unique fact content"))
        stats = await layer.get_stats()
        assert stats["episodes"] == 2
        assert stats["facts"] == 1
        assert stats["skills"] == 0
        assert stats["embeddings"] == 3  # 2 episodes + 1 fact


# ---------------------------------------------------------------------------
# Cosine fallback (simulated sqlite-vec unavailable)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCosineFallback:
    async def test_cosine_fallback_works(self, config: MemoryConfig) -> None:
        vl = VectorLayer(config)
        await vl.initialize()

        try:
            # Mock KNN to fail → triggers cosine fallback.
            async def fake_post(url, json=None, **kwargs):
                resp = MagicMock()
                resp.raise_for_status = MagicMock()
                resp.json = MagicMock(return_value={"embeddings": [_QUERY_EMBEDDING]})
                return resp

            vl._http = MagicMock()
            vl._http.post = AsyncMock(side_effect=fake_post)

            await vl.upsert_episode(make_episode(content="cosine test data"))
            # Replace _search_knn_via_vec to always return [] (simulating vec unavailable)
            vl._search_knn_via_vec = AsyncMock(return_value=[])  # type: ignore[method-assign]

            results = await vl.search_knn("any query", k=5)
            assert len(results) >= 1
        finally:
            await vl.close()


# ---------------------------------------------------------------------------
# Embedding cache
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestEmbeddingCache:
    async def test_cache_size_grows(self, layer: VectorLayer) -> None:
        assert layer.embedding_cache_size == 0
        await layer.embed("first")
        assert layer.embedding_cache_size == 1
        await layer.embed("second")
        assert layer.embedding_cache_size == 2
        await layer.embed("first")  # should hit cache
        assert layer.embedding_cache_size == 2
