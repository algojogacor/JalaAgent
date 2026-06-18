---
name: brain-management
description: Unified GBrain knowledge curation — replaces 4 Hermes skills. Direct memory_core API access for vector search, graph traversal, page ingestion, and brain health.
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 🧠
    provenance:
      source: jalaagent-exclusive
      replaces: [gbrain-companion, gbrain-signal-detector, gbrain-setup, gbrain-git-wrapper]
---

# Brain Management

## Overview
Unified knowledge curation using JalaAgent's native GBrain layer. Hermes needs 4 separate skills for knowledge management. JalaAgent has it built into `memory_core`. This skill directly calls `knowledge_graph.ingest_page()`, `vector_layer.search()`, and `file_layer.read_memory()`.

## JalaAgent Advantage
- **Native, not bolted on** — No external binary, no git wrapper, no setup script
- **4-layer integration** — Graph entities link to vector embeddings link to file entries
- **Dreaming pipeline** — Auto-consolidation runs daily, no cron setup needed
- **Schema packs** — Configurable page types (person, project, company, tool, concept, meeting)

## Process

### 1. Ingest Knowledge
```python
from memory_core.knowledge_graph import KnowledgeGraph, sync_brain_repo
from pathlib import Path
import asyncio

async def ingest_directory(repo_path: str, page_type: str = "concept"):
    kg = KnowledgeGraph(Path("~/.jalaagent/db/knowledge.db").expanduser())
    await kg.initialize()
    stats = await sync_brain_repo(Path(repo_path), kg, page_type)
    return stats  # {"synced": N, "skipped": N, "errors": N}
```

### 2. Search with Context
```python
# Vector + keyword hybrid search
from memory_core.retrieval import MemoryRetriever
results = await retriever.retrieve("What does Arya use for local inference?")

# Entity-aware graph search
entities = await kg.search_entities("Arya")
graph = await kg.graph_query("Arya", max_hops=2)
```

### 3. Curate MEMORY.md
- Read: `file_layer.read_memory()`
- Deduplicate facts by SHA1 hash
- Score importance 0.0-1.0
- Remove stale entries below threshold

### 4. Health Check
```python
stats = await kg.get_stats()
health = {
    "pages": stats["pages"],
    "entities": stats["entities"],
    "edges": stats["edges"],
    "status": "healthy" if stats["pages"] > 0 else "empty",
    "recommendation": "Run dreaming pipeline" if stats["pages"] < 10 else "Good coverage"
}
```

## Anti-Patterns
- Don't ingest without specifying page_type (uses wrong schema)
- Don't search vector layer without threshold (noise overwhelms signal)
- Don't let knowledge graph go stale (dreaming pipeline must run)
