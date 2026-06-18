---
name: memory-consolidation
description: Post-session fact extraction, dedup, and promotion. Tight integration with dreaming pipeline and knowledge graph.
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 💾
    provenance:
      source: jalaagent-exclusive
---

# Memory Consolidation

## Overview
After every session, extract facts automatically and promote them to MEMORY.md. Tight integration with JalaAgent's 4-layer memory architecture.

## Post-Session Flow
```
Session ends
  → Background self-improvement task fires
  → light_sleep: scan session JSONL for new signals
  → rem_sleep: LLM extracts atomic facts
  → deep_sleep: filter by confidence >= 0.7
  → promote: write to MEMORY.md
  → index: upsert into knowledge graph + vector layer
  → diary: append to dream-diary.md
```

## Fact Extraction Pattern
```python
# The dreaming pipeline extracts facts like:
# "User prefers Python with type hints" (confidence: 0.92)
# "User deploys to Cloud Run using Docker" (confidence: 0.88)
# "User develops on Windows 11 with WSL2" (confidence: 0.95)
```

## Consolidation Rules
- Facts below 0.7 confidence → skip (not reliable enough)
- Duplicate facts (SHA1 match) → merge, keep highest confidence
- Facts older than 30 days with no re-confirmation → auto-expire
- User-pinned facts → never auto-expire

## Anti-Patterns
- Don't promote facts from a single mention (need 2+ occurrences)
- Don't consolidate during active conversation
- Don't overwrite user-curated MEMORY.md entries
