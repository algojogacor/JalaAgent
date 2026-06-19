"""Memory retrieval: sqlite-vec KNN → FTS5 → Knowledge Graph → MEMORY.md scan.

Implements a four-tier retrieval flow:

1. **Primary:** sqlite-vec KNN search via :class:`VectorLayer`.
2. **Fallback:** FTS5 keyword search via :class:`VectorLayer`.
3. **Knowledge Graph:** entity-aware search via :class:`KnowledgeGraph`
   (entities, relations, graph traversal).
4. **Last resort:** linear scan of ``MEMORY.md`` content.

Results are combined, deduplicated, threshold-filtered, and formatted as a
``<memory-context>`` XML block for injection into the LLM system prompt.

The retrieval is **frozen at session start** (frozen snapshot pattern) —
:meth:`build_system_context` reads ``MEMORY.md`` + ``USER.md`` once and the
result is never updated mid-session.
"""

import logging
import re

from memory_core.file_layer import FileLayer
from memory_core.knowledge_graph import KnowledgeGraph
from memory_core.models import (
    Episode,
    Fact,
    MemoryConfig,
    MemorySearchResult,
)
from memory_core.vector_layer import VectorLayer

logger = logging.getLogger(__name__)

_SESSION_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def _format_entry(obj: Episode | Fact, score: float) -> str:
    score_str = f"{score:.2f}"
    max_len = 300
    content = obj.content.replace("\n", " ").strip()
    if len(content) > max_len:
        content = content[: max_len - 3] + "..."

    if isinstance(obj, Fact):
        return f"[Fact] {content} (score: {score_str})"

    date_match = _SESSION_DATE_RE.search(obj.session_id) if obj.session_id else None
    date_str = date_match.group(1) if date_match else obj.timestamp.strftime("%Y-%m-%d")
    return f"[Session {date_str}] {content} (score: {score_str})"


