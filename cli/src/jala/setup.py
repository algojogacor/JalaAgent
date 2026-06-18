"""Interactive first-time setup wizard for JalaAgent."""

from pathlib import Path

import yaml
from rich.console import Console
from rich.prompt import Confirm, Prompt

console = Console()
_CONFIG_PATH = Path.home() / ".jalaagent" / "config.yaml"


def run_setup() -> None:
    """Run the interactive setup wizard.

    Steps:
    1. Detect / configure Ollama embedding model.
    2. Choose provider and enter API key.
    3. Optional Telegram bot token.
    4. Select default approval mode.
    5. Write config.yaml.
    """
    console.print("[bold cyan]🪼 JalaAgent Setup Wizard[/]\n")

    config: dict = _load_existing()

    # --- Step 1: Ollama ---
    console.print("[bold]Step 1: Embedding Model[/]")
    embedding_model = Prompt.ask(
        "Embedding model", default=config.get("memory", {}).get("embedding_model", "qwen3:0.6b")
    )
    embedding_dim = int(
        Prompt.ask("Embedding dimensions", default=str(
            config.get("memory", {}).get("embedding_dim", 1024)
        ))
    )
    embedding_url = Prompt.ask(
        "Ollama base URL",
        default=config.get("memory", {}).get("embedding_base_url", "http://localhost:11434"),
    )

    # --- Step 2: Provider ---
    console.print("\n[bold]Step 2: LLM Provider[/]")
    provider = Prompt.ask(
        "Default provider",
        choices=["anthropic", "openai", "ollama", "openrouter"],
        default=config.get("provider", {}).get("default", "anthropic"),
    )

    api_key = ""
    if provider in ("anthropic", "openai", "openrouter"):
        api_key = Prompt.ask(
            f"{provider.upper()}_API_KEY",
            password=True,
            default="",
        )

    # --- Step 3: Telegram ---
    console.print("\n[bold]Step 3: Telegram (optional)[/]")
    use_telegram = Confirm.ask("Set up Telegram bot?", default=False)
    telegram_token = ""
    if use_telegram:
        telegram_token = Prompt.ask("TELEGRAM_BOT_TOKEN", password=True, default="")

    # --- Step 4: Approval mode ---
    console.print("\n[bold]Step 4: Approval Mode[/]")
    mode = Prompt.ask(
        "Default approval mode",
        choices=["paranoid", "normal", "yolo", "custom"],
        default=config.get("approval", {}).get("mode", "normal"),
    )

    if mode == "yolo":
        console.print(
            "\n[bold red]⚠️  WARNING: YOLO mode bypasses ALL approval checks![/]\n"
            "All tool executions will proceed without asking.\n"
            "Actions are logged to ~/.jalaagent/logs/yolo.log\n"
        )
        if not Confirm.ask("Are you sure you want YOLO mode?", default=False):
            mode = "normal"
            console.print("[green]Reverting to NORMAL mode.[/]")

    # --- Step 5: Recommended Integrations ---
    console.print("\n[bold]Step 5: Recommended Integrations (Optional)[/]")
    console.print(
        "[dim]These tools extend JalaAgent's capabilities. "
        "They run separately and connect via MCP.[/]\n"
    )
    mcp_servers: list[dict[str, str]] = config.get("mcp", {}).get("servers", [])

    integrations = [
        {
            "name": "BrowserOS",
            "key": "browseros",
            "description": "Agentic browser with session persistence, 53+ browser "
                           "tools, and login state saved across sessions. "
                           "Better than Playwright for web automation.",
            "install_hint": {
                "windows": "https://files.browseros.com/download/BrowserOS_installer.exe",
                "mac": "https://files.browseros.com/download/BrowserOS.dmg",
                "linux": "https://files.browseros.com/download/BrowserOS.AppImage",
            },
            "mcp": {
                "name": "browseros",
                "type": "http",
                "url": "http://localhost:9876",
                "auto_connect": True,
                "description": "BrowserOS agentic browser - 53+ browser automation tools",
            },
            "post_install": "Run 'browseros-cli init' after installing BrowserOS.",
        },
        # Placeholder for future integrations.
    ]

    for integration in integrations:
        name = integration["name"]
        desc = integration["description"]
        if Confirm.ask(f"Install {name}? {desc} [y/N]", default=False):
            mcp_servers.append(integration["mcp"])
            console.print(f"[green]✓ {name} added to MCP config.[/]")
            import platform
            plat = platform.system().lower()
            hint = integration["install_hint"].get(plat, integration["install_hint"].get("linux", ""))
            if hint:
                console.print(f"[dim]Install from: {hint}[/]")
            if integration.get("post_install"):
                console.print(f"[dim]{integration['post_install']}[/]")
        else:
            console.print(f"[dim]Skipped. Add later: jala mcp add {integration['key']}[/]")

    # --- Build and write config ---
    new_config = {
        "agent": {"name": "JalaAgent", "model": "claude-sonnet-4-6", "max_iterations": 100},
        "provider": {
            "default": provider,
            provider: {"api_key": f"${{{provider.upper()}_API_KEY}}"},
            "ollama": {"base_url": "http://localhost:11434"},
        },
        "memory": {
            "embedding_model": embedding_model,
            "embedding_dim": embedding_dim,
            "embedding_base_url": embedding_url,
            "dreaming": {"enabled": True, "schedule": "0 3 * * *"},
        },
        "approval": {
            "mode": mode,
            "rules": {
                "file_read": "auto",
                "file_write": "auto",
                "file_delete": "ask",
                "shell_exec": "ask",
                "network_get": "auto",
                "network_post": "ask",
                "messaging_send": "ask",
                "memory_write": "auto",
            },
        },
        "channels": {
            "telegram": {"token": "${TELEGRAM_BOT_TOKEN}", "allowed_users": []},
            "cli": {"enabled": True},
        },
        "mcp": {"idle_timeout": 300, "servers": mcp_servers},
    }

    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(yaml.dump(new_config, default_flow_style=False), encoding="utf-8")

    console.print(f"\n[green]✅ Config written to {_CONFIG_PATH}[/]")
    console.print(
        "\n[bold]Next steps:[/]\n"
        "  1. Set your API key env vars (e.g., ANTHROPIC_API_KEY)\n"
        "  2. Ensure Ollama is running (if using local embeddings)\n"
        "  3. Run [bold]jala[/] to start chatting!\n"
    )


def _load_existing() -> dict:
    if _CONFIG_PATH.exists():
        try:
            with _CONFIG_PATH.open(encoding="utf-8") as f:
                return yaml.safe_load(f.read()) or {}
        except Exception:
            pass
    return {}
