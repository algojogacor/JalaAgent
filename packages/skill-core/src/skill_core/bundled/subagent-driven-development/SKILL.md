---
name: subagent-driven-development
description: Execute implementation plans by dispatching one fresh subagent per task with two-stage review (spec compliance → code quality). Never skip review gates.
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 🤖
    requires:
      bins: [git]
      env: []
---

# Subagent-Driven Development

Execute an implementation plan by dispatching one fresh subagent per task. Two mandatory review stages per task. Continuous execution without pausing.

## Iron Law

```
EVERY TASK GETS TWO REVIEWS. SPEC COMPLIANCE FIRST. CODE QUALITY SECOND.
NO SKIPPING. NO EXCEPTIONS. FRESH SUBAGENT PER TASK.
```

## When To Use

- An approved plan exists with 3+ tasks
- Tasks are independent (no shared mutable state)
- You have `delegate_task` tool available

## When NOT To Use

- Single trivial task → use executing-plans skill
- Tasks have complex inter-dependencies → use kanban-orchestrator skill
- No approved plan → use brainstorming + writing-plans first

## Process

### Step 1: Load the Plan

Read the plan file. Verify it's approved. Extract the task list.

### Step 2: For Each Task (in order)

```
FOR each task in plan:
  1. Dispatch implementer subagent with full task text
  2. Review 1: SPEC COMPLIANCE — does output match the spec exactly?
  3. Review 2: CODE QUALITY — are tests passing, types correct, lints clean?
  4. If concerns exist → loop back to implementer with feedback
  5. If approved → mark task DONE, proceed to next
```

### Step 3: Complete

Use finishing-a-development-branch skill to present merge options.

## Review Stages (Mandatory)

### Review 1: Spec Compliance
- Does every acceptance criterion have a passing test?
- Are all required files created/modified?
- Does the behavior match the spec description?

### Review 2: Code Quality
- Do all tests pass? (`uv run pytest`)
- Does pyright pass? (`uv run pyright`)
- Does ruff pass? (`uv run ruff check .`)
- Is the code consistent with surrounding patterns?

## Model Selection

- **Implementer**: cheapest model that can follow instructions
- **Reviewer**: best available model (catches what implementer misses)

## Red Flags

| Thought | Reality |
|---------|---------|
| "This task is simple, skip review" | Simple tasks have simple bugs. Review is faster than debugging. |
| "I'll review both stages at once" | Spec bugs and style bugs need different attention. Separate them. |
| "Same model can review itself" | Fresh context finds what familiar context misses. |

## Integration

- Load plan via **writing-plans** skill
- Test tasks via **test-driven-development** skill
- Review code via **requesting-code-review** skill
- Finish via **finishing-a-development-branch** skill
