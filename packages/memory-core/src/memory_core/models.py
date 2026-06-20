"""Pydantic v2 models for the JalaAgent memory system."""

import datetime as dt
from enum import StrEnum
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ApprovalMode(StrEnum):
    """Tool approval modes for memory operations."""

    PARANOID = "paranoid"
    NORMAL = "normal"
    YOLO = "yolo"
    CUSTOM = "custom"


# ---------------------------------------------------------------------------
# Core memory data models
# ---------------------------------------------------------------------------


class MemoryEntry(BaseModel):
    """A curated memory entry stored in MEMORY.md or injected by the agent.

    Represents a single fact, preference, or lesson that the agent wants to
    remember across sessions.  Stored as human-readable text in the file layer
    and indexed in the vector layer for semantic retrieval.
    """

    id: UUID = Field(default_factory=uuid4, description="Unique identifier")
    content: str = Field(..., min_length=1, description="The memory text")
    source: Literal["session", "manual", "dreaming"] = Field(
        default="session",
        description="Origin of the entry — session extraction, manual user write, or dreaming pipeline",
    )
    created_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC),
        description="When the entry was first created",
    )
    updated_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC),
        description="When the entry was last modified",
    )
    session_id: str | None = Field(
        default=None,
        description="Session that produced this entry (None for manual entries)",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Categorization tags for filtering",
    )
    importance: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Importance score from 0.0 (trivial) to 1.0 (critical)",
    )

    @model_validator(mode="after")
    def _ensure_updated_after_created(self) -> "MemoryEntry":
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must be >= created_at")
        return self


class Episode(BaseModel):
    """A chunk of conversation from a session transcript.

    Each episode represents one turn (user message, assistant reply, or tool
    result) stored as a searchable chunk in the vector layer.  Episodes are
    the primary input to the dreaming pipeline.
    """

    id: UUID = Field(default_factory=uuid4, description="Unique identifier")
    session_id: str = Field(..., min_length=1, description="Session that produced this episode")
    timestamp: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC),
        description="When the turn occurred",
    )
    role: Literal["user", "assistant", "tool"] = Field(
        ...,
        description="Role of the message author",
    )
    content: str = Field(..., min_length=1, description="The message text")
    tool_name: str | None = Field(
        default=None,
        description="Tool name if role is 'tool'",
    )
    metadata: dict = Field(
        default_factory=dict,
        description="Arbitrary metadata (tool args, model, token counts, etc.)",
    )


class Fact(BaseModel):
    """An atomic fact extracted and promoted by the dreaming pipeline.

    Facts are high-confidence assertions distilled from multiple episodes or
    memory entries.  They carry a confidence score and track which episodes
    contributed to their extraction.
    """

    id: UUID = Field(default_factory=uuid4, description="Unique identifier")
    content: str = Field(..., min_length=1, description="The fact text")
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confidence score from 0.0 (uncertain) to 1.0 (certain)",
    )
    source_episode_ids: list[str] = Field(
        default_factory=list,
        description="Episode IDs that contributed to this fact",
    )
    promoted_at: dt.datetime | None = Field(
        default=None,
        description="When this fact was promoted to MEMORY.md (None if not yet promoted)",
    )
    promotion_count: int = Field(
        default=0,
        ge=0,
        description="How many times this fact has been promoted across dreaming cycles",
    )

    @model_validator(mode="after")
    def _promotion_requires_timestamp(self) -> "Fact":
        if self.promotion_count > 0 and self.promoted_at is None:
            raise ValueError("promoted_at is required when promotion_count > 0")
        if self.promotion_count == 0 and self.promoted_at is not None:
            raise ValueError("promotion_count must be > 0 when promoted_at is set")
        return self


class SkillIndex(BaseModel):
    """Metadata index entry for a skill stored in the vector layer.

    Tracks when a skill's embedding was last updated so the system knows
    whether re-indexing is needed.
    """

    skill_id: str = Field(..., min_length=1, description="Unique skill identifier (slug)")
    name: str = Field(..., min_length=1, description="Human-readable skill name")
    description: str = Field(..., min_length=1, description="One-line skill description")
    content_hash: str = Field(
        ...,
        min_length=1,
        description="SHA-256 hash of the skill's SKILL.md content",
    )
    embedding_updated_at: dt.datetime | None = Field(
        default=None,
        description="When the skill's embedding was last computed",
    )


