---
name: executing-plans
description: Load an approved plan, review it critically, execute all tasks in order, and complete the branch. Simpler single-session alternative to subagent-driven-development.
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata: jalaagent: always: false; emoji: ▶️
---

# Executing Plans

## Iron Law
```
FOLLOW THE PLAN EXACTLY. NO IMPROVISATION.
STOP WHEN BLOCKED. DON'T GUESS.
TESTS MUST PASS AFTER EVERY TASK.
```

## When To Use

- Approved plan with 1-5 tasks
- Single session, no need for subagent dispatch
- Tasks don't benefit from parallel execution

## When NOT To Use

- 6+ tasks → use **subagent-driven-development**
- Tasks are independent → use **dispatching-parallel-agents**
- No approved plan → use **brainstorming** first

## Process

### Step 1: Load & Review
Read the plan file. Look for:
- Missing context that would block implementation
- Ambiguous acceptance criteria
- Inconsistent file paths
Flag anything before starting. Don't discover mid-implementation.

### Step 2: Execute Tasks (in order)
```
FOR each task in plan:
  1. Read the task specification
  2. Read any files you'll modify (understand current state)
  3. Implement the change
  4. Write/update tests (use test-driven-development)
  5. Verify: uv run pytest
  6. Verify: uv run pyright .
  7. Mark task complete, move to next
```

### Step 3: Final Verification
```bash
uv run pytest          # All tests
uv run pyright .       # No type errors
uv run ruff check .    # No lint errors
```

### Step 4: Complete
Use **finishing-a-development-branch** skill.

## Stop and Ask

- **Blocked by missing dependency?** Stop. Ask.
- **Spec contradicts existing behavior?** Stop. Ask.
- **Test reveals unexpected coupling?** Stop. Ask.
- **Estimate was way off (task taking 30+ min)?** Stop. Re-plan.
