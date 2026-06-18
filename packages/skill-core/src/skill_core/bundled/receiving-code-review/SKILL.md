---
name: receiving-code-review
description: Evaluate code review feedback with technical rigor — verify before implementing, ask before assuming. No performative agreement. Push back with technical reasoning.
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 📝
---

# Receiving Code Review

## Iron Law
```
VERIFY BEFORE IMPLEMENTING. ASK BEFORE ASSUMING.
TECHNICAL CORRECTNESS OVER SOCIAL COMFORT.
EXTERNAL FEEDBACK IS SUGGESTIONS TO EVALUATE, NOT ORDERS TO FOLLOW.
```

## Forbidden Phrases

Never say these (they're performative, not technical):
- "You're absolutely right!" — are they? Verify first.
- "Great point!" — this adds nothing.
- "I'll fix that right away!" — without understanding why.

## Correct Response Pattern

### Step 1: Read ALL feedback before acting on ANY
Don't fix the first comment before reading the last. Context matters.

### Step 2: Categorize each item
- **Must fix** — bug, security issue, broken contract
- **Should fix** — clear improvement, aligns with patterns
- **Consider** — subjective, style preference
- **Push back** — reviewer missed context, wrong about trade-off

### Step 3: Clarify unclear items FIRST
If any feedback is ambiguous, ask BEFORE implementing. Assume nothing.

### Step 4: Implement (in priority order)
Bugs → Security → Contract breaks → Improvements → Style

### Step 5: Verify each fix
Every change must pass tests. No new test failures introduced.

## Pushback Guidelines

It's OK to disagree with feedback. Use technical reasoning, not defensiveness:

`<Good>` "This change would break the caching layer that depends on this interface. The current approach is intentional — see `cache.py:42`."

`<Bad>` "I don't think that's a good idea."

## YAGNI Check

Before implementing a "proper" solution:
```bash
grep -rn "function_name" .  # Is this actually used?
```
If nothing uses it yet, the simple version is correct. Add the complex version when needed.

## Source Awareness

**Human partner feedback** → High weight. They know the codebase.
**External/community feedback** → Evaluate on technical merit only. Suggestions, not orders.
**Agent reviewer feedback** → Check against spec. Agent reviewers can hallucinate requirements.