class DreamReport(BaseModel):
    """A report from one dreaming pipeline run.

    Generated after each dreaming cycle (daily by default).  Tracks how many
    signals were processed and how many facts were promoted, plus a
    human-readable diary entry.
    """

    date: dt.date = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC).date(),
        description="Date of the dreaming run",
    )
    light_sleep_signals: int = Field(
        default=0,
        ge=0,
        description="Number of new signals found in recent sessions",
    )
    rem_patterns: int = Field(
        default=0,
        ge=0,
        description="Number of cross-session patterns identified",
    )
    deep_sleep_promotions: int = Field(
        default=0,
        ge=0,
        description="Number of facts promoted to MEMORY.md",
    )
    diary_entry: str = Field(
        default="",
        description="Human-readable narrative of what was consolidated",
    )
    duration_seconds: float = Field(
        default=0.0,
        ge=0.0,
        description="Total wall-clock time for the dreaming run",
    )


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_MEMORY_DIR = Path.home() / ".jalaagent" / "memories"
_DEFAULT_DB_PATH = Path.home() / ".jalaagent" / "db" / "memory.db"


class MemoryConfig(BaseSettings):
    """Persistent configuration for the memory subsystem.

    Values are loaded from environment variables prefixed with ``JALA_MEMORY_``
    and can be overridden in ``~/.jalaagent/config.yaml`` at application level.
    """

    model_config = SettingsConfigDict(
        env_prefix="JALA_MEMORY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    memory_dir: Path = Field(
        default=_DEFAULT_MEMORY_DIR,
        description="Directory for raw memory files (MEMORY.md, USER.md, sessions/)",
    )
    db_path: Path = Field(
        default=_DEFAULT_DB_PATH,
        description="Path to the SQLite database with sqlite-vec tables",
    )
    embedding_model: str = Field(
        default="qwen3:0.6b",
        min_length=1,
        description="Ollama model name for generating embeddings",
    )
    embedding_dim: int = Field(
        default=1024,
        gt=0,
        description="Dimensionality of the embedding vectors",
    )
    embedding_base_url: str = Field(
        default="http://localhost:11434",
        min_length=1,
        description="Base URL for the Ollama embedding API",
    )
    dreaming_schedule: str = Field(
        default="0 3 * * *",
        min_length=1,
        description="Cron expression for the dreaming pipeline (default: 3 AM daily)",
    )
    dreaming_enabled: bool = Field(
        default=True,
        description="Whether the dreaming pipeline runs on schedule",
    )
    max_retrieval_results: int = Field(
        default=10,
        gt=0,
        description="Maximum number of results returned by memory retrieval",
    )
    retrieval_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Minimum cosine similarity score for retrieval results",
    )
    guardian_enabled: bool = Field(
        default=True,
        description="Whether the memory guardian runs on schedule",
    )
    guardian_schedule: str = Field(
        default="0 6 * * 0",
        min_length=1,
        description="Cron expression for memory guardian (default: Sunday 6 AM)",
    )
    guardian_auto_repair: bool = Field(
        default=True,
        description="Auto-repair minor integrity issues",
    )
    governance_enabled: bool = Field(
        default=True,
        description="Whether periodic governance rebuild runs",
    )
    governance_schedule: str = Field(
        default="0 7 * * 0",
        min_length=1,
        description="Cron expression for governance rebuild (default: Sunday 7 AM)",
    )


# ---------------------------------------------------------------------------
# Guardian + Governance models
# ---------------------------------------------------------------------------


class GuardianFinding(BaseModel):
    """A single integrity finding from a memory guardian check."""

    layer: str = Field(..., description="Memory layer: file, vector, knowledge_graph")
    severity: Literal["info", "warning", "error", "critical"] = Field(
        ..., description="Finding severity level"
    )
    category: str = Field(..., description="Finding category, e.g. orphan_embedding")
    message: str = Field(..., description="Human-readable description")
    detail: dict = Field(
        default_factory=dict, description="Machine-readable context (row IDs, counts)"
    )
    auto_repairable: bool = Field(
        default=False, description="Can this issue be auto-repaired?"
    )
    repaired: bool = Field(default=False, description="Was this issue repaired?")


