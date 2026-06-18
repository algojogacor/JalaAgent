"""Unit tests for memory-core pydantic v2 models."""

import os
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from memory_core.models import (
    ApprovalMode,
    DreamReport,
    Episode,
    Fact,
    MemoryConfig,
    MemoryEntry,
    MemoryQuery,
    MemorySearchResult,
    SkillIndex,
)
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# MemoryEntry
# ---------------------------------------------------------------------------


class TestMemoryEntry:
    """Tests for MemoryEntry — curated memory entries."""

    def test_defaults(self) -> None:
        entry = MemoryEntry(content="The user prefers dark mode")
        assert isinstance(entry.id, type(entry.id))
        assert entry.source == "session"
        assert entry.importance == 0.5
        assert entry.tags == []
        assert entry.session_id is None
        assert isinstance(entry.created_at, datetime)
        assert isinstance(entry.updated_at, datetime)

    def test_explicit_source(self) -> None:
        for src in ("session", "manual", "dreaming"):
            entry = MemoryEntry(content="test", source=src)  # type: ignore[arg-type]
            assert entry.source == src

    def test_source_rejects_invalid(self) -> None:
        with pytest.raises(ValidationError):
            MemoryEntry(content="test", source="unknown")  # type: ignore[arg-type]

    def test_importance_bounds(self) -> None:
        # Lower bound
        entry = MemoryEntry(content="test", importance=0.0)
        assert entry.importance == 0.0
        # Upper bound
        entry = MemoryEntry(content="test", importance=1.0)
        assert entry.importance == 1.0

    def test_importance_rejects_negative(self) -> None:
        with pytest.raises(ValidationError):
            MemoryEntry(content="test", importance=-0.1)

    def test_importance_rejects_above_one(self) -> None:
        with pytest.raises(ValidationError):
            MemoryEntry(content="test", importance=1.01)

    def test_content_min_length(self) -> None:
        with pytest.raises(ValidationError):
            MemoryEntry(content="")

    def test_tags_as_list_of_strings(self) -> None:
        entry = MemoryEntry(content="test", tags=["python", "preference"])
        assert entry.tags == ["python", "preference"]

    def test_session_id_optional(self) -> None:
        entry = MemoryEntry(content="test", session_id="sess-001")
        assert entry.session_id == "sess-001"

    def test_updated_at_after_created_at(self) -> None:
        past = datetime(2020, 1, 1, tzinfo=UTC)
        future = datetime(2025, 12, 31, tzinfo=UTC)
        entry = MemoryEntry(content="test", created_at=past, updated_at=future)
        assert entry.updated_at >= entry.created_at

    def test_updated_at_before_created_at_rejected(self) -> None:
        past = datetime(2020, 1, 1, tzinfo=UTC)
        future = datetime(2025, 12, 31, tzinfo=UTC)
        with pytest.raises(ValidationError):
            MemoryEntry(content="test", created_at=future, updated_at=past)


# ---------------------------------------------------------------------------
# Episode
# ---------------------------------------------------------------------------


class TestEpisode:
    """Tests for Episode — session transcript chunks."""

    def test_defaults(self) -> None:
        episode = Episode(session_id="sess-001", role="user", content="Hello world")
        assert isinstance(episode.id, type(episode.id))
        assert episode.tool_name is None
        assert episode.metadata == {}
        assert isinstance(episode.timestamp, datetime)

    def test_all_roles(self) -> None:
        for role in ("user", "assistant", "tool"):
            episode = Episode(session_id="s", role=role, content="test")  # type: ignore[arg-type]
            assert episode.role == role

    def test_role_rejects_invalid(self) -> None:
        with pytest.raises(ValidationError):
            Episode(session_id="s", role="system", content="test")  # type: ignore[arg-type]

    def test_session_id_required(self) -> None:
        with pytest.raises(ValidationError):
            Episode(role="user", content="test")  # type: ignore[call-arg]

    def test_tool_name_settable(self) -> None:
        episode = Episode(
            session_id="sess-001",
            role="tool",
            content="result",
            tool_name="read_file",
        )
        assert episode.tool_name == "read_file"

    def test_metadata_dict(self) -> None:
        episode = Episode(
            session_id="sess-001",
            role="assistant",
            content="response",
            metadata={"model": "claude-sonnet-4-6", "tokens": 150},
        )
        assert episode.metadata["model"] == "claude-sonnet-4-6"
        assert episode.metadata["tokens"] == 150


# ---------------------------------------------------------------------------
# Fact
# ---------------------------------------------------------------------------


