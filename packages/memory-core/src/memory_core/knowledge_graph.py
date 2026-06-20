"""GBrain-inspired knowledge graph — entity extraction, typed edges, graph traversal.

Key concepts adopted from GBrain (https://github.com/garrytan/gbrain):

1. **Hybrid search** — vector + keyword + reciprocal-rank fusion.
2. **Self-wiring knowledge graph** — extract entity references and create
   typed edges with zero LLM calls (regex-based extraction).
3. **Brain repo** — knowledge lives in git-trackable markdown; sync into
   the database for retrieval.
4. **Schema packs** — configurable page-type taxonomies.
"""

import hashlib
import json
import logging
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {k: row[k] for k in row.keys()}

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Entity extraction patterns (zero LLM cost)
# ---------------------------------------------------------------------------

# Matches: "Person Name" (quoted), @username, email, URL, org mentions.
_PERSON_PATTERN = re.compile(r'"([A-Z][a-z]+ [A-Z][a-z]+)"')
_MENTION_PATTERN = re.compile(r"@(\w+)")
_EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_URL_PATTERN = re.compile(r"https?://[^\s]+")
_ORG_PATTERN = re.compile(r"\b([A-Z][a-z]+ (Inc|LLC|Corp|Ltd|AI|Labs|Research))\b")

# Relation indicators: "works at X", "uses Y", "built Z", "invested in W", etc.
_RELATION_PATTERNS = {
    "works_at": re.compile(r"(work(?:s|ed|ing)?\s+(?:at|for|with))\s+([A-Z][^\s,.]{2,30})", re.IGNORECASE),
    "uses_tool": re.compile(r"(uses?|using|runs?\s+on)\s+([A-Z][^\s,.]{2,30})", re.IGNORECASE),
    "built": re.compile(r"(built|created|developed|authored|wrote)\s+([A-Z][^\s,.]{2,30})", re.IGNORECASE),
    "invested_in": re.compile(r"(invest(?:ed|s)?\s+in)\s+([A-Z][^\s,.]{2,30})", re.IGNORECASE),
    "founded": re.compile(r"(founded|started|co-founded)\s+([A-Z][^\s,.]{2,30})", re.IGNORECASE),
    "mentioned_in": re.compile(r"(mentioned|referenced|noted)\s+(?:in|by)\s+([A-Z][^\s,.]{2,30})", re.IGNORECASE),
}


# ---------------------------------------------------------------------------
# Schema packs
# ---------------------------------------------------------------------------

DEFAULT_SCHEMA = {
    "page_types": {
        "person": {"fields": ["name", "role", "company", "email", "skills", "notes"]},
        "project": {"fields": ["name", "description", "status", "tech_stack", "url", "notes"]},
        "company": {"fields": ["name", "industry", "size", "url", "notes"]},
        "tool": {"fields": ["name", "category", "url", "notes"]},
        "concept": {"fields": ["name", "domain", "definition", "notes"]},
        "meeting": {"fields": ["title", "date", "attendees", "summary", "action_items"]},
    },
    "relation_types": ["works_at", "uses_tool", "built", "invested_in", "founded", "mentioned_in", "knows", "related_to"],
}


