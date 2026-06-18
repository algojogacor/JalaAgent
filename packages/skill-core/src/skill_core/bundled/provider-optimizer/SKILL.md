---
name: provider-optimizer
description: Select optimal model/provider based on task type, token cost, and pool health. Leverages CredentialPool health checks.
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 🤖
    provenance:
      source: jalaagent-exclusive
---

# Provider Optimizer

## Overview
Automatically select the best model/provider for each task. Consider: task complexity, token cost, credential pool health, and latency requirements.

## Selection Matrix
| Task Type | Best Model | Fallback |
|-----------|-----------|----------|
| Code generation | claude-sonnet-4-6 | gpt-4o |
| Bug fixing | claude-sonnet-4-6 | deepseek-chat |
| Architecture design | claude-opus-4-6 | claude-sonnet-4-6 |
| Simple queries | claude-haiku-4-5 | groq-llama-4 |
| Bulk processing | groq-llama-4 | deepseek-chat |
| Offline/private | ollama-local | N/A |
| Cost-sensitive | deepseek-chat | groq-llama-4 |
| Vision tasks | claude-sonnet-4-6 | gpt-4o |

## Auto-Selection Algorithm
```python
async def select_provider(task: str, pool: CredentialPool):
    complexity = estimate_complexity(task)
    if complexity > 0.8:
        candidates = ["claude-opus-4-6", "claude-sonnet-4-6"]
    elif complexity > 0.5:
        candidates = ["claude-sonnet-4-6", "gpt-4o"]
    else:
        candidates = ["claude-haiku-4-5", "deepseek-chat", "groq-llama-4"]
    for provider in candidates:
        cred = await pool.acquire(provider)
        if cred and cred.is_healthy:
            return provider
    return "ollama"  # ultimate fallback
```

## Pool Health Integration
Check pool health before selecting: if primary provider has 0 healthy keys, skip to backup even for complex tasks.

## Anti-Patterns
- Don't use expensive models for simple string manipulation
- Don't ignore pool health (calling a provider with 0 healthy keys is wasted time)
- Don't hardcode model names (pool may have different models available)
