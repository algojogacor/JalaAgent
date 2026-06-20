"""Memory Observability — centralized metrics and health reporting.

Collects stats from all memory layers, computes health scores, tracks growth
trends via snapshots, and generates recommendations.
"""

import asyncio
import datetime as dt
import json
import logging
import time
from pathlib import Path
from typing import Protocol

from memory_core.models import LayerHealth, MemoryHealthReport

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


class FileLayerProtocol(Protocol):
    """Interface for the file layer needed by observability."""

    async def get_storage_stats(self) -> dict: ...


class VectorLayerProtocol(Protocol):
    """Interface for the vector layer needed by observability."""

    async def get_storage_stats(self) -> dict: ...


class KnowledgeGraphProtocol(Protocol):
    """Interface for the knowledge graph needed by observability."""

    async def get_storage_stats(self) -> dict: ...


class FamilyRegistryProtocol(Protocol):
    """Interface for the family registry needed by observability."""

    async def get_stats(self) -> dict: ...


# ---------------------------------------------------------------------------
# MemoryObservability
# ---------------------------------------------------------------------------


class MemoryObservability:
    """Centralized memory system health monitor.

    Collects metrics from FileLayer, VectorLayer, KnowledgeGraph, and
    (optionally) MemoryFamilyRegistry.  Computes per-layer health scores,
    tracks weekly growth via snapshot comparison, and surfaces
    recommendations.

    Usage::

        obs = MemoryObservability(file_layer, vector_layer, knowledge_graph, family_registry)
        report = await obs.generate_report()
        print(f"Overall health: {report.overall_health:.0%}")
        for rec in report.recommendations:
            print(f"  - {rec}")
    """

    _STATS_PATH = Path.home() / ".jalaagent" / "db" / "memory_stats.json"

    def __init__(
        self,
        file_layer: FileLayerProtocol,
        vector_layer: VectorLayerProtocol,
        knowledge_graph: KnowledgeGraphProtocol | None = None,
        family_registry: FamilyRegistryProtocol | None = None,
    ) -> None:
        self._file = file_layer
        self._vector = vector_layer
        self._kg = knowledge_graph
        self._family = family_registry

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate_report(self) -> MemoryHealthReport:
        """Generate a full memory health report."""
        start = time.monotonic()
        layers: dict[str, LayerHealth] = {}
        recommendations: list[str] = []

        # Collect stats from each layer
        file_stats = await self._file.get_storage_stats()
        vector_stats = await self._vector.get_storage_stats()
        kg_stats = await self._kg.get_storage_stats() if self._kg else {}
        family_stats = await self._family.get_stats() if self._family else {}

        # File layer health
        file_health = self._score_file_layer(file_stats, recommendations)
        layers["file"] = LayerHealth(
            layer_name="File Layer",
            entry_count=file_stats.get("session_count", 0),
            storage_bytes=file_stats.get("memory_md_bytes", 0)
            + file_stats.get("session_files_bytes", 0),
            health_score=file_health,
            issues=self._file_issues(file_stats),
        )

        # Vector layer health
        vec_health = self._score_vector_layer(vector_stats, recommendations)
        layers["vector"] = LayerHealth(
            layer_name="Vector Layer",
            entry_count=vector_stats.get("episodes", 0),
            storage_bytes=vector_stats.get("db_size_bytes", 0),
            health_score=vec_health,
            issues=self._vector_issues(vector_stats),
        )

        # Knowledge graph health
        if kg_stats:
            kg_health = self._score_kg_layer(kg_stats, recommendations)
            layers["knowledge_graph"] = LayerHealth(
                layer_name="Knowledge Graph",
                entry_count=kg_stats.get("entities", 0),
                storage_bytes=kg_stats.get("db_size_bytes", 0),
                health_score=kg_health,
                issues=self._kg_issues(kg_stats),
            )

        # Family registry health
        if family_stats:
            fam_health = 0.8  # baseline — family registry is optional
            total_rel = family_stats.get("total_relations", 0)
            if total_rel > 0:
                fam_health = min(1.0, 0.5 + (total_rel / 100) * 0.5)
            layers["family"] = LayerHealth(
                layer_name="Family Registry",
                entry_count=total_rel,
                storage_bytes=0,
                health_score=fam_health,
                issues=[] if total_rel > 0 else ["No relations built yet — run dreaming pipeline"],
            )

        # Overall health (weighted)
        weights = {"file": 0.2, "vector": 0.4, "knowledge_graph": 0.2, "family": 0.2}
        overall = sum(
            layers[name].health_score * weights.get(name, 0.0)
            for name in layers
        )
        overall = min(1.0, max(0.0, overall))

        # Growth trends
        weekly_growth = await self._compute_growth(vector_stats, kg_stats)

        # Persist snapshot
        await self._save_snapshot(vector_stats, kg_stats)

        duration = time.monotonic() - start
        return MemoryHealthReport(
            timestamp=dt.datetime.now(dt.UTC),
            layers=layers,
            overall_health=round(overall, 4),
            weekly_growth=weekly_growth,
            recommendations=recommendations,
            duration_seconds=duration,
        )

    # ------------------------------------------------------------------
    # Health scoring
    # ------------------------------------------------------------------

    @staticmethod
    def _score_file_layer(stats: dict, recs: list[str]) -> float:
        score = 0.0
        if stats.get("memory_md_bytes", 0) > 0:
            score += 0.5
        if stats.get("session_count", 0) > 0:
            score += 0.3
        if stats.get("pending_writes", 0) == 0:
            score += 0.2
        else:
            recs.append(
                f"{stats.get('pending_writes')} pending memory write(s) — run `/approve`"
            )
        return score

    @staticmethod
    def _score_vector_layer(stats: dict, recs: list[str]) -> float:
        score = 0.4  # base: DB exists
        episodes = stats.get("episodes", 0)
        embeddings = stats.get("embeddings", 0)
        total_sources = episodes + stats.get("facts", 0) + stats.get("skills", 0)
        if embeddings >= total_sources > 0:
            score += 0.4  # embeddings are up to date
        elif total_sources > 0:
            score += 0.2
            recs.append(f"{total_sources - embeddings} source(s) missing embeddings — reindex")
        if stats.get("fts_index", 0) >= total_sources > 0:
            score += 0.2  # FTS index healthy
        elif total_sources > 0:
            recs.append("FTS index incomplete — run `/memory governance`")
        if episodes == 0:
            recs.append("No episodes indexed — run the agent to start building memory")
        return score

    @staticmethod
    def _score_kg_layer(stats: dict, recs: list[str]) -> float:
        score = 0.3  # base
        entities = stats.get("entities", 0)
        edges = stats.get("edges", 0)
        if entities > 0:
            score += 0.4
        if edges > 0:
            score += 0.3
        else:
            recs.append("Knowledge graph has no edges — sync brain repo or run dreaming")
        return score

    # ------------------------------------------------------------------
    # Issue collectors
    # ------------------------------------------------------------------

    @staticmethod
    def _file_issues(stats: dict) -> list[str]:
        issues: list[str] = []
        if stats.get("memory_md_bytes", 0) == 0:
            issues.append("MEMORY.md is empty")
        if stats.get("pending_writes", 0) > 0:
            issues.append(f"{stats['pending_writes']} pending memory write(s)")
        return issues

    @staticmethod
    def _vector_issues(stats: dict) -> list[str]:
        issues: list[str] = []
        episodes = stats.get("episodes", 0)
        embeddings = stats.get("embeddings", 0)
        total = episodes + stats.get("facts", 0) + stats.get("skills", 0)
        if embeddings < total:
            issues.append(f"Orphan/missing embeddings: {total - embeddings}")
        if stats.get("fts_index", 0) < total:
            issues.append("FTS index incomplete")
        if episodes == 0:
            issues.append("No episodes indexed")
        return issues

    @staticmethod
    def _kg_issues(stats: dict) -> list[str]:
        issues: list[str] = []
        if stats.get("entities", 0) == 0:
            issues.append("No entities indexed")
        if stats.get("edges", 0) == 0:
            issues.append("No relations extracted")
        return issues

    # ------------------------------------------------------------------
    # Growth tracking
    # ------------------------------------------------------------------

    async def _compute_growth(
        self, vector_stats: dict, kg_stats: dict
    ) -> dict[str, int]:
        """Compare current stats with the most recent snapshot to compute growth."""
        prev = await self._load_latest_snapshot()
        if not prev:
            return {}
        growth: dict[str, int] = {}
        for key in ("episodes", "facts", "entities", "edges"):
            current = vector_stats.get(key, 0) if key in ("episodes", "facts") else kg_stats.get(key, 0)
            previous = prev.get(key, 0)
            if current != previous:
                growth[key] = current - previous
        return growth

    async def _save_snapshot(self, vector_stats: dict, kg_stats: dict) -> None:
        """Append current stats to the snapshot file."""
        snapshot = {
            "date": dt.datetime.now(dt.UTC).strftime("%Y-%m-%d"),
            "episodes": vector_stats.get("episodes", 0),
            "facts": vector_stats.get("facts", 0),
            "entities": kg_stats.get("entities", 0),
            "edges": kg_stats.get("edges", 0),
        }
        records = await self._load_all_snapshots()
        # Deduplicate same-day snapshots
        records = [r for r in records if r.get("date") != snapshot["date"]]
        records.append(snapshot)
        # Keep last 52 weeks
        records = records[-52:]

        def _write() -> None:
            self._STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
            self._STATS_PATH.write_text(
                json.dumps({"snapshots": records}, indent=2),
                encoding="utf-8",
            )

        await asyncio.to_thread(_write)

    async def _load_latest_snapshot(self) -> dict:
        """Load the most recent snapshot."""
        records = await self._load_all_snapshots()
        return records[-1] if records else {}

    async def _load_all_snapshots(self) -> list[dict]:
        """Load all snapshots from disk."""

        def _read() -> list[dict]:
            if not self._STATS_PATH.exists():
                return []
            try:
                data = json.loads(self._STATS_PATH.read_text(encoding="utf-8"))
                return data.get("snapshots", [])
            except (json.JSONDecodeError, OSError):
                return []

        return await asyncio.to_thread(_read)
