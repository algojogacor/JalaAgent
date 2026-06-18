---
name: finishing-a-development-branch
description: End-of-workflow cleanup — verify tests pass, detect environment, present 4 merge options, handle worktree cleanup. Tests must pass before options are presented.
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 🏁
---

# Finishing A Development Branch

## Iron Law
```
TESTS MUST PASS BEFORE OPTIONS ARE OFFERED.
NO BROKEN CODE LEAVES THE BRANCH.
```

## Process

### Step 1: Verify Tests
```bash
uv run pytest  # ALL tests must pass
uv run pyright .  # NO type errors
uv run ruff check .  # NO lint errors
```

### Step 2: Detect Environment
```bash
git worktree list  # Are we in a worktree?
git branch --show-current  # Named branch or detached HEAD?
git status --porcelain  # Any uncommitted changes?
```

### Step 3: Determine Base Branch
```bash
git merge-base origin/main HEAD  # Where we branched from
```

### Step 4: Present Options

**If on a named branch in a normal repo:**
1. 🔀 Merge locally into main
2. 📤 Push branch and create PR
3. 📦 Keep branch as-is (return later)
4. 🗑️ Discard branch (requires typing "discard" to confirm)

**If in a git worktree:**
1. 📤 Push branch and create PR
2. 📦 Keep worktree for later
3. 🗑️ Remove worktree (requires typing "discard")

### Step 5: Execute Choice
- Merge: `git checkout main && git merge <branch>`
- Push: `git push -u origin <branch>`
- Discard: `git worktree remove <path> --force && git branch -D <branch>`

### Step 6: Cleanup
```bash
cd <repo-root>  # Important: leave worktree before removing
git worktree remove <path> --force  # Only if discard chosen
```

## Red Flags
- Discarding without typing "discard" — too easy to lose work
- Trying to remove a worktree while inside it — will fail
- Merging when tests don't pass — broken code in main
