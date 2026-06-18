---
name: pre-commit-verification
description: 8-step pre-commit pipeline — static scan, baseline tests, independent review, auto-fix loop. No agent verifies its own work. Non-empty concerns = auto-fail.
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata: jalaagent: always: false; emoji: 🔍
---

# Pre-Commit Verification

## Iron Law
```
NO AGENT SHALL VERIFY ITS OWN WORK.
FRESH CONTEXT FINDS WHAT FAMILIAR CONTEXT MISSES.
NON-EMPTY CONCERNS = AUTO-FAIL.
```

## 8-Step Pipeline

### Step 1: Get the Diff
```bash
BASE_SHA=$(git merge-base origin/main HEAD)
git diff $BASE_SHA..HEAD > changes.diff
```

### Step 2: Static Security Scan
```bash
grep -nE '(eval\(|exec\(|__import__\()' changes.diff  # dangerous-exec
grep -nE '(TODO.*password|API.?KEY|secret)' changes.diff  # credential leak
grep -nE '(subprocess.*shell=True)' changes.diff  # shell injection
```

### Step 3: Baseline Tests
```bash
git stash && uv run pytest && TEST_BASELINE=$?  # pre-change baseline
git stash pop && uv run pytest                 # post-change
# Only NEW failures matter
```

### Step 4: Self-Review
Review your own diff. Be your harshest critic. Note any concerns.

### Step 5: Independent Reviewer
Dispatch a **different** subagent (not the implementer, not the orchestrator) to review `diff` against `spec`.
- If concerns list is non-empty → **AUTO-FAIL**. Fix required.

### Step 6: Evaluate
- Critical findings → fix immediately
- Important findings → fix before commit
- Minor → note, fix later

### Step 7: Auto-Fix Loop
```
MAX 2 CYCLES.
For each concern:
  1. Apply fix
  2. Re-run tests
  3. If tests fail → revert, flag for manual attention
  4. If tests pass → continue
```

### Step 8: Commit
```bash
git commit -m "[verified] <description>"
```
The `[verified]` prefix is audit trail — it means this pipeline ran and passed.

## Common Patterns

- Different model for reviewer (best available) vs implementer (cheapest capable)
- Fresh subagent context — no inherited session history
- Review happens BEFORE merge, not after
