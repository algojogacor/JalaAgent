# Contributing Guide

## Getting Started
```bash
git clone https://github.com/algojogacor/JalaAgent
cd JalaAgent && uv sync
```

## Development
```bash
uv run pytest           # Run tests
uv run pyright .        # Type check
uv run ruff check .     # Lint
uv run jala             # Test interactively
```

## Adding a Skill
1. Create `packages/skill-core/src/skill_core/bundled/<name>/SKILL.md`
2. Follow the YAML frontmatter format:
```yaml
---
name: my-skill
description: What it does
version: 1.0.0
author: YourName
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 🔧
---
```
3. Run `uv run jala skills list` to verify it loads

## Adding a Provider
1. Add provider entry to `~/.jalaagent/config.yaml` under `providers:`
2. The universal provider auto-discovers new entries

## Pull Request Checklist
- [ ] Tests pass: `uv run pytest`
- [ ] Types pass: `uv run pyright .`
- [ ] Lint pass: `uv run ruff check .`
- [ ] No hardcoded keys or paths
- [ ] No `print()`, use `logging` or `rich`
- [ ] No `threading`, use `asyncio`
