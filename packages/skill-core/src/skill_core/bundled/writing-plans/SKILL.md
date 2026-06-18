---
name: writing-plans
description: Convert approved designs into bite-sized implementation tasks. 2-5 min per task, exact file paths, complete code examples, verification steps. UI Shell Trap awareness.
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 📋
---

# Writing Plans

## Iron Law
```
EVERY TASK IS 2-5 MINUTES. EXACT FILE PATHS. COMPLETE CODE EXAMPLES.
IF A TASK IS BIGGER, SPLIT IT. IF YOU CAN'T SPLIT IT, THE DESIGN IS WRONG.
```

## Core Behavior

For this turn, you are **planning only**. No code. No edits. No mutating commands. Save the plan file. Present it for approval.

## Task Template

```markdown
### Task N: <One-line description>
- **Files to modify:** `exact/path.py:line` — <what to change>
- **Files to create:** `exact/path.py` — <what it will contain>
- **Acceptance criteria:**
  - [ ] `test_x` passes
  - [ ] Behavior: <exactly what should happen>
- **Verification:** `uv run pytest tests/test_x.py -v`
- **Depends on:** Task N-1 (or "none")
```

## UI Shell Trap

When building UI, the shell (buttons, forms, toggles, navigation) must work end-to-end. Non-functional shells create the illusion of progress:
- **Buttons must submit real data**, not `console.log("clicked")`
- **Forms must validate and persist**, not just render
- **Toggles must change state** that affects other components
- **Navigation must route to pages that exist and load data**

Each UI task must say: "When user clicks X, Y happens and Z is visible."

## Bite-Sized Split Pattern

`<Bad>` "Implement the login page" — too big, 30+ minutes
`<Good>`
- Task 1: Create `LoginForm` component with email/password fields
- Task 2: Add form validation (email format, password min length)
- Task 3: Wire form submit to `POST /api/auth/login`
- Task 4: Handle success (redirect) and error (show message)
- Task 5: Write tests for all states (empty, invalid, error, success)

## Plan Structure

```markdown
# Plan: <Title>
**Based on design:** docs/plans/YYYY-MM-DD-<topic>-design.md
**Status:** Pending Approval

## Task List
### Phase 1: Foundation
- [ ] Task 1: ...
- [ ] Task 2: ...

### Phase 2: Core Logic
...

### Phase 3: Integration & Tests
...
```
