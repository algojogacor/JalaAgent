# Contributing to JalaAgent

Thanks for contributing! Here's how to get started.

## Setup

```bash
git clone https://github.com/algojogacor/JalaAgent
cd JalaAgent/jalaagent
uv sync
uv run pytest  # 336 tests should pass
```

## Development workflow

1. Fork the repo, create a branch: `feat/my-feature` or `fix/my-bug`
2. Write tests for your change
3. Run `uv run pyright .` — must pass (0 errors)
4. Run `uv run ruff check .` — must pass
5. Run `uv run pytest` — must pass
6. Commit with conventional commits: `feat(scope): description`
7. Push and open a PR

## Code conventions

- Python 3.12+, `async def` everywhere, no `threading`
- Type hints on all public functions
- `pydantic v2` for data models
- `rich` for CLI output, `logging` for logs
- No `print()`, no hardcoded API keys

## Adding skills

Skills live in `packages/skill-core/src/skill_core/bundled/`. To add a new skill:

1. Create a directory with your skill name: `my-skill/SKILL.md`
2. Use the standard YAML frontmatter format (see existing skills)
3. Run `uv run jala skills list` to verify it loads

## Project structure

```
packages/     → memory-core, skill-core, agent-core
extensions/   → providers, channels, mcp, browser
cli/          → jala entry point
docs/         → Documentation
tests/        → Test suite
```

## License

By contributing, you agree your code will be licensed under Apache 2.0.
