"""JalaAgent CLI — gateway mode, unified commands, channels."""

import sys

# Force UTF-8 on Windows terminals so emoji and Unicode render correctly.
# Without this, Rich crashes with UnicodeEncodeError on cmd.exe / PowerShell.
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from agent_core.paths import setup_import_paths
setup_import_paths()

import asyncio
import logging
import os
import subprocess
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table

logger = logging.getLogger(__name__)

app = typer.Typer(name="jala", help="JalaAgent — persistent personal AI agent")
console = Console()
_CONFIG_PATH = Path.home() / ".jalaagent" / "config.yaml"


def _build_agent(model: str | None = None, plan: bool = False) -> Any:
    from agent_core.compaction import ContextCompactor
    from agent_core.core_tools import register_all, wire_harness
    from agent_core.credentials import CredentialPool
    from agent_core.harness import BackgroundTaskManager, DiffEditor, PlanMode, SandboxedShell
    from agent_core.loop import AgentLoop
    from agent_core.registry import ToolRegistry
    from agent_core.repair import ToolArgRepairer

    jala_cfg = _load_jala_config()

    # ── ONE shared credential pool for the entire agent ──
    creds = CredentialPool()
    # Bulk-load from auth.json (handles both "key" and "access_token" fields).
    loaded = creds.add_from_auth_json()
    logger.debug("Credential pool: %d keys loaded from auth.json", loaded)
    # Also load from env vars.
    for prov, env_var in [
        ("anthropic", "ANTHROPIC_API_KEY"), ("openai", "OPENAI_API_KEY"),
        ("openrouter", "OPENROUTER_API_KEY"), ("deepseek", "DEEPSEEK_API_KEY"),
        ("groq", "GROQ_API_KEY"), ("mistral", "MISTRAL_API_KEY"),
    ]:
        creds.add_from_env(prov, env_var)

    provider = _pick_provider(model, creds)

    # ── Registry + tools ──
    registry = ToolRegistry()
    register_all(registry)

    # Wire config-sourced tool loop guardrails into registry.
    guardrails = jala_cfg.get("tool_loop_guardrails", {})
    if guardrails:
        registry.warn_threshold = guardrails.get("warn_after", {}).get("same_tool_failure", 3)
        registry.hard_stop_threshold = guardrails.get("hard_stop_after", {}).get("same_tool_failure", 5)

    sandbox = SandboxedShell(block_dangerous=True)
    diff_editor = DiffEditor()
    bg_tasks = BackgroundTaskManager()
    plan_mode = PlanMode() if plan else None
    wire_harness(sandbox=sandbox, diff_editor=diff_editor)

    # ── Compactor with configured thresholds ──
    comp_cfg = jala_cfg.get("compression", {})
    compactor: Any | None = None
    if comp_cfg.get("enabled", True):
        compactor = ContextCompactor(token_counter=None)

    # ── Tool repairer ──
    repairer = ToolArgRepairer()

    # ── Memory (all 4 layers wired) ──
    memory = None
    try:
        from memory_core.file_layer import FileLayer
        from memory_core.knowledge_graph import KnowledgeGraph
        from memory_core.models import MemoryConfig
        from memory_core.retrieval import MemoryRetriever
        from memory_core.vector_layer import VectorLayer
        cfg = MemoryConfig()
        file_layer = FileLayer(cfg)
        vector_layer = VectorLayer(cfg)
        kg_db = Path.home() / ".jalaagent" / "db" / "graph.db"
        kg_db.parent.mkdir(parents=True, exist_ok=True)
        kg = KnowledgeGraph(db_path=kg_db)
        memory = MemoryRetriever(cfg, file_layer, vector_layer, knowledge_graph=kg)
    except Exception:
        logger.debug("Optional subsystem unavailable, continuing without it")

    # ── Skill loader ──
    skill_loader = None
    try:
        from skill_core.loader import SkillLoader
        skill_loader = SkillLoader()
    except Exception:
        logger.debug("Optional subsystem unavailable, continuing without it")

    # ── Fallback providers ──
    fallback = jala_cfg.get("fallback_providers", ["deepseek", "openrouter", "groq", "mistral", "ollama"])

    loop = AgentLoop(
        provider=provider, registry=registry, memory_retriever=memory,
        skill_loader=skill_loader, sandbox=sandbox, bg_tasks=bg_tasks,
        plan_mode=plan_mode, credential_pool=creds, model=model or "claude-sonnet-4-6",
        fallback_providers=fallback, compactor=compactor, repairer=repairer,
    )
    return loop


def _load_jala_config() -> dict:
    import yaml
    p = Path.home() / ".jalaagent" / "config.yaml"
    return yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}

def _pick_provider(model: str | None, creds: Any) -> Any:
    """Pick the best provider based on available API keys (env + auth.json).

    Delegates to :class:`ProviderRouter` — a declarative registry that
    replaces the old 130-line if/elif chain.
    """
    from agent_core.providers import ProviderRouter

    router = ProviderRouter()
    return router.resolve(model=model, creds=creds)

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


