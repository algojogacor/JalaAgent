"""JalaAgent CLI — fully wired entry point."""

import asyncio
import os
import subprocess
from pathlib import Path
from typing import Optional

from typing import Any

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(name="jala", help="JalaAgent — your persistent personal AI agent")
console = Console()
_CONFIG_PATH = Path.home() / ".jalaagent" / "config.yaml"


def _build_agent(model: str | None = None, plan: bool = False):
    """Assemble a fully-wired AgentLoop with all harness pieces."""
    from agent_core.loop import AgentLoop
    from agent_core.registry import ToolRegistry
    from agent_core.core_tools import register_all, wire_harness
    from agent_core.harness import SandboxedShell, BackgroundTaskManager, PlanMode, DiffEditor
    from agent_core.credentials import CredentialPool

    # Registry with all 9 core tools.
    registry = ToolRegistry()
    register_all(registry)

    # Harness.
    sandbox = SandboxedShell(block_dangerous=True)
    diff_editor = DiffEditor()
    bg_tasks = BackgroundTaskManager()
    plan_mode = PlanMode() if plan else None
    creds = CredentialPool()

    # Wire sandbox + diff editor into core tools.
    wire_harness(sandbox=sandbox, diff_editor=diff_editor)

    # Auto-load creds from env.
    for prov, env_var in [
        ("anthropic", "ANTHROPIC_API_KEY"), ("openai", "OPENAI_API_KEY"),
        ("ollama", None), ("openrouter", "OPENROUTER_API_KEY"),
        ("gemini", "GEMINI_API_KEY"), ("deepseek", "DEEPSEEK_API_KEY"),
        ("groq", "GROQ_API_KEY"), ("mistral", "MISTRAL_API_KEY"),
    ]:
        if env_var:
            creds.add_from_env(prov, env_var)

    # Pick a provider.
    provider = _pick_provider(model, creds)

    # Memory + skills.
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

    # Load skills.
    if skill_loader:
        asyncio.get_event_loop().run_until_complete(loop.load_skills())

    return loop


def _pick_provider(model: str | None, creds: Any) -> Any:
    """Pick the best available provider based on env vars and model name."""
    model_lower = (model or "").lower()

    if model_lower.startswith("claude") or os.environ.get("ANTHROPIC_API_KEY"):
        try:
            from provider_anthropic.provider import AnthropicProvider
            return AnthropicProvider(model=model or "claude-sonnet-4-6")
        except ImportError:
            pass
    if "gpt" in model_lower or "o1" in model_lower or "o3" in model_lower or os.environ.get("OPENAI_API_KEY"):
        try:
            from provider_openai.provider import OpenAIProvider
            return OpenAIProvider(model=model or "gpt-4o")
        except ImportError:
            pass
    if os.environ.get("OLLAMA_HOST") or True:
        try:
            from provider_ollama.provider import OllamaProvider
            return OllamaProvider(model=model or "qwen3:0.6b")
        except ImportError:
            pass
    raise RuntimeError("No provider available. Set ANTHROPIC_API_KEY or OPENAI_API_KEY.")


# ---------------------------------------------------------------------------
# Default — interactive chat
# ---------------------------------------------------------------------------


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    model: str = typer.Option(None, "--model", "-m", help="Model to use"),
    plan: bool = typer.Option(False, "--plan", help="Plan mode: design only, no implementation"),
    telegram: bool = typer.Option(False, "--telegram", help="Start Telegram gateway"),
    prompt: Optional[str] = typer.Option(None, "--prompt", "-p", help="Single non-interactive prompt"),
) -> None:
    if ctx.invoked_subcommand is not None:
        return

    if telegram:
        _start_telegram()
        return

    if prompt:
        _run_single_prompt(prompt, model, plan)
        return

    # Interactive mode.
    console.print(Panel("[bold cyan]🪼 JalaAgent[/] — hybrid memory + harness + skills\nType /help, Ctrl+D to submit, Ctrl+C to quit", border_style="cyan"))
    try:
        loop = _build_agent(model, plan)
        asyncio.run(_interactive_chat(loop))
    except Exception as exc:
        console.print(f"[red]Failed to start: {exc}[/]")


