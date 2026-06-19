# 🪼 JalaAgent

**Open-source self-improving AI agent with hybrid memory — better than Hermes, leaner than OpenClaw.**

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-336%20passing-brightgreen.svg)](tests/)
[![Pyright](https://img.shields.io/badge/type%20check-pyright%20clean-success.svg)](pyrightconfig.json)
[![Skills](https://img.shields.io/badge/skills-67-blueviolet.svg)](packages/skill-core/src/skill_core/bundled/)
[![Providers](https://img.shields.io/badge/providers-16+-orange.svg)](extensions/providers/universal/)

---

## What is JalaAgent?

JalaAgent is a persistent personal AI agent that lives on your machine, remembers everything across sessions, improves its own skills over time, and reaches you via CLI or Telegram. Not a chatbot wrapper. Not a coding copilot. **An agent that remembers, learns, and acts.**

**82 source files · ~14,000 lines Python · 336 tests · 67 skills · 46 commands · 16+ providers**

## Why JalaAgent?

- **Clean architecture**: 82 Python files vs typical agent monoliths
- **Python-native**: No TypeScript, no Node.js required
- **Built-in dreaming**: Automatic memory consolidation via cron
- **4-layer hybrid memory**: File + vector + knowledge graph + dreaming pipeline
- **Skill system**: 67 bundled skills, extensible via SKILL.md
- **Credential pool**: Multi-key rotation with fallback chain

## Quick Start

```bash
git clone https://github.com/algojogacor/JalaAgent
cd JalaAgent && uv sync
uv run jala setup   # Interactive wizard
uv run jala         # Start chatting
uv run jala gateway # CLI + Telegram
uv run jala serve   # API server (use with Claude Code)
```

## Documentation

| Doc | Description |
|-----|-------------|
| [Quickstart](docs/quickstart.md) | 5-minute setup |
| [User Guide](docs/user-guide.md) | Manual book |
| [Architecture](docs/architecture.md) | Full architecture |
| [Memory System](docs/memory.md) | 4-layer hybrid memory |
| [Skills Catalog](docs/skills.md) | All 67 skills |
| [Commands Reference](docs/commands.md) | 46 slash commands |
| [Providers](docs/providers.md) | 16+ provider setup |
| [Configuration](docs/configuration.md) | config.yaml reference |
| [API Reference](docs/api-reference.md) | Python API |
| [Contributing](docs/contributing-guide.md) | How to contribute |
| [Roadmap](docs/roadmap.md) | What's next |

## License

Apache 2.0 — see [LICENSE](LICENSE). Same as Hermes-Agent and OpenClaw. Includes explicit patent grants for AI/ML.