def _get_registry_safe() -> Any:
    from agent_core.commands import get_registry
    return get_registry()

async def _load_skills_into_registry(loop: Any) -> None:
    if loop._skill_loader:
        skills = await loop._skill_loader.load_all()
        reg = _get_registry_safe()
        for sk in skills:
            reg.register_skill(sk.slug, sk.frontmatter.description, sk.body)


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
    await _load_skills_into_registry(loop)
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
    """Entry point — delegates to typer app for full CLI routing."""
    app()


# ---------------------------------------------------------------------------
# Typer app
# ---------------------------------------------------------------------------

@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    model: str = typer.Option(None, "--model", "-m", help="Model"),
    plan: bool = typer.Option(False, "--plan", help="Plan mode"),
    telegram: bool = typer.Option(False, "--telegram", help="Telegram only"),
    prompt: str | None = typer.Option(None, "--prompt", "-p", help="Single prompt"),
) -> None:
    if ctx.invoked_subcommand is not None:
        return

    # First-run detection: no config + no provider env vars → offer setup.
    if not _CONFIG_PATH.exists():
        has_env = any(os.environ.get(v) for v in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY", "OLLAMA_HOST"])
        auth = Path.home() / ".jalaagent" / "auth.json"
        if not has_env and not auth.exists():
            try:
                console.print("[yellow]First run detected! No config or API keys found.[/]")
                console.print("[dim]Run 'jala setup' to configure, or set DEEPSEEK_API_KEY / ANTHROPIC_API_KEY.[/]")
                if sys.stdin.isatty() and Confirm.ask("Run setup wizard now?", default=True):
                    from jala.setup import run_setup
                    run_setup()
            except Exception:
                pass
            if not _CONFIG_PATH.exists():
                console.print("[yellow]Provider may not be configured. Use 'jala setup' first.[/]")

    if telegram:
        _start_telegram(model, plan)
        return
    agent_loop = _build_agent(model, plan)
    if prompt:
        # Intercept slash commands — dispatch through command registry.
        if prompt.strip().startswith("/"):
            from agent_core.commands import CommandContext, get_registry
            console.print(f"[dim]Dispatching slash command: {prompt.strip()}[/]")
            parts = prompt.strip().split()
            name = parts[0].lstrip("/").lower()
            reg = get_registry()
            cmd = reg.get(name)
            if cmd is not None:
                ctx = CommandContext(
                    channel="cli", args=parts[1:], raw=prompt,
                    agent_loop=agent_loop,
                )
                async def _dispatch():
                    return await cmd.handler(ctx)
                result = asyncio.run(_dispatch())
                if result and result.text:
                    console.print(result.text)
                return
            # Fallback: check skills (matching channel_cli/channel.py dispatch).
            skills = reg.list_skills()
            if name in skills:
                body = reg.get_skill_body(name)
                skill_prompt = f"<skill name=\"{name}\">\n{body}\n</skill>\n\n{prompt}" if body else prompt
                console.print(f"[green]Activating skill: {name}[/]")
                async def _single_skill():
                    async for chunk in agent_loop.run(skill_prompt):
                        if chunk.type.value == "text" and chunk.content:
                            console.print(chunk.content, end="")
                        elif chunk.type.value == "error" and chunk.content:
                            console.print(f"\n[red]{chunk.content}[/]")
                        elif chunk.type.value == "tool_start":
                            console.print(f"[dim]🔧 {chunk.content}...[/]")
                        elif chunk.type.value == "tool_result":
                            status = "❌" if chunk.metadata and chunk.metadata.get("is_error") else "✅"
                            console.print(f"[dim]{status} Done[/]")
                asyncio.run(_single_skill())
                console.print()
                return
            console.print(f"[red]Unknown slash command: /{name}. Type /help for list.[/]")
            return

        async def _single():
            async for chunk in agent_loop.run(prompt):
                if chunk.type.value == "text" and chunk.content:
                    console.print(chunk.content, end="")
                elif chunk.type.value == "error" and chunk.content:
                    console.print(f"\n[red]{chunk.content}[/]")
                elif chunk.type.value == "tool_start":
                    console.print(f"[dim]🔧 {chunk.content}...[/]")
                elif chunk.type.value == "tool_result":
                    status = "❌" if chunk.metadata and chunk.metadata.get("is_error") else "✅"
                    console.print(f"[dim]{status} Done[/]")
        asyncio.run(_single())
        console.print()
        return
    # Default: gateway if telegram configured, CLI otherwise.
    asyncio.run(_run_gateway(agent_loop, _get_registry_safe()))


def _start_telegram(model: str | None, plan: bool) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        console.print("[red]Set TELEGRAM_BOT_TOKEN[/]")
        return
    agent_loop = _build_agent(model, plan)
    from channel_telegram.channel import TelegramChannel
    channel = TelegramChannel(token=token, agent_loop=agent_loop, command_registry=_get_registry_safe())
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
    asyncio.run(_run_gateway(agent_loop, _get_registry_safe()))


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
    token: str | None = typer.Option(None, "--token", "-t", help="Auth token"),
) -> None:
    """Start JalaAgent as an Anthropic-compatible API server."""
    from jala.server import run_server
    run_server(host=host, port=port, token=token or os.environ.get("JALA_SERVE_TOKEN"))

