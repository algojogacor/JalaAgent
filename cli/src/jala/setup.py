"""Interactive first-time setup wizard for JalaAgent — generates Hermes-parity config."""

import platform as _platform
from pathlib import Path

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

console = Console()
_CONFIG_PATH = Path.home() / ".jalaagent" / "config.yaml"


def run_setup() -> None:
    console.print(Panel("[bold cyan]🪼 JalaAgent Setup Wizard[/]\nHermes-parity config generator", border_style="cyan"))
    config: dict = _load_existing()

    # ── Step 1: Embedding Model ──
    console.print("[bold]Step 1: Embedding Model[/]")
    embedding_model = Prompt.ask("Embedding model", default=config.get("memory", {}).get("embedding_model", "qwen3:0.6b"))
    embedding_dim = int(Prompt.ask("Embedding dimensions", default=str(config.get("memory", {}).get("embedding_dim", 1024))))
    embedding_url = Prompt.ask("Ollama base URL", default=config.get("memory", {}).get("embedding_base_url", "http://localhost:11434"))

    # ── Step 2: LLM Provider ──
    console.print("\n[bold]Step 2: Default Provider[/]")
    provider = Prompt.ask("Default provider", choices=["deepseek", "anthropic", "openai", "openrouter", "ollama", "groq", "mistral"], default=config.get("agent", {}).get("default_provider", "deepseek"))
    default_model = Prompt.ask("Default model", default=config.get("agent", {}).get("default_model", "deepseek-chat"))

    # Collect API key and create auth.json.
    api_key = Prompt.ask(f"API key for [bold]{provider}[/] (press Enter to skip)", password=True, default="")
    if api_key.strip():
        auth_path = Path.home() / ".jalaagent" / "auth.json"
        auth_path.parent.mkdir(parents=True, exist_ok=True)
        import json as _json
        auth_data: dict = {}
        if auth_path.exists():
            try:
                auth_data = _json.loads(auth_path.read_text(encoding="utf-8")) or {}
            except Exception:
                pass
        auth_data.setdefault("providers", {})[provider] = [{"key": api_key.strip(), "priority": 1}]
        auth_path.write_text(_json.dumps(auth_data, indent=2), encoding="utf-8")
        try:
            auth_path.chmod(0o600)
            auth_path.parent.chmod(0o700)
        except OSError:
            pass  # chmod is best-effort on Windows
        console.print(f"[green]✓ API key saved to {auth_path}[/]")
    else:
        console.print(
            f"[yellow]No API key provided.[/] "
            f"Set [bold]{provider.upper()}_API_KEY[/] as an env var "
            f"or add it to [bold]~/.jalaagent/auth.json[/]:\n"
            f'[dim]{{"{provider}": [{{"key": "sk-your-key", "priority": 1}}]}}[/]'
        )

    # ── Step 3: Telegram ──
    console.print("\n[bold]Step 3: Telegram (optional)[/]")
    use_telegram = Confirm.ask("Set up Telegram bot?", default=False)
    telegram_token = Prompt.ask("TELEGRAM_BOT_TOKEN", password=True, default="") if use_telegram else ""

    # ── Step 4: Approval Mode ──
    console.print("\n[bold]Step 4: Approval Mode[/]")
    mode = Prompt.ask("Default approval mode", choices=["paranoid", "normal", "yolo", "custom"], default=config.get("approval", {}).get("mode", "normal"))
    if mode == "yolo":
        console.print("\n[bold red]⚠️  WARNING: YOLO mode bypasses ALL approval checks![/]\nActions are logged to ~/.jalaagent/logs/yolo.log\n")
        if not Confirm.ask("Are you sure?", default=False): mode = "normal"

    # ── Step 5: Recommended Integrations ──
    console.print("\n[bold]Step 5: Recommended Integrations (Optional)[/]")
    mcp_servers = config.get("mcp", {}).get("servers", [])
    if _offer_integration("BrowserOS", "Agentic browser, 53+ tools, persistent sessions", "browseros", {"name": "browseros", "type": "http", "url": "http://localhost:9876", "auto_connect": True, "description": "BrowserOS agentic browser — 53+ browser tools"}):
        mcp_servers.append({"name": "browseros", "type": "http", "url": "http://localhost:9876", "auto_connect": True})
        plat = _platform.system().lower()
        hints = {"windows": "https://files.browseros.com/download/BrowserOS_installer.exe", "darwin": "https://files.browseros.com/download/BrowserOS.dmg", "linux": "https://files.browseros.com/download/BrowserOS.AppImage"}
        console.print(f"[dim]Install: {hints.get(plat, hints['linux'])}[/]")

    # ── Build full config ──
    new_config = _build_config(provider, default_model, embedding_model, embedding_dim, embedding_url, mode, telegram_token, mcp_servers)

    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(yaml.dump(new_config, default_flow_style=False, sort_keys=False), encoding="utf-8")
    # Restrict permissions: config may contain credentials.
    try:
        _CONFIG_PATH.chmod(0o600)
        _CONFIG_PATH.parent.chmod(0o700)
    except OSError:
        pass  # Windows doesn't support chmod well, but POSIX does.
    console.print(f"\n[green]✅ Config written to {_CONFIG_PATH}[/]")
    console.print("[bold]Next:[/] Set API keys in auth.json, then run [bold]jala[/] to start!")


