"""JalaAgent CLI entry point — `jala` command via typer."""

import subprocess
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="jala",
    help="JalaAgent — your persistent personal AI agent",
)
console = Console()

_CONFIG_PATH = Path.home() / ".jalaagent" / "config.yaml"


# ---------------------------------------------------------------------------
# Main — start CLI session
# ---------------------------------------------------------------------------


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    telegram: bool = typer.Option(False, "--telegram", help="Start Telegram gateway"),
) -> None:
    """Start JalaAgent CLI session (default) or Telegram gateway."""
    if ctx.invoked_subcommand is not None:
        return

    if telegram:
        console.print("[yellow]Starting Telegram gateway...[/]")
        console.print(
            "[dim]Set TELEGRAM_BOT_TOKEN env var and run: jala telegram[/]"
        )
        return

    console.print("[bold cyan]JalaAgent CLI[/] — type /help for commands")
    console.print("[dim]Full interactive mode coming in v1.1[/]")


# ---------------------------------------------------------------------------
# setup
# ---------------------------------------------------------------------------


@app.command()
def setup() -> None:
    """Run the interactive first-time setup wizard."""
    from jala.setup import run_setup
    run_setup()


# ---------------------------------------------------------------------------
# memory
# ---------------------------------------------------------------------------


@app.command()
def memory(
    action: str = typer.Argument("inspect", help="Action: search or inspect"),
    query: Optional[str] = typer.Argument(None, help="Search query (for search)"),
) -> None:
    """Search or inspect memory."""
    if action == "search" and query:
        console.print(f"[cyan]Searching memory for:[/] {query}")
        console.print("[dim]Memory search requires a running agent.[/]")
    elif action == "inspect":
        mem_path = Path.home() / ".jalaagent" / "memories" / "MEMORY.md"
        user_path = Path.home() / ".jalaagent" / "memories" / "USER.md"

        console.print("[bold]MEMORY.md[/]")
        if mem_path.exists():
            console.print(mem_path.read_text(encoding="utf-8") or "(empty)")
        else:
            console.print("[dim](not created yet)[/]")

        console.print("\n[bold]USER.md[/]")
        if user_path.exists():
            console.print(user_path.read_text(encoding="utf-8") or "(empty)")
        else:
            console.print("[dim](not created yet)[/]")
    else:
        console.print("[red]Usage: jala memory search <query>  OR  jala memory inspect[/]")


# ---------------------------------------------------------------------------
# skills
# ---------------------------------------------------------------------------


@app.command()
def skills(
    action: str = typer.Argument("list", help="Action: list, install, or search"),
    name: Optional[str] = typer.Argument(None, help="Skill name (for install/search)"),
) -> None:
    """List, install, or search skills."""
    if action == "list":
        table = Table(title="Installed Skills")
        table.add_column("Name")
        table.add_column("Version")
        table.add_column("Source")
        table.add_row("(none)", "-", "-")
        console.print(table)
    elif action == "install" and name:
        console.print(f"[yellow]Installing skill: {name}...[/]")
        console.print("[dim]Skill installation requires a running agent.[/]")
    elif action == "search" and name:
        console.print(f"[cyan]Searching hub for:[/] {name}")
        console.print("[dim]Hub search coming in v2.[/]")
    else:
        console.print("[red]Usage: jala skills list|install <name>|search <query>[/]")


# ---------------------------------------------------------------------------
# mcp
# ---------------------------------------------------------------------------


@app.command()
def mcp(
    action: str = typer.Argument("list", help="Action: add or list"),
    server: Optional[str] = typer.Argument(None, help="Server name (for add)"),
) -> None:
    """Manage MCP servers."""
    if action == "add" and server:
        console.print(f"[yellow]Adding MCP server: {server}[/]")
        config = _read_config()
        servers = config.get("mcp", {}).get("servers", [])
        servers.append(server)
        console.print(f"[green]Added {server} to config.[/]")
    elif action == "list":
        config = _read_config()
        servers = config.get("mcp", {}).get("servers", [])
        if servers:
            for s in servers:
                console.print(f"  • {s}")
        else:
            console.print("[dim]No MCP servers configured.[/]")
    else:
        console.print("[red]Usage: jala mcp add <server>  OR  jala mcp list[/]")


# ---------------------------------------------------------------------------
# dream
# ---------------------------------------------------------------------------


@app.command()
def dream() -> None:
    """Run the dreaming pipeline manually."""
    console.print("[cyan]🌙 Running dreaming pipeline...[/]")
    console.print("[dim]Dreaming pipeline requires a running agent.[/]")


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------


@app.command()
def config() -> None:
    """Open config.yaml in $EDITOR."""
    editor = subprocess.getoutput("echo $EDITOR") or "notepad"
    if _CONFIG_PATH.exists():
        subprocess.run([editor, str(_CONFIG_PATH)], check=False)
    else:
        _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CONFIG_PATH.write_text(
            "# JalaAgent config\n"
            "# Run `jala setup` for interactive configuration.\n",
            encoding="utf-8",
        )
        subprocess.run([editor, str(_CONFIG_PATH)], check=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_config() -> dict:
    import yaml
    if _CONFIG_PATH.exists():
        with _CONFIG_PATH.open(encoding="utf-8") as f:
            return yaml.safe_load(f.read()) or {}
    return {}


# Entry point: ``jala`` console script in pyproject.toml calls ``jala.main:app`` directly.