@app.command()
def memory(action: str = typer.Argument("inspect"), query: str | None = typer.Argument(None)) -> None:
    mem = Path.home() / ".jalaagent" / "memories" / "MEMORY.md"
    if action == "search" and query:
        if mem.exists():
            for line in mem.read_text(encoding="utf-8").split("\n"):
                if query.lower() in line.lower():
                    console.print(f"  {line.strip()[:200]}")
    elif action == "inspect":
        console.print(Panel(mem.read_text(encoding="utf-8") if mem.exists() else "(empty)", title="MEMORY.md"))

@app.command()
def skills(action: str = typer.Argument("list"), name: str | None = typer.Argument(None)) -> None:
    from skill_core.loader import SkillLoader

    async def _load():
        return await SkillLoader().load_all()

    if action == "list":
        sk = asyncio.run(_load())
        table = Table(title=f"Skills ({len(sk)} loaded)")
        table.add_column("Name"); table.add_column("Desc"); table.add_column("Source")
        for s in sk:
            table.add_row(s.slug, s.frontmatter.description[:60], s.source.value)
        console.print(table)
    elif action == "info" and name:
        async def _i():
            skills = await _load()
            for s in skills:
                if s.slug == name:
                    console.print(Panel(s.body[:2000], title=f"{s.slug}"))
                    return
            console.print(f"[red]Not found: {name}[/]")
        asyncio.run(_i())
    elif action == "manifest":
        from pathlib import Path as _Path
        manifest_path = _Path(__file__).resolve().parents[3] / "SKILLS_MANIFEST.md"
        if manifest_path.exists():
            console.print(manifest_path.read_text(encoding="utf-8")[:5000])
        else:
            console.print("[dim]SKILLS_MANIFEST.md not found — run 'jala skills list' to see loaded skills.[/]")
    elif action == "audit":
        from pathlib import Path as _Path
        audit_path = _Path(__file__).resolve().parents[3] / "AUDIT.md"
        if audit_path.exists():
            console.print(audit_path.read_text(encoding="utf-8")[:3000])
        else:
            console.print("[dim]AUDIT.md not found.[/]")
    else:
        console.print(f"[yellow]Unknown action: {action}. Try: list, info <name>, manifest, audit[/]")

@app.command()
def mcp(action: str = typer.Argument("list"), server: str | None = typer.Argument(None)) -> None:
    if action == "list": console.print("[dim]Base MCP: filesystem, shell, fetch[/]")

@app.command()
def dream() -> None:
    """Trigger the dreaming pipeline manually."""
    console.print("[cyan]🌙 Dreaming pipeline triggered...[/]")
    try:
        loop = _build_agent()
        if loop._memory:
            async def _run():
                from memory_core.dreaming_runner import DreamingRunner
                if hasattr(loop._memory, '_file_layer') and hasattr(loop._memory, '_vector_layer'):
                    runner = DreamingRunner(
                        config=loop._memory.config,
                        file_layer=loop._memory._file_layer,
                        vector_layer=loop._memory._vector_layer,
                        provider=loop._provider,
                    )
                    report = await runner.run_once()
                    console.print(
                        f"[green]✅ Dream complete:[/] "
                        f"{report.light_sleep_signals} signals, "
                        f"{report.rem_patterns} patterns, "
                        f"{report.deep_sleep_promotions} promoted"
                    )
                else:
                    console.print("[yellow]Memory layers not fully wired — dream skipped.[/]")
            asyncio.run(_run())
        else:
            console.print("[yellow]Memory subsystem not available.[/]")
    except Exception as exc:
        console.print(f"[red]Dream failed: {exc}[/]")

@app.command(name="config-show")
def config_show() -> None:
    """Print current configuration."""
    import yaml
    config_path = Path.home() / ".jalaagent" / "config.yaml"
    if config_path.exists():
        console.print(yaml.dump(
            yaml.safe_load(config_path.read_text(encoding="utf-8")),
            default_flow_style=False, sort_keys=False
        ))
    else:
        console.print("[yellow]No config found. Run 'jala setup' first.[/]")


@app.command(name="config-get")
def config_get(key: str = typer.Argument(...)) -> None:
    """Get a specific config value by dot-notation key."""
    import yaml
    config_path = Path.home() / ".jalaagent" / "config.yaml"
    if not config_path.exists():
        console.print("[yellow]No config found.[/]")
        return
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    for part in key.split("."):
        if isinstance(cfg, dict):
            cfg = cfg.get(part)
        else:
            console.print(f"[red]Cannot traverse '{part}'[/]")
            return
    console.print(cfg if cfg is not None else "[dim](not set)[/]")
