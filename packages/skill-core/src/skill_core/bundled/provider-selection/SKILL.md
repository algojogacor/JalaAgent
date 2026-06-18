---
name: provider-selection
description: Model selection strategy, fallback chains, cost optimization. Pick the right model for the task.
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 🤖
---

# Provider Selection

## Overview
Choose the optimal model for each task based on complexity, cost, and capability requirements.

## Model Tiers
- **Tier 1 (Best)**: claude-sonnet-4-6, claude-opus-4-6 — Complex reasoning, architecture, security review
- **Tier 2 (Good)**: gpt-4o, gemini-2.5-flash, deepseek-chat — General coding, analysis
- **Tier 3 (Fast)**: claude-haiku-4-5, groq-llama-4 — Simple tasks, bulk processing
- **Tier 4 (Local)**: ollama models — Offline, sensitive data, free

## Selection Rules
- Architecture/design → Tier 1
- Bug fixing → Tier 2 (systematic-debugging skill)
- Code generation → Tier 2
- Code review → Tier 1 (reviewer must be better than implementer)
- Bulk/simple → Tier 3
- Offline/private → Tier 4

## Fallback Chain
If primary model fails (rate limit, auth error):
1. Same tier, different provider
2. One tier down, same provider
3. Any available provider

## Anti-Patterns
- Don't use Tier 1 for simple string manipulation
- Don't use Tier 4 for security-critical review
- Don't stick with one model when another is clearly better for the task
