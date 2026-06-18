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
from datetime import datetime, timezone
from pathlib import Path

import sqlite3


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

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    async def ingest_page(self, path: Path, content: str, page_type: str = "concept") -> str:
        """Ingest a markdown page, extracting entities and relations."""
        import asyncio

        page_id = hashlib.sha256(str(path).encode()).hexdigest()[:16]
        title = path.stem.replace("-", " ").title()
        now = datetime.now(timezone.utc).isoformat()

        # Extract entities and relations.
        entities = self._extract_entities(content)
        edges = self._extract_relations(content, entities)

        def _sync() -> None:
            if self._conn is None:
                raise RuntimeError("Not initialized")
            # Store page.
            self._conn.execute(
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

        await asyncio.to_thread(_sync)
        return page_id

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    async def graph_query(self, entity_name: str, max_hops: int = 2) -> list[dict]:
        """Traverse the graph from an entity, returning connected nodes."""
        import asyncio

        def _sync() -> list[dict]:
            if self._conn is None:
                return []
            results: list[dict] = []
            visited: set[str] = set()

            # Find starting entity.
            row = self._conn.execute(
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

        def _sync() -> list[dict]:
            if self._conn is None:
                return []
            rows = self._conn.execute(
                "SELECT * FROM entities WHERE name LIKE ? LIMIT ?",
                (f"%{query}%", k),
            ).fetchall()
            return [_row_to_dict(r) for r in rows]

        return await asyncio.to_thread(_sync)

    async def get_stats(self) -> dict:
        import asyncio

        def _sync() -> dict:
            if self._conn is None:
                return {}
            return {
                "pages": self._conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0],
                "entities": self._conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
                "edges": self._conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0],
            }

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
