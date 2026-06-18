---
name: brainstorming
description: Design-before-implementation with HARD GATES. Explore ideas, propose 2-3 approaches, document design, self-review, get user approval. NO implementation before approval.
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 💡
---

# Brainstorming (Design-First)

## <HARD-GATE>
```
YOU ARE IN DESIGN MODE. YOU CANNOT WRITE IMPLEMENTATION CODE.
YOU CAN READ FILES. YOU CAN PROPOSE DESIGNS. YOU CAN WRITE PLAN FILES.
YOU CANNOT EDIT SOURCE FILES. YOU CANNOT RUN IMPLEMENTATION COMMANDS.
THE USER MUST APPROVE THE DESIGN BEFORE YOU CAN PROCEED TO IMPLEMENTATION.
```

## Anti-Pattern

**"This Is Too Simple To Need A Design"** — The most expensive words in software. Every failed project started with someone saying this. If it's truly simple, the design takes 2 minutes and costs nothing. If it's not, the design saves hours.

## Process (9 Steps)

1. **Explore** — Read existing code, understand patterns, find reusable utilities
2. **Clarify** — Ask the user one question at a time until requirements are clear
3. **Propose** — Present 2-3 distinct approaches with trade-offs (not just one!)
4. **Present** — User picks an approach (or blends)
5. **Document** — Write the design to `docs/plans/YYYY-MM-DD-<topic>-design.md`
6. **Self-Review** — Placeholder scan, consistency check, scope check, ambiguity scan
7. **User Review** — Present the plan for approval
8. **Transition** — Hand off to writing-plans skill for task breakdown
9. **Implement** — Use subagent-driven-development to execute

## Design Document Template
```markdown
# Design: <Topic>
**Date:** YYYY-MM-DD
**Status:** Draft | Approved | Implemented

## Problem
<One paragraph>

## Context
- Existing patterns to follow:
- Constraints:
- Files that will change:

## Approach
<Chosen approach with rationale>

## Alternatives Considered
1. <Alternative 1> — Pros/Cons
2. <Alternative 2> — Pros/Cons

## Files to Modify
- `path/to/file.py` — <what changes>

## Files to Create
- `path/to/new.py` — <what it does>

## Verification
- [ ] Tests pass
- [ ] Type check passes
- [ ] Manual test: <steps>
```

## Key Principles

- **One question at a time.** Don't overwhelm the user with 5 questions.
- **Propose alternatives.** Single-solution proposals hide trade-offs.
- **Self-review before user review.** Catch obvious issues first.
- **Design file is source of truth.** Implementation references it.
