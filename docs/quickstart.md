# Quickstart — 5 Minutes to JalaAgent

## Prerequisites
- Python 3.12+
- `uv` package manager (`pip install uv`)

## Install

```bash
git clone https://github.com/algojogacor/JalaAgent
cd JalaAgent/jalaagent
uv sync
```

## Setup

```bash
uv run jala setup
```

The interactive wizard will guide you through:
1. Choose embedding model (default: qwen3:0.6b via Ollama)
2. Choose LLM provider (DeepSeek, Anthropic, OpenAI, etc.)
3. Optional Telegram bot
4. Approval mode (default: NORMAL)

## Start Chatting

```bash
uv run jala
```

Type a message, press Ctrl+D to submit, see streaming response.

## Gateway (CLI + Telegram)

```bash
# Set your Telegram token first
export TELEGRAM_BOT_TOKEN="your-token"

uv run jala gateway
```

## API Server (use with Claude Code)

```bash
uv run jala serve --port 8787
# Then: ANTHROPIC_BASE_URL=http://localhost:8787 claude
```

## Provider Setup

Add API keys to `~/.jalaagent/auth.json`:

```json
{
  "deepseek": [{"key": "sk-your-key", "priority": 1}],
  "openrouter": [{"key": "sk-or-xxx", "priority": 1}]
}
```

Or use environment variables: `DEEPSEEK_API_KEY`, `OPENROUTER_API_KEY`, etc.

## Slash Commands

```
/mode normal       # Set approval mode
/model deepseek    # Switch provider
/yolo on            # Enable autonomous mode
/help              # Show all commands
```

## Next Steps
- Read the [User Guide](user-guide.md) for full usage
- Browse [Skills Catalog](skills.md) to see 77 bundled skills
- Check [Commands Reference](commands.md) for 46 slash commands
- See [Configuration](configuration.md) for all settings
