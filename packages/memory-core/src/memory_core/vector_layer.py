"""Layer 2 — SQLite + sqlite-vec vector database for semantic memory search."""

import asyncio
import hashlib
import json
import math
import sqlite3
import struct

import httpx

from memory_core.models import Episode, Fact, MemoryConfig, SkillIndex

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hash_text(text: str) -> str:
    """SHA-256 hex digest of *text* (used for embedding cache key)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _blob_to_floats(blob: bytes) -> list[float]:
    """Unpack a little-endian float32 blob into a list of floats."""
    count = len(blob) // 4
    fmt = f"<{count}f"
    return list(struct.unpack(fmt, blob))


def _floats_to_blob(vec: list[float]) -> bytes:
    """Pack a list of floats into a little-endian float32 blob."""
    fmt = f"<{len(vec)}f"
    return struct.pack(fmt, *vec)


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors of equal dimension."""
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


# ---------------------------------------------------------------------------
# VectorLayer
# ---------------------------------------------------------------------------

SearchResult = tuple[Episode | Fact, float]

_CREATE_EPISODES = """\
CREATE TABLE IF NOT EXISTS episodes (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    tool_name TEXT,
    metadata TEXT DEFAULT '{}'
)
"""

_CREATE_FACTS = """\
CREATE TABLE IF NOT EXISTS facts (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.5,
    source_episode_ids TEXT DEFAULT '[]',
    promoted_at TEXT,
    promotion_count INTEGER NOT NULL DEFAULT 0
)
"""

_CREATE_SKILLS = """\
CREATE TABLE IF NOT EXISTS skills (
    skill_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    embedding_updated_at TEXT
)
"""

_CREATE_EMBEDDINGS = """\
CREATE TABLE IF NOT EXISTS embeddings (
    id TEXT PRIMARY KEY,
    table_name TEXT NOT NULL,
    row_id TEXT NOT NULL,
    embedding BLOB NOT NULL
)
"""

_CREATE_FTS = """\
CREATE VIRTUAL TABLE IF NOT EXISTS fts_index USING fts5(
    content,
    id UNINDEXED,
    table_name UNINDEXED,
    tokenize='unicode61'
)
"""


