# Memory System — 4-Layer Hybrid

## Layer 1: File Storage
- `~/.jalaagent/memories/MEMORY.md` — curated facts, human-readable
- `~/.jalaagent/memories/USER.md` — user profile
- `~/.jalaagent/memories/sessions/YYYY-MM-DD.jsonl` — session transcripts
- Atomic writes, drift detection, frozen snapshot pattern

## Layer 2: Vector Database
- SQLite + sqlite-vec for KNN similarity search
- FTS5 full-text search with BM25 ranking
- Embedding via Ollama (qwen3:0.6b, 1024-dim)
- Cosine similarity fallback when sqlite-vec unavailable

## Layer 3: Dreaming Pipeline
- Cron-based (default: 3 AM daily)
- Light Sleep → REM → Deep Sleep
- Fact extraction via LLM, SHA1 deduplication
- Promotes high-confidence facts to MEMORY.md
- Dream diary at `~/.jalaagent/memories/dream-diary.md`

## Layer 4: Knowledge Graph
- Entity extraction (regex, zero LLM cost)
- Typed relation edges (works_at, uses_tool, built, invested_in)
- Graph traversal with max_hops
- Brain repo sync from markdown directories

## Retrieval Flow
```
Query → sqlite-vec KNN → FTS5 keyword → Knowledge Graph → MEMORY.md scan
     → merge + deduplicate + threshold filter → <memory-context> XML
```