class GuardianReport(BaseModel):
    """Result of a memory guardian integrity check run."""

    timestamp: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC),
    )
    findings: list[GuardianFinding] = Field(default_factory=list)
    total_checks: int = Field(default=0, description="Total checks performed")
    repair_count: int = Field(default=0, description="Number of auto-repairs applied")
    error_count: int = Field(default=0, description="Number of error/critical findings")
    health_status: Literal["healthy", "degraded", "unhealthy"] = Field(
        default="healthy",
        description="Overall health: healthy (no errors), degraded (warnings only), unhealthy (errors)",
    )
    duration_seconds: float = Field(default=0.0, ge=0.0)


class GovernanceReport(BaseModel):
    """Result of a governance rebuild run."""

    timestamp: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC),
    )
    before_stats: dict = Field(default_factory=dict)
    after_stats: dict = Field(default_factory=dict)
    rebuild_actions: list[str] = Field(default_factory=list)
    duration_seconds: float = Field(default=0.0, ge=0.0)


# ---------------------------------------------------------------------------
# Family Registry models
# ---------------------------------------------------------------------------


class RelationType(StrEnum):
    """Types of relationships between memory entries."""

    SAME_SESSION = "same_session"
    SAME_TAG = "same_tag"
    PARENT_CHILD = "parent_child"
    SEMANTIC_SIMILAR = "semantic_similar"
    KG_GROUPED = "kg_grouped"


class MemoryRelation(BaseModel):
    """A relationship between two memory entries."""

    id: UUID = Field(default_factory=uuid4)
    source_id: UUID = Field(..., description="Source entry ID")
    target_id: UUID = Field(..., description="Target entry ID")
    relation_type: RelationType = Field(..., description="Type of relationship")
    strength: float = Field(default=0.5, ge=0.0, le=1.0)
    created_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC),
    )
    metadata: dict = Field(default_factory=dict)


class FamilyTreeNode(BaseModel):
    """A node in a memory family tree."""

    entry_id: UUID = Field(..., description="Memory entry ID")
    content: str = Field(default="", description="Entry content preview")
    depth: int = Field(default=0, ge=0)
    children: list["FamilyTreeNode"] = Field(default_factory=list)
    relations: list[MemoryRelation] = Field(default_factory=list)


class FamilyTree(BaseModel):
    """A memory family tree rooted at a given entry."""

    root: FamilyTreeNode | None = None
    total_nodes: int = Field(default=0, ge=0)
    max_depth: int = Field(default=0, ge=0)


# ---------------------------------------------------------------------------
# Observability models
# ---------------------------------------------------------------------------


class LayerHealth(BaseModel):
    """Health metrics for a single memory layer."""

    layer_name: str = Field(..., description="Layer name")
    entry_count: int = Field(default=0, ge=0)
    storage_bytes: int = Field(default=0, ge=0)
    health_score: float = Field(default=0.0, ge=0.0, le=1.0)
    issues: list[str] = Field(default_factory=list)


class MemoryHealthReport(BaseModel):
    """A comprehensive memory system health report."""

    timestamp: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC),
    )
    layers: dict[str, LayerHealth] = Field(default_factory=dict)
    overall_health: float = Field(default=0.0, ge=0.0, le=1.0)
    weekly_growth: dict[str, int] = Field(default_factory=dict)
    recommendations: list[str] = Field(default_factory=list)
    duration_seconds: float = Field(default=0.0, ge=0.0)


# ---------------------------------------------------------------------------
# Re-exports and backward compatibility
# ---------------------------------------------------------------------------


class MemoryQuery(BaseModel):
    """A query against the memory system."""

    text: str = Field(..., min_length=1, description="Query text")
    max_results: int = Field(default=10, gt=0)
    threshold: float = Field(default=0.7, ge=0.0, le=1.0)


class MemorySearchResult(BaseModel):
    """A search result from memory retrieval."""

    entry_id: str = Field(..., description="ID of the matched entry")
    content: str = Field(..., description="Matched content snippet")
    score: float = Field(..., ge=0.0, description="Similarity or relevance score")
    source: str = Field(default="unknown", description="Source table or layer")


# Resolve forward references for FamilyTreeNode (children: list[FamilyTreeNode])
FamilyTreeNode.model_rebuild()

__all__ = [
    "ApprovalMode",
    "MemoryEntry",
    "Episode",
    "Fact",
    "SkillIndex",
    "DreamReport",
    "MemoryConfig",
    "MemoryQuery",
    "MemorySearchResult",
    "GuardianFinding",
    "GuardianReport",
    "GovernanceReport",
    "RelationType",
    "MemoryRelation",
    "FamilyTreeNode",
    "FamilyTree",
    "LayerHealth",
    "MemoryHealthReport",
]
