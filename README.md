# JalaAgent

Open-source, self-improving AI agent with a hybrid memory system.

**Status:** v0.1 — pre-development scaffold.

## Architecture

```
jalaagent/
├── packages/
│   ├── agent-core/      # Core agent loop, provider abstraction, tool registry
│   ├── memory-core/     # Hybrid memory: file + sqlite-vec + dreaming
│   └── skill-core/      # Skill system: SKILL.md, workshop, hub
├── extensions/
│   ├── channels/        # Telegram, CLI
│   └── providers/       # Anthropic, Ollama, OpenAI, OpenRouter
├── cli/                 # jala entry point
└── tests/               # Integration tests
```

## Quick Start

```bash
uv sync
python -m jala setup
python -m jala
```

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Ollama (for local embedding model)

## License

Apache 2.0
