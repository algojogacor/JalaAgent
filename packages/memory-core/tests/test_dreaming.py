"""Tests for memory-core dreaming pipeline (Layer 3)."""

import asyncio
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from memory_core.dreaming import (
    DreamingPipeline,
    _format_fact_markdown,
    _make_extraction_prompt,
    _sha1,
)
from memory_core.file_layer import FileLayer
from memory_core.models import DreamReport, Episode, Fact, MemoryConfig
from memory_core.vector_layer import VectorLayer

# ---------------------------------------------------------------------------
# Mock dependencies
# ---------------------------------------------------------------------------


class MockLLMAdapter:
    """Returns a fixed JSON array of facts."""

    def __init__(self, facts: list[dict] | None = None) -> None:
        self._facts = facts or [
            {"content": "User prefers Python over JavaScript.", "confidence": 0.92},
            {"content": "User develops on Windows 11 with WSL2.", "confidence": 0.88},
        ]
        self.prompts: list[str] = []

    async def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return json.dumps(self._facts)


class AutoApproveCallback:
    """Approves all facts (YOLO mode)."""

    def __init__(self) -> None:
        self.calls: list[list[Fact]] = []

    async def request_approval(self, facts: list[Fact]) -> list[str]:
        self.calls.append(facts)
        return [str(f.id) for f in facts]


class SelectiveApproveCallback:
    """Approves only facts whose content contains a given keyword."""

    def __init__(self, keyword: str) -> None:
        self.keyword = keyword
        self.calls: list[list[Fact]] = []

    async def request_approval(self, facts: list[Fact]) -> list[str]:
        self.calls.append(facts)
        return [str(f.id) for f in facts if self.keyword in f.content]


class FailingLLMAdapter:
    """Simulates an LLM error."""

    async def generate(self, prompt: str) -> str:
        raise RuntimeError("LLM unavailable")


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


@pytest_asyncio.fixture
async def vector_layer(config: MemoryConfig) -> VectorLayer:
    """VectorLayer with actual db (no embedding needed for dreaming tests)."""
    # We use a real db because dreaming doesn't call embed directly —
    # it only calls upsert_fact which does embed, so we need to mock that.
    vl = VectorLayer(config)
    await vl.initialize()
    # Mock embed to return a dummy vector (avoid HTTP calls).
    vl.embed = lambda text: asyncio.coroutine(lambda: [0.1] * 10)()  # type: ignore[assignment]
    async def _noop_embed_and_store(*args, **kwargs):
        pass
    vl._embed_and_store = _noop_embed_and_store  # type: ignore[assignment]
    async def _noop_fts(*args, **kwargs):
        pass
    vl._index_fts = _noop_fts  # type: ignore[assignment]
    yield vl
    await vl.close()


@pytest.fixture
def llm() -> MockLLMAdapter:
    return MockLLMAdapter()


@pytest.fixture
def approval() -> AutoApproveCallback:
    return AutoApproveCallback()


@pytest.fixture
def pipeline(
    config: MemoryConfig,
    file_layer: FileLayer,
    vector_layer: VectorLayer,
    llm: MockLLMAdapter,
    approval: AutoApproveCallback,
) -> DreamingPipeline:
    return DreamingPipeline(config, file_layer, vector_layer, llm, approval)


