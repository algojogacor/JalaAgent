---
name: git-workflow
description: Complete git workflow — branching, committing, PR management, worktree isolation, conflict resolution. Safe patterns for agent-driven version control.
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata: jalaagent: always: false; emoji: 🌿
---

# Git Workflow

## Iron Law
```
NEVER FORCE PUSH TO MAIN. NEVER COMMIT SECRETS. NEVER LOSE WORK.
ALWAYS PULL BEFORE PUSH. ALWAYS VERIFY TESTS BEFORE COMMITTING.
```

## Branch Strategy

```
main          ← production-ready
├── develop   ← integration branch
├── feat/*    ← feature branches
├── fix/*     ← bug fix branches
└── jala/*    ← agent-created worktrees
```

## Worktree Isolation

When the agent writes code, use a worktree:
```bash
git worktree add -b jala/task-name .claude/worktrees/task-name
cd .claude/worktrees/task-name
# ... do work ...
git worktree remove .claude/worktrees/task-name --force  # cleanup
```

## Commit Discipline

### Good Commit Messages
```
feat(memory): add knowledge graph entity extraction
fix(registry): handle sync handlers in tool execution
test(harness): add sandboxed shell path scoping tests
```

### Commit Format
```
<type>(<scope>): <description>

<optional body>

Co-Authored-By: JalaAgent <agent@jalaagent.dev>
```

Types: `feat`, `fix`, `test`, `refactor`, `docs`, `chore`, `security`

## PR Workflow

### Creating a PR
```bash
git checkout -b feat/my-feature
git add -A
git commit -m "feat: description"
git push -u origin feat/my-feature
# Create PR via gh CLI
gh pr create --title "feat: description" --body "..." --base main
```

### PR Body Template
```markdown
## What
<One-line description>

## Verification
- [ ] Tests pass: `uv run pytest`
- [ ] Types pass: `uv run pyright .`
- [ ] Lint pass: `uv run ruff check .`
- [ ] Manual test: <steps>

🤖 Generated with [JalaAgent](https://github.com/algojogacor/JalaAgent)
```

## Conflict Resolution

1. `git fetch origin`
2. `git merge origin/main`
3. If conflicts: resolve manually, `git add`, `git merge --continue`
4. Re-run tests after merge
5. Push resolved branch

## Safety Checks Before Push

```bash
uv run pytest                    # All tests pass
uv run pyright .                 # No type errors
uv run ruff check .              # No lint errors
git diff origin/main..HEAD       # Review what you're pushing
git log origin/main..HEAD --oneline  # Review commit history
```
