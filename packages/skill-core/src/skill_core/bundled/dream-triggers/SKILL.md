---
name: dream-triggers
description: When and how to invoke dreaming mid-session. Auto-trigger rules, manual /dream command, post-session consolidation.
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 🌙
    provenance:
      source: jalaagent-exclusive
---

# Dream Triggers

## Overview
JalaAgent's dreaming pipeline runs inside the agent process. This skill defines when to trigger it for maximum memory consolidation.

## Auto-Trigger Rules
1. After session with 10+ tool calls → light consolidation
2. After important decision (user said "remember this") → immediate fact extraction
3. Daily at 3 AM (if `dreaming.enabled` in config)
4. After ingesting 5+ new knowledge graph pages
5. After user explicitly types `/dream`

## Manual Trigger
```
/dream                # Run full pipeline now
/dream light          # Light sleep only (scan recent sessions)
/dream status         # Show last dream report
```

## Dream Report Format
```python
from memory_core.dreaming_runner import DreamingRunner
runner = DreamingRunner(config, file_layer, vector_layer, provider)
report = await runner.run_once()
print(f"Signals: {report.light_sleep_signals}")
print(f"Patterns: {report.rem_patterns}")
print(f"Promoted: {report.deep_sleep_promotions}")
```

## Anti-Patterns
- Don't trigger dreaming during active conversation (runs in background)
- Don't expect instant results (dreaming processes session transcripts)
- Don't run more than once per hour (deduplication needs accumulation)
