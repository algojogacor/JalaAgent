---
name: code-review-skill
description: Structured code review — correctness, security, performance, simplicity. Severity levels with actionable feedback.
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 👀
---

# Code Review

## Overview
Review code changes systematically. Find bugs, security issues, and simplification opportunities.

## Review Dimensions
1. **Correctness**: Does it do what it says? Edge cases handled?
2. **Security**: Injection, auth, data exposure?
3. **Performance**: N+1 queries, unnecessary allocations, blocking I/O?
4. **Simplicity**: Could this be simpler? Is there duplicated code?
5. **Style**: Consistent with surrounding code? Follows conventions?

## Severity Levels
- **Critical**: Security vulnerability, data loss, broken functionality
- **High**: Bug in common path, performance regression
- **Medium**: Code smell, missing test coverage, duplicated logic
- **Low**: Style nit, naming suggestion, optional improvement

## Review Output Format
```markdown
### Finding: [Severity] Brief title
**File**: path/to/file.py:42
**Issue**: What's wrong
**Fix**: Specific change to make
```

## Anti-Patterns
- Don't review style without reviewing logic
- Don't say "this is wrong" without explaining what's right
- Don't review more than 400 lines at once (diminishing returns)
