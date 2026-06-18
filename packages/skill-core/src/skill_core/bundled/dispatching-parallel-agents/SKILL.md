---
name: dispatching-parallel-agents
description: Run multiple independent investigations or tasks concurrently. Independence check first, then dispatch, then review and integrate. Never dispatch parallel implementations.
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata: jalaagent: always: false; emoji: ⚡
---

# Dispatching Parallel Agents

## Iron Law
```
NEVER DISPATCH PARALLEL IMPLEMENTATION AGENTS. THEY WILL CONFLICT.
ONLY DISPATCH PARALLEL INVESTIGATION AGENTS. THEY ARE INDEPENDENT.
VERIFY INDEPENDENCE BEFORE DISPATCH. REVIEW CONFLICTS AFTER.
```

## When To Use

- Searching multiple codebases/directories simultaneously
- Investigating different hypotheses about a bug
- Researching different approaches to a problem
- Running independent verifications (lint, test, type-check) concurrently

## When NOT To Use

- Implementing code that modifies the same files
- Tasks with sequential dependencies

## Process

### Step 1: Identify Independent Work
List tasks. For each pair, ask: "Could these run at the same time without conflicts?"

### Step 2: Create Agent Prompts
Each agent gets a **focused, self-contained** prompt:
- Exact search scope (directory, pattern, time range)
- Exact output format expected
- No inherited session context — construct exactly what they need

### Step 3: Dispatch
```python
results = await dispatch_parallel([
    agent("Search packages/ for usage of ToolRegistry", schema=FINDINGS),
    agent("Search extensions/ for usage of ToolRegistry", schema=FINDINGS),
    agent("Search tests/ for usage of ToolRegistry", schema=FINDINGS),
])
```

### Step 4: Review and Integrate
- Verify no findings conflict
- Merge complementary results
- Flag contradictory findings for manual review

## Common Mistakes

❌ Bad: 3 agents each modifying `auth.py`  
✅ Good: 3 agents searching different directories for auth-related code

❌ Bad: Agent inherits full conversation context (gets confused)  
✅ Good: Agent receives exactly the search scope + output format
