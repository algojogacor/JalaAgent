---
name: technical-writing
description: README, CHANGELOG, ADR, API docs, documentation structure. Clear, concise, audience-aware technical content.
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 📖
---

# Technical Writing

## Overview
Write clear, structured technical documentation. Every doc has an audience, a purpose, and a structure.

## Document Types
- **README**: What, why, quickstart, contributing, license
- **CHANGELOG**: Per-version changes, grouped by type (Added, Changed, Fixed)
- **ADR**: Architecture Decision Record — context, decision, consequences
- **API docs**: Endpoint, method, params, response, example

## README Structure
```markdown
# Project Name
> One-line description
## Quickstart (copy-paste to get running)
## Usage (common patterns)
## API / Configuration
## Contributing
## License
```

## Writing Rules
- Active voice: "Click the button" not "The button should be clicked"
- One idea per paragraph. Short paragraphs.
- Code blocks must be copy-pasteable and work
- Every command shown must have been tested

## Anti-Patterns
- Don't start with installation if quickstart exists
- Don't explain what the reader already knows
- Don't use "simply" or "just" (nothing is simple to a new user)