class KnowledgeGraph:
    """Self-wiring knowledge graph with entity extraction and typed edges.

    Parameters
    ----------
    db_path:
        Path to the SQLite database for the graph.
    schema:
        Schema pack configuration (defaults to DEFAULT_SCHEMA).
    """

    def __init__(self, db_path: Path, schema: dict | None = None) -> None:
        self._db_path = db_path
        self._schema = schema or DEFAULT_SCHEMA
        self._conn: sqlite3.Connection | None = None
        self._init_lock: "asyncio.Lock | None" = None  # created lazily in _get_conn
        self._write_lock: "asyncio.Lock | None" = None  # created lazily in _get_write_lock

    async def initialize(self) -> None:
        """Create tables if they don't exist."""
        import asyncio

        def _sync() -> None:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""CREATE TABLE IF NOT EXISTS entities (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, type TEXT NOT NULL,
                data TEXT DEFAULT '{}', source TEXT, created_at TEXT,
                updated_at TEXT)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS edges (
                id TEXT PRIMARY KEY, source_id TEXT NOT NULL, target_id TEXT NOT NULL,
                relation TEXT NOT NULL, confidence REAL DEFAULT 1.0,
                evidence TEXT, created_at TEXT,
                FOREIGN KEY(source_id) REFERENCES entities(id),
                FOREIGN KEY(target_id) REFERENCES entities(id))""")
            conn.execute("""CREATE TABLE IF NOT EXISTS pages (
                id TEXT PRIMARY KEY, path TEXT NOT NULL, title TEXT,
                content TEXT, page_type TEXT, metadata TEXT DEFAULT '{}',
                indexed_at TEXT)""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type)")
            conn.commit()
            self._conn = conn

        await asyncio.to_thread(_sync)

    async def _get_write_lock(self) -> "asyncio.Lock":
        """Return a shared asyncio.Lock for write operations.

        Created lazily so the lock lives on the same event loop as the
        first caller.
        """
        import asyncio as _asyncio

        if self._write_lock is None:
            self._write_lock = _asyncio.Lock()
        return self._write_lock

    async def _get_conn(self) -> sqlite3.Connection:
        """Lazy-initialize and return the SQLite connection.

        Uses double-checked locking so multiple concurrent callers
        only trigger initialization once.
        """
        import asyncio as _asyncio

        if self._conn is None:
            if self._init_lock is None:
                self._init_lock = _asyncio.Lock()
            async with self._init_lock:
                if self._conn is None:  # double-check after acquiring lock
                    await self.initialize()
        assert self._conn is not None
        return self._conn

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    async def ingest_page(self, path: Path, content: str, page_type: str = "concept") -> str:
        """Ingest a markdown page, extracting entities and relations.

        Write operations are serialised through an ``asyncio.Lock`` so
        concurrent callers cannot interleave writes on the thread pool.
        """
        import asyncio

        page_id = hashlib.sha256(str(path).encode()).hexdigest()[:16]
        title = path.stem.replace("-", " ").title()
        now = datetime.now(UTC).isoformat()

        # Extract entities and relations (pure Python, no lock needed).
        entities = self._extract_entities(content)
        edges = self._extract_relations(content, entities)

        await self._get_conn()  # ensure initialized

        def _sync() -> None:
            # Store page.
            self._conn.execute(  # type: ignore[union-attr]
                "INSERT OR REPLACE INTO pages(id, path, title, content, page_type, indexed_at) VALUES(?,?,?,?,?,?)",
                (page_id, str(path), title, content, page_type, now),
            )
            # Store entities.
            for ent in entities:
                ent_id = hashlib.sha256(f"{ent['name']}:{ent['type']}".encode()).hexdigest()[:16]
                self._conn.execute(
                    "INSERT OR REPLACE INTO entities(id, name, type, data, source, created_at, updated_at) VALUES(?,?,?,?,?,?,?)",
                    (ent_id, ent["name"], ent["type"], json.dumps(ent.get("data", {})), str(path), now, now),
                )
            # Store edges.
            for edge in edges:
                edge_id = hashlib.sha256(f"{edge['source']}:{edge['relation']}:{edge['target']}".encode()).hexdigest()[:16]
                try:
                    self._conn.execute(
                        "INSERT OR REPLACE INTO edges(id, source_id, target_id, relation, confidence, evidence, created_at) VALUES(?,?,?,?,?,?,?)",
                        (edge_id, edge["source"], edge["target"], edge["relation"], edge.get("confidence", 1.0), edge.get("evidence", ""), now),
                    )
                except sqlite3.IntegrityError:
                    pass
            self._conn.commit()

        # Serialise writes: only one ingest_page at a time.
        write_lock = await self._get_write_lock()
        async with write_lock:
            await asyncio.to_thread(_sync)
        return page_id

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    async def graph_query(self, entity_name: str, max_hops: int = 2) -> list[dict]:
        """Traverse the graph from an entity, returning connected nodes."""
        import asyncio

        await self._get_conn()  # ensure initialized

        def _sync() -> list[dict]:
            results: list[dict] = []
            visited: set[str] = set()

            # Find starting entity.
            row = self._conn.execute(  # type: ignore[union-attr]
                "SELECT id, name, type FROM entities WHERE name LIKE ? LIMIT 1",
                (f"%{entity_name}%",),
            ).fetchone()
            if not row:
                return []

            queue = [(row["id"], 0)]
            while queue:
                cur_id, depth = queue.pop(0)
                if cur_id in visited or depth > max_hops:
                    continue
                visited.add(cur_id)
                entity = self._conn.execute(
                    "SELECT * FROM entities WHERE id = ?", (cur_id,)
                ).fetchone()
                if entity:
                    results.append(_row_to_dict(entity))
                edges = self._conn.execute(
                    "SELECT * FROM edges WHERE source_id = ? OR target_id = ?",
                    (cur_id, cur_id),
                ).fetchall()
                for edge in edges:
                    neighbor = edge["target_id"] if edge["source_id"] == cur_id else edge["source_id"]
                    if neighbor not in visited:
                        queue.append((neighbor, depth + 1))
            return results

        return await asyncio.to_thread(_sync)

    async def search_entities(self, query: str, k: int = 10) -> list[dict]:
        """Search entities by name (keyword match)."""
        import asyncio

        await self._get_conn()  # ensure initialized

        def _sync() -> list[dict]:
            rows = self._conn.execute(  # type: ignore[union-attr]
                "SELECT * FROM entities WHERE name LIKE ? LIMIT ?",
                (f"%{query}%", k),
            ).fetchall()
            return [_row_to_dict(r) for r in rows]

        return await asyncio.to_thread(_sync)

    async def get_stats(self) -> dict:
        import asyncio

        await self._get_conn()  # ensure initialized

        def _sync() -> dict:
            return {
                "pages": self._conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0],  # type: ignore[union-attr]
                "entities": self._conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0],  # type: ignore[union-attr]
                "edges": self._conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0],  # type: ignore[union-attr]
            }

        return await asyncio.to_thread(_sync)

    async def get_storage_stats(self) -> dict:
        """Return storage stats including DB file size."""
        import asyncio
        import os as _os
        stats = await self.get_stats()
        db_size = _os.path.getsize(str(self._db_path)) if self._db_path.exists() else 0
        stats["db_size_bytes"] = db_size
        return stats

    async def get_orphan_edge_count(self) -> int:
        """Count edges with broken foreign keys."""
        import asyncio
        await self._get_conn()

        def _sync() -> int:
            # Edges pointing to non-existent entities
            cursor = self._conn.execute(  # type: ignore[union-attr]
                """SELECT COUNT(*) FROM edges
                   WHERE source_id NOT IN (SELECT id FROM entities)
                      OR target_id NOT IN (SELECT id FROM entities)"""
            )
            return cursor.fetchone()[0]

        return await asyncio.to_thread(_sync)

    async def cleanup_orphan_edges(self) -> int:
        """Delete edges with broken foreign keys. Returns count removed."""
        import asyncio
        await self._get_conn()

        def _sync() -> int:
            cursor = self._conn.execute(  # type: ignore[union-attr]
                """SELECT id FROM edges
                   WHERE source_id NOT IN (SELECT id FROM entities)
                      OR target_id NOT IN (SELECT id FROM entities)"""
            )
            orphan_ids = [r[0] for r in cursor.fetchall()]
            for oid in orphan_ids:
                self._conn.execute("DELETE FROM edges WHERE id = ?", (oid,))  # type: ignore[union-attr]
            self._conn.commit()  # type: ignore[union-attr]
            return len(orphan_ids)

        return await asyncio.to_thread(_sync)

    async def close(self) -> None:
        import asyncio

        def _sync() -> None:
            if self._conn:
                self._conn.close()
        await asyncio.to_thread(_sync)

    # ------------------------------------------------------------------
    # Extraction (zero LLM cost)
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_entities(content: str) -> list[dict]:
        entities: list[dict] = []
        seen: set[str] = set()

        for match in _PERSON_PATTERN.finditer(content):
            name = match.group(1)
            if name not in seen:
                seen.add(name)
                entities.append({"name": name, "type": "person"})

        for match in _ORG_PATTERN.finditer(content):
            name = match.group(0)
            if name not in seen:
                seen.add(name)
                entities.append({"name": name, "type": "company"})

        return entities

    @staticmethod
    def _extract_relations(content: str, entities: list[dict]) -> list[dict]:
        edges: list[dict] = []
        entity_names = {e["name"].lower() for e in entities}

        for rel_type, pattern in _RELATION_PATTERNS.items():
            for match in pattern.finditer(content):
                target_candidate = match.group(2)
                # Find the closest preceding entity.
                before = content[: match.start()]
                for ent_name in sorted(entity_names, key=lambda n: -len(n)):
                    idx = before.rfind(ent_name.lower())
                    if idx >= 0 and (match.start() - idx) < 200:
                        source_id = hashlib.sha256(f"{ent_name}:person".encode()).hexdigest()[:16]
                        target_id = hashlib.sha256(f"{target_candidate}:company".encode()).hexdigest()[:16]
                        edges.append({
                            "source": source_id,
                            "target": target_id,
                            "relation": rel_type,
                            "confidence": 0.8,
                            "evidence": match.group(0),
                        })
                        break
        return edges


# ---------------------------------------------------------------------------
# Brain repo sync
# ---------------------------------------------------------------------------


async def sync_brain_repo(repo_dir: Path, kg: KnowledgeGraph, page_type: str = "concept") -> dict:
    """Sync a directory of markdown files into the knowledge graph."""
    stats = {"synced": 0, "skipped": 0, "errors": 0}
    for md_file in sorted(repo_dir.rglob("*.md")):
        if md_file.name.startswith("."):
            continue
        try:
            content = md_file.read_text(encoding="utf-8")
            await kg.ingest_page(md_file, content, page_type)
            stats["synced"] += 1
        except Exception:
            stats["errors"] += 1
    return stats
