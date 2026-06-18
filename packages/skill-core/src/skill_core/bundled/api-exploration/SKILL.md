---
name: api-exploration
description: API discovery, endpoint mapping, schema extraction, rate limit handling, pagination patterns.
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 🔌
---

# API Exploration

## Overview
Discover, map, and interact with REST APIs. Handle authentication, pagination, rate limits, error recovery.

## Process
1. Find docs: OpenAPI spec, developer portal, or inspect network traffic
2. Auth: identify method (Bearer, API Key, OAuth, Basic)
3. Test: curl or httpx with minimal viable request
4. Map: document endpoints, params, response schemas
5. Handle edges: pagination, rate limits, errors

## Rate Limit Handling
```python
import time, httpx
async def rate_limited_get(url, headers):
    while True:
        resp = await client.get(url, headers=headers)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 5))
            time.sleep(retry_after)
            continue
        return resp
```

## Anti-Patterns
- Don't hardcode API keys in scripts
- Don't assume pagination style (offset, cursor, page)
- Don't ignore rate limit headers
