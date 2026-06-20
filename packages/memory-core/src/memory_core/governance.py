"""Memory Governance Rebuild — periodic index maintenance and orphan cleanup.

Provides background maintenance for the vector layer (FTS5 rebuild, orphan cleanup)
and knowledge graph (index rebuild, edge cleanup).  Designed to run on a weekly
cron schedule via the JalaAgent cron system.
"""

import asyncio
import datetime as dt
import logging
import time
from typing import Protocol

from memory_core.models import GovernanceReport

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


class VectorLayerProtocol(Protocol):
    """Interface for the vector layer needed by governance."""

    async def get_stats(self) -> dict: ...
    async def get_storage_stats(self) -> dict: ...
    async def rebuild_fts_index(self) -> int: ...
    async def cleanup_orphans(self) -> int: ...


class KnowledgeGraphProtocol(Protocol):
    """Interface for the knowledge graph needed by governance."""

    async def get_stats(self) -> dict: ...
    async def get_orphan_edge_count(self) -> int: ...
    async def cleanup_orphan_edges(self) -> int: ...


# ---------------------------------------------------------------------------
# GovernanceRebuild
# ---------------------------------------------------------------------------


class GovernanceRebuild:
    """Periodic index rebuild and orphan cleanup for the memory system.

    Runs maintenance operations that improve performance (FTS5 rebuild, index
    optimization) and clean up inconsistencies (orphan embeddings, broken edges).

    Usage::

        governance = GovernanceRebuild(vector_layer, knowledge_graph)
        report = await governance.rebuild_all()
        print(report.before_stats, "->", report.after_stats)
    """

    def __init__(
        self,
        vector_layer: VectorLayerProtocol,
        knowledge_graph: KnowledgeGraphProtocol | None = None,
    ) -> None:
        self._vector = vector_layer
        self._kg = knowledge_graph

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def rebuild_all(self) -> GovernanceReport:
        """Run all maintenance operations and return a report."""
        start = time.monotonic()
        actions: list[str] = []

        before = await self._collect_stats()

        # 1. Rebuild FTS index
        try:
            fts_count = await self._vector.rebuild_fts_index()
            actions.append(f"FTS index rebuilt ({fts_count} rows reindexed)")
            logger.info("Governance: FTS index rebuilt — %d rows", fts_count)
        except Exception as exc:
            actions.append(f"FTS rebuild failed: {exc}")
            logger.error("Governance: FTS rebuild error — %s", exc)

        # 2. Cleanup orphan embeddings
        try:
            orphan_count = await self._vector.cleanup_orphans()
            if orphan_count > 0:
                actions.append(f"Orphan embeddings removed ({orphan_count})")
            else:
                actions.append("No orphan embeddings found")
        except Exception as exc:
            actions.append(f"Orphan cleanup failed: {exc}")
            logger.error("Governance: orphan cleanup error — %s", exc)

        # 3. Knowledge Graph maintenance
        if self._kg is not None:
            try:
                edge_count = await self._kg.cleanup_orphan_edges()
                if edge_count > 0:
                    actions.append(f"KG orphan edges removed ({edge_count})")
                else:
                    actions.append("No KG orphan edges found")
                # Vacuum-like optimization: get fresh stats to trigger ANALYZE
                await self._kg.get_stats()
            except Exception as exc:
                actions.append(f"KG maintenance failed: {exc}")
                logger.error("Governance: KG maintenance error — %s", exc)

        after = await self._collect_stats()

        return GovernanceReport(
            timestamp=dt.datetime.now(dt.UTC),
            before_stats=before,
            after_stats=after,
            rebuild_actions=actions,
            duration_seconds=time.monotonic() - start,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _collect_stats(self) -> dict:
        """Collect stats from all available layers."""
        stats: dict = {"vector": await self._vector.get_storage_stats()}
        if self._kg is not None:
            stats["knowledge_graph"] = await self._kg.get_stats()
        return stats
