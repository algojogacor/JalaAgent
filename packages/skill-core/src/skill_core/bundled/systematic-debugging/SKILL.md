---
name: systematic-debugging
description: >-
  Four-phase root cause debugging — investigate before fixing. No fixes without root cause identification. Rule of Three: after 3 failed attempts, question architecture.
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 🐛
    requires:
      bins: []
      env: []
---

# Systematic Debugging

Four-phase root cause debugging that enforces investigation before any fix attempts. Average fix time: 15-30 minutes vs 2-3 hours of random guessing.

## Iron Law

```
NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST.
AFTER 3 FAILED FIX ATTEMPTS, STOP. QUESTION THE ARCHITECTURE.
```

## When To Use

- Any bug where the cause is not immediately obvious
- Intermittent failures
- Regression after a change

## Four Phases

### Phase 1: Root Cause Investigation
1. Reproduce the bug consistently
2. Identify exact failure point (log, stack trace, assertion)
3. Trace data flow backward from failure to source
4. Identify the earliest point where expected ≠ actual
5. State the root cause as a single sentence

### Phase 2: Pattern Analysis
1. Check: has this bug occurred before? (search issues, commits)
2. Check: are there similar patterns elsewhere in the codebase?
3. Check: was this introduced by a recent change? (`git bisect`)

### Phase 3: Hypothesis
1. Write down: "If root cause is X, then changing Y should fix it"
2. Make ONE change
3. Verify the change fixes the bug AND doesn't break anything else

### Phase 4: Implementation
1. Write a regression test that fails WITHOUT the fix
2. Apply the fix
3. Watch the test pass
4. Run full test suite

## Multi-Component Diagnostic Pattern

When a bug spans multiple components, instrument at boundaries:
```python
logger.debug("Component A → B: input=%s", value)
logger.debug("Component B → C: transformed=%s", transformed)
```
This creates a data flow trace showing exactly where values diverge from expectations.

## Rule of Three

After 3 failed fix attempts:
- STOP adding code
- Question the interface design
- Question the data model
- Consider: is the abstraction wrong?

## Common Rationalizations

| Excuse | Reality |
|--------|---------|
| "I know what the bug is" | If you knew, you'd have fixed it already. |
| "It's a simple typo" | Simple bugs expose missing tests. |
| "Just one more attempt" | After 3, each attempt makes things worse. |

## Integration

- Write regression tests via **test-driven-development**
- After fixing, request review via **requesting-code-review**