class TestFact:
    """Tests for Fact — atomic facts from the dreaming pipeline."""

    def test_defaults(self) -> None:
        fact = Fact(content="User prefers Python over JavaScript")
        assert isinstance(fact.id, type(fact.id))
        assert fact.confidence == 0.5
        assert fact.source_episode_ids == []
        assert fact.promoted_at is None
        assert fact.promotion_count == 0

    def test_confidence_bounds(self) -> None:
        assert Fact(content="test", confidence=0.0).confidence == 0.0
        assert Fact(content="test", confidence=1.0).confidence == 1.0

    def test_confidence_rejects_negative(self) -> None:
        with pytest.raises(ValidationError):
            Fact(content="test", confidence=-0.01)

    def test_confidence_rejects_above_one(self) -> None:
        with pytest.raises(ValidationError):
            Fact(content="test", confidence=1.01)

    def test_source_episode_ids(self) -> None:
        fact = Fact(
            content="test",
            source_episode_ids=["ep-001", "ep-002", "ep-003"],
        )
        assert len(fact.source_episode_ids) == 3

    def test_promotion_count_ge_zero(self) -> None:
        with pytest.raises(ValidationError):
            Fact(content="test", promotion_count=-1)

    def test_promoted_requires_count(self) -> None:
        """promotion_count must be > 0 when promoted_at is set."""
        now = datetime.now(UTC)
        with pytest.raises(ValidationError):
            Fact(content="test", promoted_at=now, promotion_count=0)

    def test_count_requires_promoted_at(self) -> None:
        """promoted_at must be set when promotion_count > 0."""
        with pytest.raises(ValidationError):
            Fact(content="test", promotion_count=3, promoted_at=None)

    def test_valid_promotion(self) -> None:
        now = datetime.now(UTC)
        fact = Fact(content="test", promotion_count=2, promoted_at=now)
        assert fact.promotion_count == 2
        assert fact.promoted_at == now


# ---------------------------------------------------------------------------
# SkillIndex
# ---------------------------------------------------------------------------


class TestSkillIndex:
    """Tests for SkillIndex — skill metadata in the vector layer."""

    def test_required_fields(self) -> None:
        skill = SkillIndex(
            skill_id="git-workflow",
            name="Git Workflow",
            description="Automate Git branching, commits, and PRs",
            content_hash="sha256:abc123def456",
        )
        assert skill.skill_id == "git-workflow"
        assert skill.name == "Git Workflow"
        assert skill.description == "Automate Git branching, commits, and PRs"
        assert skill.content_hash == "sha256:abc123def456"
        assert skill.embedding_updated_at is None

    def test_embedding_updated_at_settable(self) -> None:
        now = datetime.now(UTC)
        skill = SkillIndex(
            skill_id="s",
            name="n",
            description="d",
            content_hash="sha256:abc",
            embedding_updated_at=now,
        )
        assert skill.embedding_updated_at == now

    def test_content_hash_required(self) -> None:
        with pytest.raises(ValidationError):
            SkillIndex(skill_id="s", name="n", description="d")  # type: ignore[call-arg]

    def test_name_required(self) -> None:
        with pytest.raises(ValidationError):
            SkillIndex(
                skill_id="s",
                description="d",
                content_hash="sha256:abc",
            )  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# DreamReport
# ---------------------------------------------------------------------------


class TestDreamReport:
    """Tests for DreamReport — dreaming pipeline run report."""

    def test_defaults(self) -> None:
        report = DreamReport(diary_entry="All quiet on the memory front.")
        assert isinstance(report.date, date)
        assert report.light_sleep_signals == 0
        assert report.rem_patterns == 0
        assert report.deep_sleep_promotions == 0
        assert report.duration_seconds == 0.0

    def test_full_report(self) -> None:
        report = DreamReport(
            date=date(2026, 6, 18),
            light_sleep_signals=42,
            rem_patterns=7,
            deep_sleep_promotions=3,
            diary_entry="Consolidated 3 facts about code preferences.",
            duration_seconds=12.5,
        )
        assert report.light_sleep_signals == 42
        assert report.rem_patterns == 7
        assert report.deep_sleep_promotions == 3
        assert report.diary_entry == "Consolidated 3 facts about code preferences."
        assert report.duration_seconds == 12.5

    def test_signals_ge_zero(self) -> None:
        with pytest.raises(ValidationError):
            DreamReport(light_sleep_signals=-1)

    def test_patterns_ge_zero(self) -> None:
        with pytest.raises(ValidationError):
            DreamReport(rem_patterns=-1)

    def test_promotions_ge_zero(self) -> None:
        with pytest.raises(ValidationError):
            DreamReport(deep_sleep_promotions=-1)

    def test_duration_seconds_ge_zero(self) -> None:
        with pytest.raises(ValidationError):
            DreamReport(diary_entry="test", duration_seconds=-0.1)

    def test_date_defaults_to_today(self) -> None:
        report = DreamReport(diary_entry="test")
        today = datetime.now(UTC).date()
        assert report.date == today


# ---------------------------------------------------------------------------
# ApprovalMode
# ---------------------------------------------------------------------------