def make_episode(
    session_id: str = "sess-001",
    role: str = "user",
    content: str = "Hello world",
    ts: datetime | None = None,
) -> Episode:
    return Episode(
        session_id=session_id,
        role=role,  # type: ignore[arg-type]
        content=content,
        timestamp=ts or datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_sha1_deterministic(self) -> None:
        assert _sha1("hello") == _sha1("hello")
        assert _sha1("hello") != _sha1("world")

    def test_format_fact_markdown(self) -> None:
        now = datetime(2026, 6, 18, 12, 0, 0, tzinfo=UTC)
        fact = Fact(
            content="User prefers dark mode.",
            confidence=0.95,
            promotion_count=2,
            promoted_at=now,
        )
        md = _format_fact_markdown(fact)
        assert "User prefers dark mode" in md
        assert "0.95" in md
        assert "2026-06-18" in md

    def test_make_extraction_prompt(self) -> None:
        episodes = [
            make_episode(content="I use Python daily"),
            make_episode(role="assistant", content="Noted!"),
        ]
        prompt = _make_extraction_prompt(episodes)
        assert "I use Python daily" in prompt
        assert "JSON" in prompt


# ---------------------------------------------------------------------------
# Light Sleep
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestLightSleep:
    async def test_no_sessions(self, pipeline: DreamingPipeline) -> None:
        episodes = await pipeline._light_sleep(
            datetime.now(UTC)
        )
        assert episodes == []

    async def test_finds_recent_episodes(
        self, pipeline: DreamingPipeline, file_layer: FileLayer
    ) -> None:
        old = datetime(2020, 1, 1, tzinfo=UTC)
        recent = datetime(2026, 6, 18, tzinfo=UTC)

        await file_layer.append_session(make_episode("s1", ts=old))
        await file_layer.append_session(make_episode("s1", ts=recent))
        await file_layer.append_session(make_episode("s2", ts=recent))

        # Query since 2025-01-01 — should get the 2 recent ones.
        since = datetime(2025, 1, 1, tzinfo=UTC)
        episodes = await pipeline._light_sleep(since)
        assert len(episodes) == 2

    async def test_chronological_order(
        self, pipeline: DreamingPipeline, file_layer: FileLayer
    ) -> None:
        t1 = datetime(2026, 6, 17, tzinfo=UTC)
        t2 = datetime(2026, 6, 18, tzinfo=UTC)

        await file_layer.append_session(make_episode("s1", ts=t2))
        await file_layer.append_session(make_episode("s1", ts=t1))

        since = datetime(2026, 1, 1, tzinfo=UTC)
        episodes = await pipeline._light_sleep(since)
        assert episodes[0].timestamp <= episodes[1].timestamp


# ---------------------------------------------------------------------------
# REM Sleep
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestREMSleep:
    async def test_extracts_facts(
        self, pipeline: DreamingPipeline, file_layer: FileLayer
    ) -> None:
        episodes = [
            make_episode(content="I love Python"),
            make_episode(content="VS Code is my editor"),
        ]
        facts = await pipeline._rem_sleep(episodes)
        assert len(facts) == 2  # from MockLLMAdapter defaults
        for f in facts:
            assert isinstance(f, Fact)
            assert f.confidence > 0.5
            # Source episode IDs attached.
            assert len(f.source_episode_ids) == 2

    async def test_empty_episodes(self, pipeline: DreamingPipeline) -> None:
        facts = await pipeline._rem_sleep([])
        assert facts == []

    async def test_llm_failure_graceful(
        self,
        config: MemoryConfig,
        file_layer: FileLayer,
        vector_layer: VectorLayer,
        approval: AutoApproveCallback,
    ) -> None:
        bad_llm = FailingLLMAdapter()
        pl = DreamingPipeline(config, file_layer, vector_layer, bad_llm, approval)
        episodes = [make_episode(content="test")]
        facts = await pl._rem_sleep(episodes)
        assert facts == []

    async def test_parse_facts_markdown_fence(self, pipeline: DreamingPipeline) -> None:
        raw = '```json\n[{"content": "Fact 1", "confidence": 0.9}]\n```'
        facts = pipeline._parse_facts(raw)
        assert len(facts) == 1
        assert facts[0].content == "Fact 1"

    async def test_parse_facts_no_marks(self, pipeline: DreamingPipeline) -> None:
        raw = '[{"content": "Plain fact", "confidence": 0.75}]'
        facts = pipeline._parse_facts(raw)
        assert len(facts) == 1
        assert facts[0].confidence == 0.75

    async def test_parse_facts_clamps_confidence(
        self, pipeline: DreamingPipeline
    ) -> None:
        raw = '[{"content": "Overconfident", "confidence": 1.5}]'
        facts = pipeline._parse_facts(raw)
        assert facts[0].confidence == 1.0

        raw2 = '[{"content": "Underconfident", "confidence": -0.5}]'
        facts2 = pipeline._parse_facts(raw2)
        assert facts2[0].confidence == 0.0

    async def test_parse_facts_skips_invalid(
        self, pipeline: DreamingPipeline
    ) -> None:
        raw = '[{"content": "", "confidence": 0.5}, {"content": "Good", "confidence": 0.8}]'
        facts = pipeline._parse_facts(raw)
        assert len(facts) == 1
        assert facts[0].content == "Good"


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


class TestDeduplicate:
    def test_removes_duplicates(self) -> None:
        f1 = Fact(content="User likes Python", confidence=0.8)
        f2 = Fact(content="User likes Python", confidence=0.9)
        result = DreamingPipeline._deduplicate([f1, f2])
        assert len(result) == 1
        assert result[0].confidence == 0.9  # keeps higher

    def test_merges_source_ids(self) -> None:
        f1 = Fact(
            content="User likes Python",
            confidence=0.8,
            source_episode_ids=["ep1"],
        )
        f2 = Fact(
            content="User likes Python",
            confidence=0.7,
            source_episode_ids=["ep2"],
        )
        result = DreamingPipeline._deduplicate([f1, f2])
        assert len(result) == 1
        assert set(result[0].source_episode_ids) == {"ep1", "ep2"}

    def test_keeps_unique(self) -> None:
        f1 = Fact(content="A", confidence=0.8)
        f2 = Fact(content="B", confidence=0.7)
        result = DreamingPipeline._deduplicate([f1, f2])
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Deep Sleep
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestDeepSleep:
    async def test_filters_by_confidence(self, pipeline: DreamingPipeline) -> None:
        facts = [
            Fact(content="High confidence", confidence=0.95),
            Fact(content="Medium confidence", confidence=0.75),
            Fact(content="Low confidence", confidence=0.5),
            Fact(content="Very low", confidence=0.3),
        ]
        candidates = await pipeline._deep_sleep(facts)
        assert len(candidates) == 2
        assert all(f.confidence >= 0.7 for f in candidates)

    async def test_sorted_descending(self, pipeline: DreamingPipeline) -> None:
        facts = [
            Fact(content="A", confidence=0.7),
            Fact(content="B", confidence=0.99),
            Fact(content="C", confidence=0.85),
        ]
        candidates = await pipeline._deep_sleep(facts)
        # Sorted by confidence descending.
        assert candidates[0].confidence == 0.99
        assert candidates[-1].confidence == 0.7


# ---------------------------------------------------------------------------
# Promotion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestPromoteFacts:
    async def test_promotes_approved_facts(
        self, pipeline: DreamingPipeline, file_layer: FileLayer
    ) -> None:
        await file_layer.write_memory("Existing memory\n")
        fact = Fact(content="New fact about user", confidence=0.92)
        count = await pipeline._promote_facts([fact])
        assert count == 1
        assert fact.promotion_count == 1
        assert fact.promoted_at is not None
        # Check MEMORY.md now contains the new fact.
        memory = await file_layer.read_memory()
        assert "New fact about user" in memory
        assert "Existing memory" in memory  # preserved

    async def test_selective_approval(
        self,
        config: MemoryConfig,
        file_layer: FileLayer,
        vector_layer: VectorLayer,
        llm: MockLLMAdapter,
    ) -> None:
        approval = SelectiveApproveCallback("Python")
        pl = DreamingPipeline(config, file_layer, vector_layer, llm, approval)
        facts = [
            Fact(content="User likes Python", confidence=0.9),
            Fact(content="User likes JavaScript", confidence=0.85),
        ]
        count = await pl._promote_facts(facts)
        assert count == 1

    async def test_no_facts(self, pipeline: DreamingPipeline) -> None:
        count = await pipeline._promote_facts([])
        assert count == 0


# ---------------------------------------------------------------------------
# Full pipeline (run)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestFullPipeline:
    async def test_run_produces_report(
        self, pipeline: DreamingPipeline, file_layer: FileLayer
    ) -> None:
        # Add some session data first.
        await file_layer.append_session(
            make_episode(content="I write all code in Python")
        )
        await file_layer.append_session(
            make_episode(content="My IDE is VS Code")
        )

        report = await pipeline.run()
        assert isinstance(report, DreamReport)
        assert report.light_sleep_signals == 2
        assert report.rem_patterns >= 1
        assert report.deep_sleep_promotions >= 1
        assert report.duration_seconds > 0.0
        assert len(report.diary_entry) > 0

    async def test_run_with_no_sessions(
        self, pipeline: DreamingPipeline
    ) -> None:
        report = await pipeline.run()
        assert report.light_sleep_signals == 0
        assert report.rem_patterns == 0
        assert report.deep_sleep_promotions == 0

    async def test_run_writes_diary(
        self, pipeline: DreamingPipeline, file_layer: FileLayer
    ) -> None:
        await file_layer.append_session(make_episode(content="test"))
        await pipeline.run()
        diary_path = pipeline._config.memory_dir / "dream-diary.md"
        assert diary_path.exists()
        content = diary_path.read_text(encoding="utf-8")
        assert "Dream Report" in content

    async def test_last_run_updated(
        self, pipeline: DreamingPipeline, file_layer: FileLayer
    ) -> None:
        assert pipeline.last_run is None
        await file_layer.append_session(make_episode(content="test"))
        await pipeline.run()
        assert pipeline.last_run is not None

    async def test_run_idempotent(
        self, pipeline: DreamingPipeline, file_layer: FileLayer
    ) -> None:
        """Second run only picks up episodes since the first run."""
        await file_layer.append_session(make_episode(content="batch 1"))
        r1 = await pipeline.run()
        assert r1.light_sleep_signals == 1

        # No new episodes → second run should have 0 signals.
        r2 = await pipeline.run()
        assert r2.light_sleep_signals == 0


# ---------------------------------------------------------------------------
# Diary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestDiary:
    async def test_build_diary_entry(self) -> None:
        facts = [
            Fact(content="User prefers Python", confidence=0.95),
            Fact(content="User uses VS Code", confidence=0.82),
        ]
        entry = DreamingPipeline._build_diary_entry(10, 5, facts, 2)
        assert "10 new episodes" in entry
        assert "5 patterns" in entry
        assert "2 facts written" in entry

    async def test_write_diary_prepends(
        self, pipeline: DreamingPipeline
    ) -> None:
        report = DreamReport(
            light_sleep_signals=3,
            rem_patterns=1,
            deep_sleep_promotions=1,
            diary_entry="## Dream Report — First run",
            duration_seconds=1.0,
        )
        await pipeline._write_diary(report)
        diary_path = pipeline._config.memory_dir / "dream-diary.md"
        content = diary_path.read_text(encoding="utf-8")
        assert "First run" in content

        # Write a second diary entry.
        report2 = DreamReport(
            light_sleep_signals=0,
            rem_patterns=0,
            deep_sleep_promotions=0,
            diary_entry="## Dream Report — Second run",
            duration_seconds=0.5,
        )
        await pipeline._write_diary(report2)
        content2 = diary_path.read_text(encoding="utf-8")
        # Most recent should appear first (prepended).
        assert content2.index("Second run") < content2.index("First run")


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestProperties:
    def test_last_run_initially_none(
        self,
        config: MemoryConfig,
        file_layer: FileLayer,
        vector_layer: VectorLayer,
        llm: MockLLMAdapter,
        approval: AutoApproveCallback,
    ) -> None:
        pl = DreamingPipeline(config, file_layer, vector_layer, llm, approval)
        assert pl.last_run is None
