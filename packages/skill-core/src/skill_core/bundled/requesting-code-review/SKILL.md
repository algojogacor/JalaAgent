---
name: requesting-code-review
description: >-
  Dispatch an independent reviewer subagent with precise git SHAs. Fail-closed: non-empty concerns = auto-fail. Auto-fix loop capped at 2 cycles.
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 👀
---

# Requesting Code Review

## Iron Law
```
NO AGENT VERIFIES ITS OWN WORK.
FRESH CONTEXT FINDS WHAT FAMILIAR CONTEXT MISSES.
NON-EMPTY CONCERNS = AUTO-FAIL.
```

## Process

### Step 1: Compute Diff Range
```bash
BASE_SHA=$(git merge-base origin/main HEAD)
HEAD_SHA=$(git rev-parse HEAD)
```

### Step 2: Dispatch Independent Reviewer
Use `delegate_task` with a DIFFERENT model than the implementer. The reviewer receives:
- The diff: `git diff $BASE_SHA..$HEAD_SHA`
- The spec/plan the implementer followed
- Context about the codebase conventions

### Step 3: Review Dimensions
- **Correctness**: Does it do what the spec says?
- **Security**: Any injection, leak, or unsafe patterns?
- **Performance**: Obvious N+1 queries, memory leaks?
- **Reuse**: Duplicated existing functionality?
- **Simplicity**: Could this be simpler without losing functionality?

### Step 4: Evaluate Findings
```
Critical  → Fix now. Cannot proceed without it.
Important → Fix before merge. Won't break prod but should be addressed.
Minor     → Note for later. Style, naming, optional improvements.
```

### Step 5: Auto-Fix Loop (MAX 2 CYCLES)
For each concern:
1. Apply the fix
2. Re-run tests
3. If tests fail → revert, flag for manual attention
4. If tests pass → commit with `[verified]` prefix

## Reviewer Prompt Template
```markdown
Review the following diff against the spec below.

SPEC:
{spec_content}

DIFF:
```diff
{diff_content}
```

Check for: correctness, security, performance, reuse, simplicity.
Return a JSON list of concerns (empty list if none):
[{"severity": "critical|important|minor", "file": "...", "line": N, "description": "..."}]
```