def _build_config(provider: str, default_model: str, embedding_model: str, embedding_dim: int, embedding_url: str, mode: str, telegram_token: str, mcp_servers: list) -> dict:
    return {
        # ═══ BLOCK 1: Provider System ═══
        "model": {"default": default_model, "provider": provider, "context_length": 200000},
        "providers": {
            "deepseek": {"base_url": "https://api.deepseek.com/v1", "models": [{"name": "deepseek-chat", "default": True}, {"name": "deepseek-reasoner"}]},
            "openrouter": {"base_url": "https://openrouter.ai/api/v1", "models": [{"name": "anthropic/claude-sonnet-4", "default": True}, {"name": "openai/gpt-4o"}, {"name": "google/gemini-2.5-flash"}], "extra_headers": {"HTTP-Referer": "https://jalaagent.dev", "X-Title": "JalaAgent"}},
            "groq": {"base_url": "https://api.groq.com/openai/v1", "models": [{"name": "llama-4-scout-17b-16e-instruct", "default": True}]},
            "mistral": {"base_url": "https://api.mistral.ai/v1", "models": [{"name": "mistral-large-latest", "default": True}, {"name": "codestral-latest"}]},
            "together": {"base_url": "https://api.together.xyz/v1", "models": [{"name": "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8", "default": True}]},
            "perplexity": {"base_url": "https://api.perplexity.ai", "models": [{"name": "sonar-pro", "default": True}]},
            "xai": {"base_url": "https://api.x.ai/v1", "models": [{"name": "grok-2", "default": True}]},
            "qwen": {"base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1", "models": [{"name": "qwen3-max", "default": True}]},
            "cohere": {"base_url": "https://api.cohere.ai/v1", "models": [{"name": "command-a", "default": True}]},
            "fireworks": {"base_url": "https://api.fireworks.ai/inference/v1", "models": [{"name": "accounts/fireworks/models/llama-v3p1-70b-instruct", "default": True}]},
            "cerebras": {"base_url": "https://api.cerebras.ai/v1", "models": [{"name": "llama-3.3-70b", "default": True}]},
            "sambanova": {"base_url": "https://api.sambanova.ai/v1", "models": [{"name": "Meta-Llama-3.1-70B", "default": True}]},
            "nvidia": {"base_url": "https://integrate.api.nvidia.com/v1", "models": [{"name": "meta/llama-4-maverick", "default": True}]},
            "openai": {"base_url": "https://api.openai.com/v1", "models": [{"name": "gpt-4o", "default": True}]},
            "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta", "models": [{"name": "gemini-2.5-flash", "default": True}]},
            "ollama": {"base_url": "http://localhost:11434/v1", "models": [{"name": "qwen3:0.6b", "default": True}]},
        },
        "fallback_providers": ["deepseek", "openrouter", "groq", "mistral", "ollama"],
        "credential_pool": {"strategy": "random", "health_check_interval": 3600, "max_retries": 3, "jitter": True},
        "auxiliary": {"provider": "deepseek", "model": "deepseek-chat", "description": "Cheaper model for dreaming, self-improvement, background tasks"},

        # ═══ BLOCK 2: Agent Runtime ═══
        "agent": {"name": "JalaAgent", "max_iterations": 100, "model": default_model, "provider": provider, "api_max_retries": 3, "tool_use_enforcement": "auto", "task_completion_guidance": True, "image_input_mode": "auto"},
        "delegation": {"max_sub_agent_depth": 1, "max_concurrent_sub_agents": 5, "sub_agent_iteration_budget": 50},
        "compression": {"enabled": True, "threshold": 0.8, "keep_recent_tokens": 20000},
        "prompt_caching": {"enabled": True, "provider": "anthropic"},
        "checkpoints": {"enabled": True, "max_checkpoints": 10, "directory": "~/.jalaagent/checkpoints"},
        "toolsets": ["jala-core"],

        # ═══ BLOCK 3: Tools & Execution ═══
        "tool_loop_guardrails": {"loop_detection_window": 10, "loop_warning_threshold": 3, "loop_hard_stop_threshold": 5},
        "tool_output": {"max_result_chars": 50000, "overflow_dir": "~/.jalaagent/tmp"},
        "code_execution": {"block_dangerous": True, "default_timeout": 120, "max_output_chars": 100000},
        "approval": {"mode": mode, "rules": {"file_read": "auto", "file_write": "auto", "file_delete": "ask", "shell_exec": "ask", "network_get": "auto", "network_post": "ask", "messaging_send": "ask", "memory_write": "auto"}},
        "command_allowlist": {},

        # ═══ BLOCK 4: Channels ═══
        "channels": {
            "cli": {"enabled": True, "footer": True, "spinner": True, "streaming_refresh": 10},
            "telegram": {"token": telegram_token or "${TELEGRAM_BOT_TOKEN}", "allowed_users": [], "polling_interval": 1, "edit_interval": 0.5},
            "slack": {"enabled": False, "comment": "v2 — not yet implemented"},
            "discord": {"enabled": False, "comment": "v2 — not yet implemented"},
            "whatsapp": {"enabled": False, "comment": "v2 — not yet implemented"},
        },

        # ═══ BLOCK 5: Memory & Skills ═══
        "memory": {"embedding_model": embedding_model, "embedding_dim": embedding_dim, "embedding_base_url": embedding_url, "dreaming": {"enabled": True, "schedule": "0 3 * * *"}, "max_retrieval_results": 10, "retrieval_threshold": 0.7, "memory_dir": "~/.jalaagent/memories", "db_path": "~/.jalaagent/db/memory.db"},
        "skills": {"bundled_dir": "auto", "user_dir": "~/.jalaagent/skills", "max_skills_in_prompt": 150, "max_chars_per_skill": 40000},
        "curator": {"enabled": True, "stale_days": 30, "auto_archive": False},
        "goals": {"max_active": 1, "auto_clear_on_new": True},

        # ═══ BLOCK 6: Hooks & Automation ═══
        "hooks": {},
        "cron": {"enabled": False, "tasks": {}},
        "blueprints": {"directory": "~/.jalaagent/blueprints"},
        "kanban": {"enabled": False, "comment": "Kanban orchestrator available via /kanban command and skill"},

        # ═══ BLOCK 7: UX & Display ═══
        "display": {"footer": True, "spinner": True, "theme": "auto", "timestamps": False},
        "streaming": {"chunk_size": None, "max_delay": 0.1, "refresh_rate": 10},
        "personalities": {"directory": "~/.jalaagent/personalities", "bundled": ["default", "concise", "researcher"]},
        "onboarding": {"completed": True, "version": "2026.6.18"},

        # ═══ BLOCK 8: Production ═══
        "network": {"proxy": "", "timeout": 120, "max_retries": 3, "verify_ssl": True},
        "logging": {"level": "INFO", "file": "~/.jalaagent/logs/jala.log", "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"},
        "security": {"prompt_injection_detection": True, "scan_skills_on_install": True},
        "privacy": {"telemetry": False, "data_dir": "~/.jalaagent", "no_phone_home": True},
        "sessions": {"storage": "jsonl", "directory": "~/.jalaagent/memories/sessions", "cleanup_days": 90},
        "mcp": {"idle_timeout": 300, "servers": mcp_servers},
    }


def _offer_integration(name: str, desc: str, key: str, mcp_config: dict) -> bool:
    console.print(f"\n[bold]{name}[/]: {desc}")
    if Confirm.ask(f"Configure {name}? [y/N]", default=False):
        console.print(f"[green]✓ {name} added to MCP config.[/]")
        return True
    console.print(f"[dim]Skipped. Add later: jala mcp add {key}[/]")
    return False


def _load_existing() -> dict:
    if _CONFIG_PATH.exists():
        try:
            return yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}
        except Exception:
            pass
    return {}
