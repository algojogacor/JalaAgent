---
name: git-advanced
description: Interactive rebase, bisect, worktrees, reflog, cherry-pick, submodules. Advanced Git patterns for complex workflows.
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 🌿
    requires: {bins: [git], env: []}
---

# Advanced Git

## Overview
Beyond basic add/commit/push. Handle complex history, recover lost work, manage multi-branch workflows.

## Key Commands
- `git reflog` — Recover deleted commits/branches (30-day safety net)
- `git bisect` — Binary search for bug-introducing commit
- `git rebase -i` — Squash, reorder, edit commit history
- `git cherry-pick` — Apply specific commits to another branch
- `git worktree` — Multiple working trees from one repo

## Recovering Lost Work
```bash
git reflog                          # Find lost commit hash
git checkout -b recovered <hash>    # Restore it
```

## Interactive Rebase
```bash
git rebase -i HEAD~5   # Last 5 commits
# pick = keep, squash = merge, reword = rename, drop = remove
```

## Anti-Patterns
- Never rebase shared branches (only your own)
- Never force push to main/master
- Never amend pushed commits without communicating
