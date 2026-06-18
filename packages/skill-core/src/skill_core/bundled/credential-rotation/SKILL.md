---
name: credential-rotation
description: Auto-rotate credentials mid-session on auth/rate-limit errors. Integration with CredentialPool for failover.
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 🔑
    provenance:
      source: jalaagent-exclusive
      replaces: [hermes-credential-proxy]
---

# Credential Rotation

## Overview
JalaAgent's native CredentialPool handles multi-key rotation without external proxies. On auth failure or rate limit, automatically switch to the next healthy credential.

## JalaAgent Advantage
Hermes needs `hermes-credential-proxy` (external Flask proxy) for multi-key rotation. JalaAgent has `agent-core/credentials.py` built into the agent loop. No external process needed.

## Auto-Rotation Flow
```
Provider call fails with 401/429
  → APIErrorClassifier.classify() → FailoverReason
  → CredentialPool.report_failure() → exponential cooldown
  → CredentialPool.acquire() → next healthy credential
  → Retry with new key
```

## Pool Configuration
```python
from agent_core.credentials import CredentialPool
pool = CredentialPool()
pool.add("anthropic", "sk-ant-primary", {"tier": "pro"})
pool.add("anthropic", "sk-ant-backup", {"tier": "backup"})
pool.add_from_env("openai", "OPENAI_API_KEYS")  # comma-separated
```

## Health Check
```python
status = await pool.status()
for provider, info in status.items():
    print(f"{provider}: {info['healthy']}/{info['total']} healthy")
```

## Anti-Patterns
- Don't put all keys in a single env var without backup keys
- Don't ignore cooldown (let rate-limited keys recover)
- Don't remove failed keys without checking if they recovered
