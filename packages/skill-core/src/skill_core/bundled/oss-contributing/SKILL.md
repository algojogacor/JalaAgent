---
name: oss-contributing
description: End-to-end open source contribution workflow — find issues, fork, fix, PR. 100+ merged PRs of battle-tested patterns.
version: 1.0.0
author: JalaAgent (ported from Hermes)
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 🐙
    provenance:
      source: hermes-agent
      original: open-source-contributing
      category: oss
      ported: 2026-06-18
---

# Open Source Contributing

## Overview
Find, fork, fix, and submit PRs to open source projects. Workflow tested with 100+ merged PRs.

## Process
1. **Find**: Search GitHub for "good first issue", exclude repos with 10k+ stars (meta-repo trap)
2. **Fork**: Use `gh repo fork` with `--clone=false` to avoid unnecessary clones
3. **Fix**: Use sparse clone for large repos, write tests, follow project conventions
4. **PR**: Follow project's PR template, reference the issue, keep changes focused

## PR Body Standard
```markdown
## What
Brief description of the change

## Why
Link to issue and explain the fix

## Verification
- [ ] Tests pass
- [ ] Follows project conventions
- [ ] No unrelated changes
```

## Common Pitfalls
- **Meta-repo trap**: Repos with 10k+ stars have 500+ open issues — look for "good first issue" labels
- **Secondary rate limit**: GitHub rate-limits after 100 requests/hour unauthenticated
- **Branch collision**: Always use unique branch names: `fix/issue-123-description`
- **MSYS2 quirks**: On Windows, use Git Bash not MSYS2 for git operations

## Anti-Patterns
- Don't submit PRs without reading CONTRIBUTING.md
- Don't change formatting in the same PR as a bug fix
- Don't argue with maintainers about style preferences