class VectorLayer:
    """Vector-based memory with sqlite-vec KNN search and FTS5 keyword fallback.

    Stores episodes, facts, and skills in SQLite tables.  Generates embeddings
    via an Ollama-compatible API and indexes them with ``sqlite-vec`` for
    approximate KNN search.  Falls back gracefully to a full cosine scan when
    ``sqlite-vec`` is unavailable.
    """

    def __init__(self, config: MemoryConfig) -> None:
        self._config = config
        self._db_path = config.db_path
        self._embedding_model = config.embedding_model
        self._embedding_dim = config.embedding_dim
        self._embedding_base_url = config.embedding_base_url
        self._conn: sqlite3.Connection | None = None
        self._http: httpx.AsyncClient | None = None
        self._embedding_cache: dict[str, list[float]] = {}

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    async def _get_db(self) -> sqlite3.Connection:
        if self._conn is None:
            await self.initialize()
        assert self._conn is not None
        return self._conn

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        return self._http

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Create all tables and the FTS index if they don't exist."""

        def _sync() -> sqlite3.Connection:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute(_CREATE_EPISODES)
            conn.execute(_CREATE_FACTS)
            conn.execute(_CREATE_SKILLS)
            conn.execute(_CREATE_EMBEDDINGS)
            conn.execute(_CREATE_FTS)
            conn.commit()
            return conn

        self._conn = await asyncio.to_thread(_sync)

    # ------------------------------------------------------------------
    # Embedding
    # ------------------------------------------------------------------

    async def embed(self, text: str) -> list[float]:
        """Return the embedding vector for *text* via the Ollama API.

        Results are cached by SHA-256 content hash.  Repeated calls with the
        same text skip the HTTP round-trip entirely.
        """
        key = _hash_text(text)
        if key in self._embedding_cache:
            return self._embedding_cache[key]

        http = await self._get_http()
        response = await http.post(
            f"{self._embedding_base_url}/api/embed",
            json={"model": self._embedding_model, "input": text},
        )
        response.raise_for_status()
        data = response.json()
        vec: list[float] = data["embeddings"][0]
        self._embedding_cache[key] = vec
        return vec

    # ------------------------------------------------------------------
    # Upsert helpers
    # ------------------------------------------------------------------

    async def _embed_and_store(
        self, content: str, table_name: str, row_id: str
    ) -> None:
        """Generate an embedding for *content* and upsert into embeddings table."""
        vec = await self.embed(content)
        blob = _floats_to_blob(vec)
        db = await self._get_db()

        def _sync() -> None:
            db.execute(
                "INSERT OR REPLACE INTO embeddings(id, table_name, row_id, embedding) "
                "VALUES(?, ?, ?, ?)",
                (_hash_text(content), table_name, row_id, blob),
            )
            db.commit()

        await asyncio.to_thread(_sync)

    async def _index_fts(self, row_id: str, table_name: str, content: str) -> None:
        """Insert or replace a row in the FTS virtual table."""
        db = await self._get_db()

        def _sync() -> None:
            db.execute(
                "INSERT OR REPLACE INTO fts_index(rowid, content, id, table_name) "
                "VALUES((SELECT rowid FROM fts_index WHERE id = ? AND table_name = ?), "
                "?, ?, ?)",
                (row_id, table_name, content, row_id, table_name),
            )
            db.commit()

        await asyncio.to_thread(_sync)

    # ------------------------------------------------------------------
    # Upsert public methods
    # ------------------------------------------------------------------

    async def upsert_episode(self, episode: Episode) -> None:
        db = await self._get_db()

        def _sync() -> None:
            db.execute(
                "INSERT OR REPLACE INTO episodes(id, session_id, timestamp, role, "
                "content, tool_name, metadata) VALUES(?, ?, ?, ?, ?, ?, ?)",
                (
                    str(episode.id),
                    episode.session_id,
                    episode.timestamp.isoformat(),
                    episode.role,
                    episode.content,
                    episode.tool_name,
                    json.dumps(episode.metadata),
                ),
            )
            db.commit()

        await asyncio.to_thread(_sync)
        await self._embed_and_store(episode.content, "episodes", str(episode.id))
        await self._index_fts(str(episode.id), "episodes", episode.content)

    async def upsert_fact(self, fact: Fact) -> None:
        db = await self._get_db()

        def _sync() -> None:
            promoted = fact.promoted_at.isoformat() if fact.promoted_at else None
            db.execute(
                "INSERT OR REPLACE INTO facts(id, content, confidence, "
                "source_episode_ids, promoted_at, promotion_count) "
                "VALUES(?, ?, ?, ?, ?, ?)",
                (
                    str(fact.id),
                    fact.content,
                    fact.confidence,
                    json.dumps(fact.source_episode_ids),
                    promoted,
                    fact.promotion_count,
                ),
            )
            db.commit()

        await asyncio.to_thread(_sync)
        await self._embed_and_store(fact.content, "facts", str(fact.id))
        await self._index_fts(str(fact.id), "facts", fact.content)

    async def upsert_skill(self, skill: SkillIndex) -> None:
        db = await self._get_db()

        def _sync() -> None:
            emb_updated = (
                skill.embedding_updated_at.isoformat()
                if skill.embedding_updated_at
                else None
            )
            db.execute(
                "INSERT OR REPLACE INTO skills(skill_id, name, description, "
                "content_hash, embedding_updated_at) VALUES(?, ?, ?, ?, ?)",
                (
                    skill.skill_id,
                    skill.name,
                    skill.description,
                    skill.content_hash,
                    emb_updated,
                ),
            )
            db.commit()

        await asyncio.to_thread(_sync)

    # ------------------------------------------------------------------
    # Retrieval helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _episode_from_row(row: sqlite3.Row) -> Episode:
        return Episode(
            id=row["id"],
            session_id=row["session_id"],
            timestamp=row["timestamp"],
            role=row["role"],
            content=row["content"],
            tool_name=row["tool_name"],
            metadata=json.loads(row["metadata"]),
        )

    @staticmethod
    def _fact_from_row(row: sqlite3.Row) -> Fact:
        promoted = row["promoted_at"]
        return Fact(
            id=row["id"],
            content=row["content"],
            confidence=row["confidence"],
            source_episode_ids=json.loads(row["source_episode_ids"]),
            promoted_at=promoted if promoted else None,
            promotion_count=row["promotion_count"],
        )

    async def _search_knn_via_vec(self, query_vec: list[float], k: int) -> list[SearchResult]:
        """Try sqlite-vec native KNN.  Returns empty list on failure."""
        db = await self._get_db()
        blob = _floats_to_blob(query_vec)

        def _sync() -> list[tuple[str, str, float]]:
            """Return (table_name, row_id, cosine_distance) for each row."""
            try:
                rows = db.execute(
                    "SELECT e.embedding, e.table_name, e.row_id "
                    "FROM embeddings e "
                    "WHERE e.embedding MATCH ? AND k = ? "
                    "ORDER BY distance",
                    (blob, k),
                ).fetchall()
            except (sqlite3.OperationalError, sqlite3.DatabaseError):
                return []

            scored: list[tuple[str, str, float]] = []
            for row in rows:
                emb_vec = _blob_to_floats(row["embedding"])
                score = 1.0 - _cosine(query_vec, emb_vec)
                scored.append((row["table_name"], row["row_id"], score))
            return scored

        scored_rows = await asyncio.to_thread(_sync)

        # Resolve objects in async context (calls outside the thread).
        results: list[SearchResult] = []
        for table_name, row_id, score in scored_rows:
            obj = await self._load_row(table_name, row_id)
            if obj is not None:
                results.append((obj, score))
        return results

    async def _search_cosine_fallback(
        self, query_vec: list[float], k: int
    ) -> list[SearchResult]:
        """Full cosine-similarity scan when sqlite-vec is unavailable."""
        db = await self._get_db()

        def _sync() -> list[tuple[float, str, str]]:
            rows = db.execute(
                "SELECT embedding, table_name, row_id FROM embeddings"
            ).fetchall()
            scored: list[tuple[float, str, str]] = []
            for row in rows:
                emb_vec = _blob_to_floats(row["embedding"])
                score = _cosine(query_vec, emb_vec)
                scored.append((score, row["table_name"], row["row_id"]))
            scored.sort(key=lambda x: x[0], reverse=True)
            return scored[:k]

        scored_rows = await asyncio.to_thread(_sync)

        results: list[SearchResult] = []
        for item in scored_rows:
            score, table_name, row_id = item
            obj = await self._load_row(table_name, row_id)
            if obj is not None:
                results.append((obj, score))
        return results

    async def _load_row(
        self, table_name: str, row_id: str
    ) -> Episode | Fact | None:
        db = await self._get_db()

        def _sync() -> Episode | Fact | None:
            if table_name == "episodes":
                row = db.execute(
                    "SELECT * FROM episodes WHERE id = ?", (row_id,)
                ).fetchone()
                if row:
                    return VectorLayer._episode_from_row(row)
            elif table_name == "facts":
                row = db.execute(
                    "SELECT * FROM facts WHERE id = ?", (row_id,)
                ).fetchone()
                if row:
                    return VectorLayer._fact_from_row(row)
            return None

        return await asyncio.to_thread(_sync)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search_knn(self, query: str, k: int = 10) -> list[SearchResult]:
        """KNN vector search with graceful fallback to full cosine scan."""
        try:
            query_vec = await self.embed(query)
        except Exception:
            return []
        results = await self._search_knn_via_vec(query_vec, k)
        if not results:
            results = await self._search_cosine_fallback(query_vec, k)
        return results

    async def search_fts(self, query: str, k: int = 10) -> list[SearchResult]:
        """FTS5 full-text search with BM25 ranking."""
        db = await self._get_db()

        def _sync() -> list[tuple[str, str, float]]:
            try:
                rows = db.execute(
                    "SELECT id, table_name, bm25(fts_index, 0, 10, 5) AS score "
                    "FROM fts_index WHERE fts_index MATCH ? "
                    "ORDER BY score LIMIT ?",
                    (query, k),
                ).fetchall()
            except (sqlite3.OperationalError, sqlite3.DatabaseError):
                # FTS5 may reject queries with special characters — fall back
                # to LIKE-based search.
                like_q = f"%{query}%"
                rows = db.execute(
                    "SELECT id, table_name, 0.0 AS score "
                    "FROM fts_index WHERE content LIKE ? LIMIT ?",
                    (like_q, k),
                ).fetchall()
            return [(r["id"], r["table_name"], r["score"]) for r in rows]

        rows = await asyncio.to_thread(_sync)
        results: list[SearchResult] = []
        for row_id, table_name, score in rows:
            obj = await self._load_row(table_name, row_id)
            if obj is not None:
                # Normalise BM25 into a rough 0-1 range (heuristic sigmoid).
                norm = 1.0 / (1.0 + math.exp(-score / 5.0))
                results.append((obj, norm))
        return results

    async def search(self, query: str, k: int = 10) -> list[SearchResult]:
        """KNN first, FTS fallback, deduplicated by id, sorted by score DESC."""
        # Collect KNN results.
        knn_results = await self.search_knn(query, k)

        # Collect FTS results, but only those not already in KNN.
        seen_ids: set[str] = set()
        for obj, _ in knn_results:
            seen_ids.add(str(obj.id))

        fts_results = await self.search_fts(query, k)
        merged = list(knn_results)
        for obj, score in fts_results:
            if str(obj.id) not in seen_ids:
                merged.append((obj, score))
                seen_ids.add(str(obj.id))

        # Sort by score descending, take top k.
        merged.sort(key=lambda x: x[1], reverse=True)
        return merged[:k]

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete_episode(self, episode_id: str) -> None:
        """Remove an episode and its embedding."""
        db = await self._get_db()

        def _sync() -> None:
            db.execute("DELETE FROM episodes WHERE id = ?", (episode_id,))
            db.execute(
                "DELETE FROM embeddings WHERE table_name = 'episodes' AND row_id = ?",
                (episode_id,),
            )
            db.execute(
                "DELETE FROM fts_index WHERE id = ? AND table_name = 'episodes'",
                (episode_id,),
            )
            db.commit()

        await asyncio.to_thread(_sync)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    async def get_stats(self) -> dict:
        """Return row counts per table."""
        db = await self._get_db()

        def _sync() -> dict:
            return {
                "episodes": db.execute("SELECT COUNT(*) FROM episodes").fetchone()[0],
                "facts": db.execute("SELECT COUNT(*) FROM facts").fetchone()[0],
                "skills": db.execute("SELECT COUNT(*) FROM skills").fetchone()[0],
                "embeddings": db.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0],
                "fts_index": db.execute("SELECT COUNT(*) FROM fts_index").fetchone()[0],
            }

        return await asyncio.to_thread(_sync)

    async def get_storage_stats(self) -> dict:
        """Return storage stats including DB file size."""
        import os as _os
        stats = await self.get_stats()
        db_size = _os.path.getsize(str(self._db_path)) if self._db_path.exists() else 0
        stats["db_size_bytes"] = db_size
        return stats

    async def rebuild_fts_index(self) -> int:
        """Drop and recreate the FTS5 index from episode/fact/skill content.

        Returns the number of rows reindexed.
        """
        db = await self._get_db()

        def _sync() -> int:
            db.execute("DELETE FROM fts_index")
            count = 0
            for table in ("episodes", "facts", "skills"):
                id_col = "skill_id" if table == "skills" else "id"
                rows = db.execute(
                    f"SELECT {id_col}, content FROM {table}"
                ).fetchall()
                db.executemany(
                    "INSERT INTO fts_index (id, table_name, content) VALUES (?, ?, ?)",
                    [(r[0], table, r[1]) for r in rows],
                )
                count += len(rows)
            db.commit()
            return count

        return await asyncio.to_thread(_sync)

    async def cleanup_orphans(self) -> int:
        """Remove orphan embeddings (no matching row in source tables).

        Returns the number of orphan embeddings removed.
        """
        db = await self._get_db()

        def _sync() -> int:
            # Find embeddings whose row_id doesn't exist in any source table
            cursor = db.execute(
                """SELECT e.id FROM embeddings e
                   WHERE (e.table_name = 'episodes'
                         AND e.row_id NOT IN (SELECT id FROM episodes))
                      OR (e.table_name = 'facts'
                         AND e.row_id NOT IN (SELECT id FROM facts))
                      OR (e.table_name = 'skills'
                         AND e.row_id NOT IN (SELECT skill_id FROM skills))"""
            )
            orphan_ids = [r[0] for r in cursor.fetchall()]
            for oid in orphan_ids:
                db.execute("DELETE FROM embeddings WHERE id = ?", (oid,))
            db.commit()
            return len(orphan_ids)

        return await asyncio.to_thread(_sync)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the SQLite connection and HTTP client."""
        if self._http is not None:
            try:
                await self._http.aclose()
            except (TypeError, AttributeError):
                pass  # mock or already-closed client
            self._http = None
        if self._conn is not None:
            def _sync() -> None:
                self._conn.close()  # type: ignore[union-attr]
            await asyncio.to_thread(_sync)
            self._conn = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def embedding_cache_size(self) -> int:
        """Number of entries in the in-memory embedding cache."""
        return len(self._embedding_cache)


# ---------------------------------------------------------------------------
# Backward-compatibility alias
# ---------------------------------------------------------------------------


class VectorMemoryLayer(VectorLayer):
    """Legacy alias for :class:`VectorLayer`."""

    pass
