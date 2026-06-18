---
name: agent-benchmark
description: Self-evaluation suite — measure tool accuracy, memory recall precision, provider latency. No Hermes equivalent.
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 📊
    provenance:
      source: jalaagent-exclusive
---

# Agent Benchmark

## Overview
Run self-evaluation tests to measure JalaAgent's performance. Tool accuracy, memory recall, provider latency, skill triggering precision.

## Benchmarks

### 1. Tool Accuracy
Run 10 test prompts that should trigger specific tools. Measure:
- Was the correct tool called? (precision)
- Were arguments correct? (accuracy)
- Was the result within expected range? (quality)

### 2. Memory Recall
Ingest 5 known facts. Query with 5 paraphrased questions. Measure:
- Recall@5: were all 5 facts returned?
- Relevance: were returned facts actually relevant?
- Latency: time from query to result

### 3. Provider Latency
Measure TTFT (time to first token) across providers:
```python
import time, asyncio
async def measure_latency(provider, prompt):
    start = time.monotonic()
    async for chunk in provider.stream_completion(prompt):
        if chunk.content:
            return time.monotonic() - start
```

### 4. Skill Triggering
Test 20 prompts. 10 should trigger specific skills. 10 should not.
Measure: precision, recall, F1 score.

### 5. Memory Health
```python
stats = await kg.get_stats()
report = {
    "total_pages": stats["pages"],
    "total_entities": stats["entities"],
    "total_edges": stats["edges"],
    "stale_pages": # pages not updated in 30 days,
    "coverage_score": min(stats["pages"] / 100, 1.0)
}
```

## Anti-Patterns
- Don't benchmark with production credentials (costs real money)
- Don't compare providers on a single prompt (use 5+ for statistical validity)
- Don't optimize for benchmark scores at expense of real-world quality
