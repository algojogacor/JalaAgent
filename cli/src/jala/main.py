"""JalaAgent CLI — gateway mode, unified commands, channels."""

import asyncio
import os
import subprocess
from pathlib import Path
from typing import Any, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table

app = typer.Typer(name="jala", help="JalaAgent — persistent personal AI agent")
console = Console()
_CONFIG_PATH = Path.home() / ".jalaagent" / "config.yaml"


def _build_agent(model: str | None = None, plan: bool = False) -> Any:
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
        memory = MemoryRetriever(cfg, FileLayer(cfg), VectorLayer(cfg))
    except Exception: pass

    try:
        from skill_core.loader import SkillLoader
        skill_loader = SkillLoader()
    except Exception: pass

    # Read fallback providers from config.
    fallback = []
    try:
        cfg = _load_jala_config()
        fallback = cfg.get("fallback_providers", ["deepseek", "openrouter", "groq", "mistral", "ollama"])
    except Exception: pass

    loop = AgentLoop(
        provider=provider, registry=registry, memory_retriever=memory,
        skill_loader=skill_loader, sandbox=sandbox, bg_tasks=bg_tasks,
        plan_mode=plan_mode, credential_pool=creds, model=model or "claude-sonnet-4-6",
        fallback_providers=fallback,
    )
    if skill_loader:
        asyncio.get_event_loop().run_until_complete(loop.load_skills())
    return loop


def _load_jala_config() -> dict:
    import yaml
    p = Path.home() / ".jalaagent" / "config.yaml"
    return yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}

def _pick_provider(model: str | None, creds: Any) -> Any:
    model_lower = (model or "").lower()
    if model_lower.startswith("claude") or os.environ.get("ANTHROPIC_API_KEY"):
        from provider_anthropic.provider import AnthropicProvider
        return AnthropicProvider(model=model or "claude-sonnet-4-6")
    if "gpt" in model_lower or "o1" in model_lower or os.environ.get("OPENAI_API_KEY"):
        from provider_openai.provider import OpenAIProvider
        return OpenAIProvider(model=model or "gpt-4o")
    # Default to universal provider (config-driven).
    try:
        from provider_universal.provider import OpenAICompatibleProvider  # type: ignore[import-untyped]
        cfg = _load_jala_config()
        default_prov = cfg.get("model", {}).get("provider", "deepseek")
        default_m = cfg.get("model", {}).get("default", "deepseek-chat")
        return OpenAICompatibleProvider(default_provider=default_prov, default_model=default_m)
    except Exception:
        from provider_ollama.provider import OllamaProvider
        return OllamaProvider(model=model or "qwen3:0.6b")

def _build_auxiliary() -> Any:  # pyright: ignore[reportUnusedFunction] — used by dreaming_runner + bg tasks
    """Build a cheaper auxiliary provider for dreaming + background tasks."""
    cfg = _load_jala_config()
    aux = cfg.get("auxiliary", {})
    prov = aux.get("provider", "deepseek")
    model = aux.get("model", "deepseek-chat")
    try:
        from provider_universal.provider import OpenAICompatibleProvider  # pyright: ignore
        return OpenAICompatibleProvider(default_provider=prov, default_model=model)
    except Exception:
        return _pick_provider(model, None)


def _setup_registry(agent_loop: Any) -> Any:
    """Setup command registry with auto-registered skill commands + bodies."""
    from agent_core.commands import get_registry
    reg = get_registry()
    if agent_loop._skill_loader:
        try:
            skills = asyncio.get_event_loop().run_until_complete(agent_loop._skill_loader.load_all())
            for sk in skills:
                reg.register_skill(sk.slug, sk.frontmatter.description, sk.body)
        except Exception: pass
    return reg


def _gateway_banner(loop: Any, skills_count: int, tokens: dict[str, bool]) -> None:
    model = getattr(loop, "_model", "default")
    tg = "✓" if tokens.get("telegram") else "✗"
    console.print(Panel(
        f"[bold cyan]🪼 JalaAgent v2026.6.18[/] · {model}\n\n"
        f"Channels:  CLI ✓  Telegram {tg}\n"
        f"Skills:    {skills_count} bundled\n"
        f"MCP:       filesystem ✓  shell ✓  fetch ✓\n"
        f"Memory:    ~/.jalaagent/memories/\n"
        f"Mode:      NORMAL",
        title="Gateway Active", border_style="cyan",
    ))


