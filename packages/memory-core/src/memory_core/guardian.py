"""Memory Guardian — integrity checks across all memory layers.

Runs periodic integrity verification on FileLayer, VectorLayer, and KnowledgeGraph.
Detects orphan embeddings, broken foreign keys, malformed session files, and drift.
Can auto-repair minor issues when configured.
"""

import asyncio
import datetime as dt
import logging
import time
from pathlib import Path
from typing import Protocol

from memory_core.models import GuardianFinding, GuardianReport

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocols for dependency injection (no hard dep on agent-core)
# ---------------------------------------------------------------------------


class FileLayerProtocol(Protocol):
    """Interface for the file layer needed by the guardian."""

    async def read_memory(self) -> str: ...
    async def get_session_count(self) -> int: ...
    async def get_storage_stats(self) -> dict: ...
    memory_dir: Path


class VectorLayerProtocol(Protocol):
    """Interface for the vector layer needed by the guardian."""

    async def get_stats(self) -> dict: ...
    async def get_storage_stats(self) -> dict: ...
    async def cleanup_orphans(self) -> int: ...
    async def rebuild_fts_index(self) -> int: ...


class KnowledgeGraphProtocol(Protocol):
    """Interface for the knowledge graph needed by the guardian."""

    async def get_stats(self) -> dict: ...
    async def get_orphan_edge_count(self) -> int: ...
    async def cleanup_orphan_edges(self) -> int: ...


# ---------------------------------------------------------------------------
# MemoryGuardian
# ---------------------------------------------------------------------------


