# JalaAgent User Guide — Manual Book

## Table of Contents
1. [Getting Started](#getting-started)
2. [Chatting with JalaAgent](#chatting)
3. [Slash Commands](#commands)
4. [Skills](#skills)
5. [Memory System](#memory)
6. [Gateway Mode](#gateway)
7. [API Server](#serve)
8. [Approval Modes](#approval)
9. [Configuration](#config)
10. [Troubleshooting](#troubleshoot)

---

## Getting Started

### Installation
```bash
git clone https://github.com/algojogacor/JalaAgent
cd JalaAgent && uv sync
uv run jala setup
```

### First Chat
```bash
uv run jala
You: Hello, what can you help with?
# JalaAgent responds with streaming text
```

### Provider Setup
JalaAgent uses `~/.jalaagent/auth.json` for API keys. Add your keys:

```json
{"deepseek": [{"key": "sk-xxx", "priority": 1}]}
```

Or set environment variables: `DEEPSEEK_API_KEY`, `ANTHROPIC_API_KEY`, etc.

---

## Chatting with JalaAgent

### Interactive Mode
```bash
uv run jala                 # CLI chat
uv run jala --model gpt-4o  # Specific model
uv run jala --plan          # Plan mode (no code until approved)
uv run jala -p "Write a script"  # Single prompt
```

### Streaming Output
JalaAgent streams responses token-by-token using Rich Live panels. You see the response build in real-time. Tool calls appear as status lines.

### Slash Commands
Type `/` during a chat session to access 46 commands. See [Commands Reference](commands.md) for the full list.

---

## Skills

JalaAgent ships with 67 bundled skills across 13 categories:

| Category | Count | Examples |
|----------|:---:|----------|
| Software Development | 17 | TDD, debugging, code review, SDD, planning |
| Creative | 13 | Design, pixel art, creative writing, presentations |
| DevOps | 8 | Docker, deployment, secrets, environments |
| Research | 4 | Web research, API exploration, papers |
| JalaAgent Exclusive | 8 | Brain management, YOLO mode, self-upgrade |

Skills auto-load into every session. Use `/skills` to list them. Skills in `bundled/design-pack/` can be removed with `rm -rf`.

---

## Memory System

JalaAgent remembers across sessions with 4 memory layers:

1. **File Layer**: `~/.jalaagent/memories/MEMORY.md` — human-readable facts
2. **Vector Layer**: SQLite + sqlite-vec — semantic search across episodes
3. **Dreaming Pipeline**: Auto-consolidates facts daily at 3 AM
4. **Knowledge Graph**: Entities and relations extracted from your content

Inspect memory: `jala memory inspect`
Search memory: `jala memory search <query>`

---

## Gateway Mode

Run all channels at once:

```bash
jala gateway
```

This starts CLI + Telegram in one asyncio event loop. The gateway banner shows active channels, model, skills count, and memory status.

---

## API Server

Expose JalaAgent as an Anthropic-compatible API:

```bash
jala serve --port 8787
# Then use with Claude Code:
ANTHROPIC_BASE_URL=http://localhost:8787 claude
```

Endpoints: `POST /v1/messages`, `GET /v1/models`, `POST /v1/messages/count_tokens`

---

## Approval Modes

| Mode | Behavior |
|------|----------|
| NORMAL | Ask only for destructive actions |
| PARANOID | Ask for everything |
| YOLO | Bypass all approvals |
| CUSTOM | Per-category rules in config.yaml |

Switch modes: `/mode yolo` or `jala setup` → Step 4.

---

## Configuration

Full Hermes-parity `~/.jalaagent/config.yaml` with 8 blocks:

- **Provider System**: 16 providers, fallback chains, credential strategies, auxiliary LLM
- **Agent Runtime**: Max iterations, retries, compression, caching, delegation
- **Tools & Execution**: Loop guardrails, sandbox, overflow, approvals
- **Channels**: CLI, Telegram, Slack/Discord/WhatsApp stubs
- **Memory & Skills**: Embedding, dreaming, retrieval, curator, goals
- **Hooks & Automation**: Hooks, cron, blueprints, kanban
- **UX & Display**: Footer, spinner, theme, streaming, personalities
- **Production**: Network proxy, logging, security, privacy

See [Configuration](configuration.md) for complete reference.

View your config: `jala config-show`
Get a specific value: `jala config-get model.provider`

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| No provider available | Set API key in auth.json or env var |
| Ollama not found | Install Ollama or use cloud provider |
| Skills don't load | Check YAML frontmatter syntax |
| Memory database locked | Kill stale process, remove WAL files |
| Telegram bot unreachable | Verify token, check internet |