async def _run_gateway(loop: Any, reg: Any) -> None:
    from channel_cli.channel import CLIChannel
    cli = CLIChannel(command_registry=reg)
    tasks: list[asyncio.Task[Any]] = [asyncio.create_task(cli.run(loop), name="cli")]

    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if tg_token:
        from channel_telegram.channel import TelegramChannel
        tg = TelegramChannel(token=tg_token, agent_loop=loop, command_registry=reg)
        await tg.start()
        tasks.append(asyncio.create_task(tg.run_polling(), name="telegram"))

    _gateway_banner(loop, len(reg.list_skills()), {"telegram": bool(tg_token)})
    try:
        await asyncio.gather(*tasks)
    except (KeyboardInterrupt, asyncio.CancelledError):
        console.print("\n[dim]Shutting down...[/]")
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def main_cli() -> None:
    asyncio.run(_main_async())


async def _main_async() -> None:
    loop = _build_agent()
    reg = _setup_registry(loop)
    cli = __import__("channel_cli.channel", fromlist=["CLIChannel"]).CLIChannel(command_registry=reg)
    await cli.run(loop)


# ---------------------------------------------------------------------------
# Typer app
# ---------------------------------------------------------------------------

@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    model: str = typer.Option(None, "--model", "-m", help="Model"),
    plan: bool = typer.Option(False, "--plan", help="Plan mode"),
    telegram: bool = typer.Option(False, "--telegram", help="Telegram only"),
    prompt: Optional[str] = typer.Option(None, "--prompt", "-p", help="Single prompt"),
) -> None:
    if ctx.invoked_subcommand is not None:
        return

    # First-run detection: no config + no provider env vars → offer setup.
    if not _CONFIG_PATH.exists():
        has_env = any(os.environ.get(v) for v in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY", "OLLAMA_HOST"])
        auth = Path.home() / ".jalaagent" / "auth.json"
        if not has_env and not auth.exists():
            console.print("[yellow]First run detected! No config or API keys found.[/]")
            if Confirm.ask("Run setup wizard now?", default=True):
                from jala.setup import run_setup
                run_setup()
            else:
                console.print("[dim]Run 'jala setup' later to configure.[/]")
            return

    if telegram:
        _start_telegram(model, plan)
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
    # Default: gateway if telegram configured, CLI otherwise.
    reg = _setup_registry(agent_loop)
    asyncio.run(_run_gateway(agent_loop, reg))


def _start_telegram(model: str | None, plan: bool) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        console.print("[red]Set TELEGRAM_BOT_TOKEN[/]")
        return
    agent_loop = _build_agent(model, plan)
    reg = _setup_registry(agent_loop)
    from channel_telegram.channel import TelegramChannel
    channel = TelegramChannel(token=token, agent_loop=agent_loop, command_registry=reg)
    console.print("[green]Telegram bot starting...[/]")
    asyncio.run(channel.start())
    asyncio.run(asyncio.Event().wait())


# ---------------------------------------------------------------------------
# Gateway command
# ---------------------------------------------------------------------------

@app.command()
def gateway(
    model: str = typer.Option(None, "--model", "-m", help="Model"),
) -> None:
    """Run all enabled channels simultaneously."""
    agent_loop = _build_agent(model)
    reg = _setup_registry(agent_loop)
    asyncio.run(_run_gateway(agent_loop, reg))


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

@app.command()
def setup() -> None:
    from jala.setup import run_setup; run_setup()

@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Bind host"),
    port: int = typer.Option(8787, "--port", "-p", help="Bind port"),
    token: Optional[str] = typer.Option(None, "--token", "-t", help="Auth token"),
) -> None:
    """Start JalaAgent as an Anthropic-compatible API server."""
    from jala.server import run_server
    run_server(host=host, port=port, token=token or os.environ.get("JALA_SERVE_TOKEN"))

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
        table = Table(title=f"Skills ({len(sk)} loaded)"); table.add_column("Name"); table.add_column("Desc"); table.add_column("Source")
        for s in sk: table.add_row(s.slug, s.frontmatter.description[:60], s.source.value)
        console.print(table)
    elif action == "info" and name:
        from skill_core.loader import SkillLoader
        async def _i():
            skills = await SkillLoader().load_all()
            for s in skills:
                if s.slug == name:
                    console.print(Panel(s.body[:2000], title=f"{s.slug}"))
                    return
            console.print(f"[red]Not found: {name}[/]")
        asyncio.run(_i())

@app.command()
def mcp(action: str = typer.Argument("list"), server: Optional[str] = typer.Argument(None)) -> None:
    if action == "list": console.print("[dim]Base MCP: filesystem, shell, fetch[/]")

@app.command()
def dream() -> None:
    console.print("[cyan]🌙 Dreaming triggered...[/]")

@app.command()
def config() -> None:
    editor = os.environ.get("EDITOR", "notepad")
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not _CONFIG_PATH.exists(): _CONFIG_PATH.write_text("# JalaAgent config\n", encoding="utf-8")
    subprocess.run([editor, str(_CONFIG_PATH)], check=False)
