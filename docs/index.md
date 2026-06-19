---
layout: home

hero:
  name: "JalaAgent"
  text: "Open-source self-improving AI agent"
  tagline: Persistent. Self-improving. Enterprise-grade. Lives on your infrastructure.
  actions:
    - theme: brand
      text: Quickstart
      link: /guide/quickstart
    - theme: alt
      text: View on GitHub
      link: https://github.com/algojogacor/JalaAgent

features:
  - icon: 🧠
    title: 4-Layer Hybrid Memory
    details: File + SQLite-vec + Knowledge Graph + Dreaming Pipeline. Remembers everything across sessions.
  - icon: 🔌
    title: 16+ Providers
    details: Anthropic, OpenAI, Ollama, DeepSeek, Groq, Mistral, Gemini, OpenRouter, and any OpenAI-compatible API.
  - icon: 🛠️
    title: 67 Bundled Skills
    details: Extensible skill system with SKILL.md format. AI-assisted workshop pipeline for creating new skills.
  - icon: 📡
    title: Multi-Channel
    details: CLI + Telegram + WhatsApp. Unified slash commands across all channels.
  - icon: 🔒
    title: Enterprise-Grade
    details: Credential pool with rotation, fail-closed approval, sandboxed shell, worktree isolation.
  - icon: 🪄
    title: Self-Improving
    details: Dreaming pipeline consolidates memories. Skill workshop proposes improvements. Automatic maintenance.

---

## Quick Start

```bash
# Install uv (if not already)
pip install uv

# Clone and enter repo
git clone https://github.com/algojogacor/JalaAgent.git
cd JalaAgent

# Sync dependencies
uv sync --all-packages

# Run setup wizard
uv run jala setup

# Start the gateway (CLI + Telegram + WhatsApp)
jala gateway
```

## Why JalaAgent?

JalaAgent combines the best of [Hermes-Agent](https://github.com/NapthaAI/hermes-agent) (provider/model flexibility, interactive model picker, credential pools) and [OpenClaw](https://github.com/openclaw/openclaw) (file-based memory, dreaming pipeline, skill system) with enterprise-grade engineering.

- **Clean architecture**: 82 Python files — not a monolith. Packages for agent-core, memory-core, skill-core
- **Python-native**: No TypeScript, no Node.js required (WhatsApp channel uses optional Baileys bridge)
- **Transparent by default**: Everything the agent knows is readable as plain files — no opaque databases
- **Production-first**: Proper error handling with classified retry strategies, comprehensive tests, full type hints
