---
name: memory-management
description: MEMORY.md curation, fact deduplication, importance scoring. Keep the agent's memory clean and high-signal.
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 🧠
---

# Memory Management

## Overview
Curate JalaAgent's MEMORY.md. Remove noise, deduplicate facts, score importance. High-signal memory = better responses.

## Process
1. Read full MEMORY.md
2. Flag: duplicates, contradictions, outdated info, low-value entries
3. Deduplicate: keep highest-confidence version of each fact
4. Score importance: 0.0 (trivial) to 1.0 (critical)
5. Remove facts below 0.3 importance unless user-pinned
6. Group related facts under category headers

## Importance Scoring
- 1.0: User identity, core preferences, ongoing projects
- 0.7: Technical preferences, tools, recurring patterns
- 0.5: One-off facts, historical context
- 0.3: Session-specific details (auto-expire after 30 days)
- 0.1: Noise to remove

## Memory Format
```markdown
## [Category]
- [YYYY-MM-DD] [0.X] Fact description. <!-- id:uuid -->
```

## Anti-Patterns
- Don't store temporary context as permanent memory
- Don't duplicate facts that already exist in session transcripts
- Don't remove facts without user approval (unless auto-expired)