class TestApprovalMode:
    """Tests for ApprovalMode enum."""

    def test_all_values(self) -> None:
        assert ApprovalMode.PARANOID == "paranoid"
        assert ApprovalMode.NORMAL == "normal"
        assert ApprovalMode.YOLO == "yolo"
        assert ApprovalMode.CUSTOM == "custom"

    def test_from_string(self) -> None:
        assert ApprovalMode("paranoid") == ApprovalMode.PARANOID
        assert ApprovalMode("normal") == ApprovalMode.NORMAL
        assert ApprovalMode("yolo") == ApprovalMode.YOLO
        assert ApprovalMode("custom") == ApprovalMode.CUSTOM

    def test_rejects_unknown(self) -> None:
        with pytest.raises(ValueError):
            ApprovalMode("unknown")

    def test_is_str_enum(self) -> None:
        assert ApprovalMode.NORMAL == "normal"
        assert isinstance(ApprovalMode.NORMAL, str)


# ---------------------------------------------------------------------------
# MemoryConfig
# ---------------------------------------------------------------------------


class TestMemoryConfig:
    """Tests for MemoryConfig — pydantic BaseSettings."""

    def test_defaults(self) -> None:
        cfg = MemoryConfig()
        assert cfg.memory_dir == Path.home() / ".jalaagent" / "memories"
        assert cfg.db_path == Path.home() / ".jalaagent" / "db" / "memory.db"
        assert cfg.embedding_model == "qwen3:0.6b"
        assert cfg.embedding_dim == 1024
        assert cfg.embedding_base_url == "http://localhost:11434"
        assert cfg.dreaming_schedule == "0 3 * * *"
        assert cfg.dreaming_enabled is True
        assert cfg.max_retrieval_results == 10
        assert cfg.retrieval_threshold == 0.7

    def test_embedding_dim_gt_zero(self) -> None:
        with pytest.raises(ValidationError):
            MemoryConfig(embedding_dim=0)

    def test_retrieval_threshold_bounds(self) -> None:
        assert MemoryConfig(retrieval_threshold=0.0).retrieval_threshold == 0.0
        assert MemoryConfig(retrieval_threshold=1.0).retrieval_threshold == 1.0
        with pytest.raises(ValidationError):
            MemoryConfig(retrieval_threshold=-0.1)
        with pytest.raises(ValidationError):
            MemoryConfig(retrieval_threshold=1.01)

    def test_max_retrieval_results_gt_zero(self) -> None:
        with pytest.raises(ValidationError):
            MemoryConfig(max_retrieval_results=0)

    def test_env_var_override(self) -> None:
        os.environ["JALA_MEMORY_EMBEDDING_DIM"] = "2048"
        os.environ["JALA_MEMORY_DREAMING_ENABLED"] = "false"
        os.environ["JALA_MEMORY_MAX_RETRIEVAL_RESULTS"] = "25"
        try:
            cfg = MemoryConfig()
            assert cfg.embedding_dim == 2048
            assert cfg.dreaming_enabled is False
            assert cfg.max_retrieval_results == 25
        finally:
            del os.environ["JALA_MEMORY_EMBEDDING_DIM"]
            del os.environ["JALA_MEMORY_DREAMING_ENABLED"]
            del os.environ["JALA_MEMORY_MAX_RETRIEVAL_RESULTS"]

    def test_env_var_memory_dir(self) -> None:
        test_path = "/tmp/test_memories"
        os.environ["JALA_MEMORY_MEMORY_DIR"] = test_path
        try:
            cfg = MemoryConfig()
            assert cfg.memory_dir == Path(test_path)
        finally:
            del os.environ["JALA_MEMORY_MEMORY_DIR"]


# ---------------------------------------------------------------------------
# MemoryQuery & MemorySearchResult
# ---------------------------------------------------------------------------


class TestMemoryQuery:
    """Tests for MemoryQuery — search query model."""

    def test_defaults(self) -> None:
        query = MemoryQuery(text="user preferences")
        assert query.text == "user preferences"
        assert query.max_results == 10
        assert query.threshold == 0.7

    def test_max_results_gt_zero(self) -> None:
        with pytest.raises(ValidationError):
            MemoryQuery(text="test", max_results=0)

    def test_threshold_bounds(self) -> None:
        assert MemoryQuery(text="test", threshold=0.0).threshold == 0.0
        assert MemoryQuery(text="test", threshold=1.0).threshold == 1.0
        with pytest.raises(ValidationError):
            MemoryQuery(text="test", threshold=-0.1)
        with pytest.raises(ValidationError):
            MemoryQuery(text="test", threshold=1.01)


class TestMemorySearchResult:
    """Tests for MemorySearchResult — retrieval result model."""

    def test_required_fields(self) -> None:
        result = MemorySearchResult(
            entry_id="mem-001",
            content="The user codes in Python.",
            score=0.92,
        )
        assert result.entry_id == "mem-001"
        assert result.content == "The user codes in Python."
        assert result.score == 0.92
        assert result.source == "unknown"

    def test_source_field(self) -> None:
        result = MemorySearchResult(
            entry_id="fact-002",
            content="Always uses type hints.",
            score=0.85,
            source="facts",
        )
        assert result.source == "facts"

    def test_score_ge_zero(self) -> None:
        with pytest.raises(ValidationError):
            MemorySearchResult(entry_id="x", content="x", score=-0.1)