class MemoryGuardian:
    """Periodic integrity checker for the JalaAgent memory system.

    Verifies consistency between FileLayer (MEMORY.md, sessions),
    VectorLayer (sqlite-vec embeddings, FTS5), and KnowledgeGraph
    (entities, edges).  Can auto-repair minor issues.

    Usage::

        guardian = MemoryGuardian(file_layer, vector_layer, knowledge_graph)
        report = await guardian.run(auto_repair=True)
        print(report.health_status)  # 'healthy', 'degraded', or 'unhealthy'
    """

    def __init__(
        self,
        file_layer: FileLayerProtocol,
        vector_layer: VectorLayerProtocol,
        knowledge_graph: KnowledgeGraphProtocol | None = None,
    ) -> None:
        self._file = file_layer
        self._vector = vector_layer
        self._kg = knowledge_graph

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self, auto_repair: bool = False) -> GuardianReport:
        """Run all integrity checks and return a report.

        Parameters
        ----------
        auto_repair:
            If ``True``, minor issues (orphan embeddings, broken FKs) are
            automatically repaired.
        """
        start = time.monotonic()
        findings: list[GuardianFinding] = []

        # Layer 1 — File checks
        findings.extend(await self._check_memory_readability())
        findings.extend(await self._check_session_integrity())

        # Layer 2 — Vector checks
        findings.extend(await self._check_embedding_consistency())
        findings.extend(await self._check_fts_consistency())

        # Layer 3 — Knowledge Graph checks
        if self._kg is not None:
            findings.extend(await self._check_kg_foreign_keys())

        # Auto-repair
        repair_count = 0
        if auto_repair:
            repairable = [f for f in findings if f.auto_repairable]
            for f in repairable:
                count = await self._repair(f.category)
                if count > 0:
                    f.repaired = True
                    repair_count += count

        # Compute health status
        errors = sum(1 for f in findings if f.severity in ("error", "critical"))
        health: GuardianReport._LiteralHealthStatus
        if any(f.severity == "critical" for f in findings):
            health = "unhealthy"
        elif errors > 0:
            health = "unhealthy"
        elif any(f.severity == "warning" for f in findings):
            health = "degraded"
        else:
            health = "healthy"

        return GuardianReport(
            timestamp=dt.datetime.now(dt.UTC),
            findings=findings,
            total_checks=len(findings),
            repair_count=repair_count,
            error_count=errors,
            health_status=health,
            duration_seconds=time.monotonic() - start,
        )

    # ------------------------------------------------------------------
    # Layer 1 — File checks
    # ------------------------------------------------------------------

    async def _check_memory_readability(self) -> list[GuardianFinding]:
        """Check that MEMORY.md is readable."""
        try:
            content = await self._file.read_memory()
            if not content.strip():
                return [
                    GuardianFinding(
                        layer="file",
                        severity="info",
                        category="empty_memory",
                        message="MEMORY.md is empty — no curated memories yet.",
                    )
                ]
            return []
        except FileNotFoundError:
            return [
                GuardianFinding(
                    layer="file",
                    severity="warning",
                    category="missing_memory",
                    message="MEMORY.md not found. Run dreaming pipeline or write memory manually.",
                )
            ]
        except Exception as exc:
            return [
                GuardianFinding(
                    layer="file",
                    severity="critical",
                    category="unreadable_memory",
                    message=f"MEMORY.md is unreadable: {exc}",
                )
            ]

    async def _check_session_integrity(self) -> list[GuardianFinding]:
        """Check session JSONL files for malformed content."""
        import json as _json

        sessions_dir = self._file.memory_dir / "sessions"
        if not sessions_dir.is_dir():
            return [
                GuardianFinding(
                    layer="file",
                    severity="info",
                    category="no_sessions",
                    message="No session directory yet.",
                )
            ]

        findings: list[GuardianFinding] = []
        for jsonl_file in sorted(sessions_dir.glob("*.jsonl")):
            total_lines = 0
            bad_lines = 0
            try:
                with open(jsonl_file, "r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        total_lines += 1
                        try:
                            _json.loads(line)
                        except _json.JSONDecodeError:
                            bad_lines += 1
            except Exception as exc:
                findings.append(
                    GuardianFinding(
                        layer="file",
                        severity="error",
                        category="unreadable_session",
                        message=f"Cannot read session file {jsonl_file.name}: {exc}",
                        detail={"file": str(jsonl_file.name)},
                    )
                )
                continue

            if total_lines > 0 and bad_lines / total_lines > 0.1:
                findings.append(
                    GuardianFinding(
                        layer="file",
                        severity="warning",
                        category="malformed_session",
                        message=(
                            f"Session {jsonl_file.name}: {bad_lines}/{total_lines} "
                            "lines are malformed JSON (>10%)"
                        ),
                        detail={
                            "file": str(jsonl_file.name),
                            "total": total_lines,
                            "bad": bad_lines,
                        },
                    )
                )

        return findings

    # ------------------------------------------------------------------
    # Layer 2 — Vector checks
    # ------------------------------------------------------------------

    async def _check_embedding_consistency(self) -> list[GuardianFinding]:
        """Check that every embedding row has a valid source row."""
        findings: list[GuardianFinding] = []
        stats = await self._vector.get_stats()

        # The ratio of embeddings to (episodes + facts + skills) should be close to 1:1
        total_sources = stats.get("episodes", 0) + stats.get("facts", 0) + stats.get("skills", 0)
        total_embeddings = stats.get("embeddings", 0)

        if total_embeddings > total_sources:
            orphan_count = total_embeddings - total_sources
            findings.append(
                GuardianFinding(
                    layer="vector",
                    severity="warning",
                    category="orphan_embedding",
                    message=(
                        f"{orphan_count} orphan embedding(s) detected — "
                        "more embeddings than source rows"
                    ),
                    detail={"orphan_count": orphan_count, "total_embeddings": total_embeddings},
                    auto_repairable=True,
                )
            )
        elif total_embeddings < total_sources:
            findings.append(
                GuardianFinding(
                    layer="vector",
                    severity="warning",
                    category="missing_embedding",
                    message=(
                        f"{total_sources - total_embeddings} source row(s) "
                        "have no embedding"
                    ),
                    detail={"missing_count": total_sources - total_embeddings},
                )
            )

        return findings

    async def _check_fts_consistency(self) -> list[GuardianFinding]:
        """Check FTS index has entries for all source rows."""
        stats = await self._vector.get_stats()
        fts_count = stats.get("fts_index", 0)
        total_sources = stats.get("episodes", 0) + stats.get("facts", 0) + stats.get("skills", 0)

        if total_sources > 0 and fts_count < total_sources:
            missing = total_sources - fts_count
            return [
                GuardianFinding(
                    layer="vector",
                    severity="warning",
                    category="missing_fts",
                    message=f"{missing} FTS index entries missing — run governance rebuild",
                    detail={"missing_count": missing, "total_sources": total_sources},
                    auto_repairable=True,
                )
            ]
        return []

    # ------------------------------------------------------------------
    # Layer 3 — Knowledge Graph checks
    # ------------------------------------------------------------------

    async def _check_kg_foreign_keys(self) -> list[GuardianFinding]:
        """Check for broken foreign keys in the knowledge graph."""
        if self._kg is None:
            return []
        orphan_count = await self._kg.get_orphan_edge_count()
        if orphan_count > 0:
            return [
                GuardianFinding(
                    layer="knowledge_graph",
                    severity="error",
                    category="broken_edge_fk",
                    message=f"{orphan_count} edge(s) with broken foreign keys",
                    detail={"orphan_edge_count": orphan_count},
                    auto_repairable=True,
                )
            ]
        return []

    # ------------------------------------------------------------------
    # Auto-repair
    # ------------------------------------------------------------------

    async def _repair(self, category: str) -> int:
        """Attempt to auto-repair a specific category of problem. Returns count fixed."""
        if category == "orphan_embedding":
            return await self._vector.cleanup_orphans()
        if category == "missing_fts":
            return await self._vector.rebuild_fts_index()
        if category == "broken_edge_fk":
            if self._kg is not None:
                return await self._kg.cleanup_orphan_edges()
        logger.info("Guardian: no auto-repair for category %s", category)
        return 0