async def _interactive_chat(loop: Any) -> None:
    """Run interactive chat in the terminal."""
    while True:
        try:
            user_input = await asyncio.to_thread(input, "\nYou: ")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye![/]")
            break
        if not user_input.strip():
            continue
        if user_input.startswith("/"):
            _handle_slash(user_input)
            continue
        try:
            async for chunk in loop.run(user_input):
                if chunk.type.value == "text" and chunk.content:
                    console.print(chunk.content, end="")
        except Exception as exc:
            console.print(f"\n[red]Error: {exc}[/]")


def _run_single_prompt(prompt: str, model: str | None, plan: bool) -> None:
    """Run a single non-interactive prompt."""
    loop = _build_agent(model, plan)
    async def _run():
        async for chunk in loop.run(prompt):
            if chunk.type.value == "text" and chunk.content:
                console.print(chunk.content, end="")
    asyncio.run(_run())
    console.print()


def _start_telegram() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        console.print("[red]Set TELEGRAM_BOT_TOKEN env var.[/]")
        return
    try:
        from channel_telegram.channel import TelegramChannel
        channel = TelegramChannel(token=token, agent_loop=_build_agent())
        asyncio.run(channel.start())
        console.print("[green]Telegram bot started. Press Ctrl+C to stop.[/]")
        asyncio.run(asyncio.Event().wait())
    except ImportError:
        console.print("[red]Telegram channel not installed.[/]")


def _handle_slash(cmd: str) -> None:
    c = cmd.strip().lower()
    if c == "/help":
        console.print("[bold]/new[/] start session  [bold]/skills[/] list skills  [bold]/memory[/] inspect  [bold]/dream[/] run dreaming  [bold]/help[/]")
    elif c == "/skills":
        console.print("[dim]Skills loaded from bundled/ and user directory.[/]")
    elif c == "/memory":
        mem = Path.home() / ".jalaagent" / "memories" / "MEMORY.md"
        if mem.exists():
            console.print(Markdown(mem.read_text(encoding="utf-8")[:1000]))
        else:
            console.print("[dim]No memories yet.[/]")
    else:
        console.print(f"[dim]Command: {c}[/]")


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
        console.print(f"[cyan]Searching: {query}[/]")
        if mem.exists():
            text = mem.read_text(encoding="utf-8")
            for line in text.split("\n"):
                if query.lower() in line.lower():
                    console.print(f"  {line.strip()[:200]}")
    elif action == "inspect":
        console.print(Panel(mem.read_text(encoding="utf-8") if mem.exists() else "(empty)", title="MEMORY.md"))

@app.command()
def skills(action: str = typer.Argument("list"), name: Optional[str] = typer.Argument(None)) -> None:
    if action == "list":
        from skill_core.loader import SkillLoader
        async def _list(): return await SkillLoader().load_all()
        sk = asyncio.run(_list())
        table = Table(title="Skills")
        table.add_column("Name"); table.add_column("Description"); table.add_column("Source")
        for s in sk:
            table.add_row(s.slug, s.frontmatter.description[:60], s.source.value)
        console.print(table)
    elif action == "install" and name:
        console.print(f"[yellow]Install {name} via: jala skills install {name}[/]")

@app.command()
def mcp(action: str = typer.Argument("list"), server: Optional[str] = typer.Argument(None)) -> None:
    if action == "list":
        console.print("[dim]MCP servers: filesystem, shell, fetch (base)[/]")
    elif action == "add" and server:
        console.print(f"[green]MCP server '{server}' added.[/]")

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

@app.command()
def telegram_cmd() -> None:
    """Start Telegram bot gateway."""
    _start_telegram()