class MemoryRetriever:
    """Multi-strategy memory retrieval with four-tier fallback.

    Parameters
    ----------
    config:
        Memory subsystem configuration.
    file_layer:
        File-layer instance for reading ``MEMORY.md`` and ``USER.md``.
    vector_layer:
        Vector-layer instance for KNN and FTS search.
    knowledge_graph:
        Optional knowledge graph for entity-aware retrieval.
    """

    def __init__(
        self,
        config: MemoryConfig,
        file_layer: FileLayer,
        vector_layer: VectorLayer,
        knowledge_graph: KnowledgeGraph | None = None,
    ) -> None:
        self._config = config
        self._file_layer = file_layer
        self._vector_layer = vector_layer
        self._kg = knowledge_graph

    async def upsert_episode(self, episode: "Episode") -> None:
        """Index an episode in the vector layer for semantic search.

        Delegates to the underlying ``VectorLayer``.  Errors are logged
        and silently swallowed — this is a best-effort operation that
        must never block the caller.
        """
        try:
            await self._vector_layer.upsert_episode(episode)
        except Exception:
            logger.exception("Failed to upsert episode %s", episode.id)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def retrieve(self, query: str, k: int | None = None) -> str:
        raw = await self.retrieve_raw(query, k)
        if not raw:
            return ""

        lines = ["<memory-context>"]
        for _entry_id, content, _score, _source in raw:
            lines.append(f"  {content}")
        lines.append("</memory-context>")

        return "\n".join(lines) + "\n"

    async def retrieve_raw(
        self, query: str, k: int | None = None
    ) -> list[MemorySearchResult]:
        max_results = k if k is not None else self._config.max_retrieval_results
        threshold = self._config.retrieval_threshold

        # Tier 1 & 2: vector KNN + FTS fallback.
        vector_results = await self._vector_layer.search(query, max_results)

        # Tier 3: Knowledge Graph — entity and relation search.
        kg_results = await self._search_knowledge_graph(query, max_results)

        # Tier 4: MEMORY.md linear scan.
        memory_results = await self._scan_memory_md(query, max_results)

        # Merge all sources with priority: vector > KG > memory.
        return self._merge_results(
            vector_results, kg_results, memory_results, max_results, threshold
        )

    async def build_system_context(self) -> str:
        memory = await self._file_layer.read_memory()
        user = await self._file_layer.read_user()

        parts: list[str] = []
        if user.strip():
            parts.append(f"<user-profile>\n{user.strip()}\n</user-profile>")
        if memory.strip():
            parts.append(f"<curated-memory>\n{memory.strip()}\n</curated-memory>")

        # Append knowledge graph summary if available.
        if self._kg:
            stats = await self._kg.get_stats()
            if stats.get("entities", 0) > 0:
                parts.append(
                    f"<knowledge-graph>\n"
                    f"  {stats['entities']} entities, "
                    f"{stats['edges']} relations, "
                    f"{stats['pages']} pages indexed.\n"
                    f"</knowledge-graph>"
                )

        return "\n\n".join(parts) + "\n" if parts else ""

    # ------------------------------------------------------------------
    # Tier 3: Knowledge Graph
    # ------------------------------------------------------------------

    async def _search_knowledge_graph(
        self, query: str, k: int
    ) -> list[MemorySearchResult]:
        """Search the knowledge graph for entities and relations matching *query*."""
        if self._kg is None:
            return []

        results: list[MemorySearchResult] = []

        try:
            # Entity search.
            entities = await self._kg.search_entities(query, k)
            for i, entity in enumerate(entities):
                name = entity.get("name", "unknown")
                etype = entity.get("type", "entity")
                results.append(
                    MemorySearchResult(
                        entry_id=entity.get("id", f"ent-{i}"),
                        content=f"[Entity:{etype}] {name}",
                        score=0.85,
                        source="knowledge_graph",
                    )
                )

            # If we found an entity, traverse its graph for related entities.
            if entities:
                top_entity = entities[0]
                name = top_entity.get("name", "")
                graph_results = await self._kg.graph_query(name, max_hops=1)
                for j, node in enumerate(graph_results[1:]):  # Skip the queried entity.
                    node_name = node.get("name", "unknown")
                    node_type = node.get("type", "entity")
                    results.append(
                        MemorySearchResult(
                            entry_id=node.get("id", f"rel-{j}"),
                            content=f"[Relation] {name} → {node_name} ({node_type})",
                            score=0.75,
                            source="knowledge_graph",
                        )
                    )
        except Exception:
            logger.debug("Knowledge graph search failed, continuing without it")

        return results[:k]

    # ------------------------------------------------------------------
    # Merging
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_results(
        vector_results: list[tuple[Episode | Fact, float]],
        kg_results: list[MemorySearchResult],
        memory_results: list[MemorySearchResult],
        max_results: int,
        threshold: float,
    ) -> list[MemorySearchResult]:
        seen: set[str] = set()
        merged: list[MemorySearchResult] = []

        # Tier 1-2: Vector + FTS (highest priority).
        for obj, score in vector_results:
            if score < threshold:
                continue
            obj_id = str(obj.id)
            if obj_id in seen:
                continue
            seen.add(obj_id)
            merged.append(
                MemorySearchResult(
                    entry_id=obj_id,
                    content=_format_entry(obj, score),
                    score=round(score, 4),
                    source=type(obj).__name__.lower(),
                )
            )

        # Tier 3: Knowledge graph (medium priority — supplement, don't override).
        for result in kg_results:
            if result.score < threshold:
                continue
            if result.entry_id in seen:
                continue
            seen.add(result.entry_id)
            merged.append(result)

        # Tier 4: Memory.md scan (lowest priority).
        for result in memory_results:
            if result.score < threshold:
                continue
            if result.entry_id in seen:
                continue
            seen.add(result.entry_id)
            merged.append(result)

        merged.sort(key=lambda r: r.score, reverse=True)
        return merged[:max_results]

    async def _scan_memory_md(
        self, query: str, k: int
    ) -> list[MemorySearchResult]:
        content = await self._file_layer.read_memory()
        if not content.strip():
            return []

        query_tokens = set(query.lower().split())
        if not query_tokens:
            return []

        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        scored: list[MemorySearchResult] = []

        for i, para in enumerate(paragraphs):
            para_tokens = set(para.lower().split())
            if not para_tokens:
                continue
            overlap = query_tokens & para_tokens
            if not overlap:
                continue
            union = query_tokens | para_tokens
            score = len(overlap) / len(union)
            if query.lower() in para.lower():
                score = min(1.0, score + 0.3)
            scored.append(
                MemorySearchResult(
                    entry_id=f"memory-md-para-{i}",
                    content=f"[Memory] {para[:300]}",
                    score=round(score, 4),
                    source="memory_md",
                )
            )

        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:k]

    @property
    def config(self) -> MemoryConfig:
        return self._config
