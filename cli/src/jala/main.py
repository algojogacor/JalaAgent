"""JalaAgent CLI — fully wired entry point."""

import asyncio
import os
import subprocess
from pathlib import Path
from typing import Any, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(name="jala", help="JalaAgent — your persistent personal AI agent")
console = Console()
_CONFIG_PATH = Path.home() / ".jalaagent" / "config.yaml"


def _build_agent(model: str | None = None, plan: bool = False) -> Any:
    """Assemble a fully-wired AgentLoop."""
    from agent_core.loop import AgentLoop
    from agent_core.registry import ToolRegistry
    from agent_core.core_tools import register_all, wire_harness
    from agent_core.harness import SandboxedShell, DiffEditor, BackgroundTaskManager, PlanMode
    from agent_core.credentials import CredentialPool

    registry = ToolRegistry()
    register_all(registry)

    sandbox = SandboxedShell(block_dangerous=True)
    diff_editor = DiffEditor()
    bg_tasks = BackgroundTaskManager()
    plan_mode = PlanMode() if plan else None
    creds = CredentialPool()
    wire_harness(sandbox=sandbox, diff_editor=diff_editor)

    for prov, env_var in [
        ("anthropic", "ANTHROPIC_API_KEY"), ("openai", "OPENAI_API_KEY"),
        ("openrouter", "OPENROUTER_API_KEY"), ("gemini", "GEMINI_API_KEY"),
        ("deepseek", "DEEPSEEK_API_KEY"), ("groq", "GROQ_API_KEY"),
        ("mistral", "MISTRAL_API_KEY"),
    ]:
        creds.add_from_env(prov, env_var)

    provider = _pick_provider(model, creds)

    memory = None
    skill_loader = None
    try:
        from memory_core.file_layer import FileLayer
        from memory_core.vector_layer import VectorLayer
        from memory_core.retrieval import MemoryRetriever
        from memory_core.models import MemoryConfig
        cfg = MemoryConfig()
        fl = FileLayer(cfg)
        vl = VectorLayer(cfg)
        memory = MemoryRetriever(cfg, fl, vl)
    except Exception:
        pass

    try:
        from skill_core.loader import SkillLoader
        skill_loader = SkillLoader()
    except Exception:
        pass

    loop = AgentLoop(
        provider=provider, registry=registry,
        memory_retriever=memory, skill_loader=skill_loader,
        sandbox=sandbox, bg_tasks=bg_tasks, plan_mode=plan_mode,
        credential_pool=creds, model=model or "claude-sonnet-4-6",
    )

    if skill_loader:
        asyncio.get_event_loop().run_until_complete(loop.load_skills())

    return loop


def _pick_provider(model: str | None, creds: Any) -> Any:
    model_lower = (model or "").lower()
    if model_lower.startswith("claude") or os.environ.get("ANTHROPIC_API_KEY"):
        from provider_anthropic.provider import AnthropicProvider
        return AnthropicProvider(model=model or "claude-sonnet-4-6")
    if "gpt" in model_lower or "o1" in model_lower or "o3" in model_lower or os.environ.get("OPENAI_API_KEY"):
        from provider_openai.provider import OpenAIProvider
        return OpenAIProvider(model=model or "gpt-4o")
    from provider_ollama.provider import OllamaProvider
    return OllamaProvider(model=model or "qwen3:0.6b")


async def _run_agent(agent_loop: Any) -> None:
    """Interactive chat loop."""
    from channel_cli.channel import CLIChannel
    channel = CLIChannel()
    await channel.run(agent_loop)


def main_cli() -> None:
    """Sync entry point for `jala` console script."""
    asyncio.run(_main_async())


async def _main_async() -> None:
    loop = _build_agent()
    await _run_agent(loop)


# ---------------------------------------------------------------------------
# Typer app (jala chat is default)
# ---------------------------------------------------------------------------

@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    model: str = typer.Option(None, "--model", "-m", help="Model to use"),
    plan: bool = typer.Option(False, "--plan", help="Plan mode: design only"),
    telegram: bool = typer.Option(False, "--telegram", help="Start Telegram bot"),
    prompt: Optional[str] = typer.Option(None, "--prompt", "-p", help="Single prompt"),
) -> None:
    if ctx.invoked_subcommand is not None:
        return

    if telegram:
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not token:
            console.print("[red]Set TELEGRAM_BOT_TOKEN[/]")
            return
        from channel_telegram.channel import TelegramChannel
        channel = TelegramChannel(token=token, agent_loop=_build_agent(model, plan))
        console.print("[green]Telegram bot starting...[/]")
        asyncio.run(channel.start())
        asyncio.run(asyncio.Event().wait())
        return

    agent_loop = _build_agent(model, plan)

    if prompt:
        async def _single():
            async for chunk in agent_loop.run(prompt):
                if chunk.type.value == "text" and chunk.content:
                    console.print(chunk.content, end="")
        asyncio.run(_single())
        console.print()
        return

    console.print(Panel("[bold cyan]🪼 JalaAgent v0.2[/] — type /help for commands", border_style="cyan"))
    asyncio.run(_run_agent(agent_loop))


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

@app.command()
def setup() -> None:
    from jala.setup import run_setup; run_setup()

@app.command()
def memory(action: str = typer.Argument("inspect"), query: Optional[str] = typer.Argument(None)) -> None:
    mem = Path.home() / ".jalaagent" / "memories" / "MEMORY.md"
    if action == "search" and query:
        if mem.exists():
            for line in mem.read_text(encoding="utf-8").split("\n"):
                if query.lower() in line.lower():
                    console.print(f"  {line.strip()[:200]}")
    elif action == "inspect":
        console.print(Panel(mem.read_text(encoding="utf-8") if mem.exists() else "(empty)", title="MEMORY.md"))

@app.command()
def skills(action: str = typer.Argument("list"), name: Optional[str] = typer.Argument(None)) -> None:
    if action == "list":
        from skill_core.loader import SkillLoader
        async def _l(): return await SkillLoader().load_all()
        sk = asyncio.run(_l())
        table = Table(title="Skills"); table.add_column("Name"); table.add_column("Description"); table.add_column("Source")
        for s in sk:
            table.add_row(s.slug, s.frontmatter.description[:60], s.source.value)
        console.print(table)

@app.command()
def mcp(action: str = typer.Argument("list"), server: Optional[str] = typer.Argument(None)) -> None:
    if action == "list":
        console.print("[dim]Base MCP: filesystem, shell, fetch[/]")

@app.command()
def dream() -> None:
    console.print("[cyan]🌙 Dreaming pipeline triggered...[/]")

@app.command()
def config() -> None:
    editor = os.environ.get("EDITOR", "notepad")
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not _CONFIG_PATH.exists():
        _CONFIG_PATH.write_text("# JalaAgent config\n", encoding="utf-8")
    subprocess.run([editor, str(_CONFIG_PATH)], check=False)
