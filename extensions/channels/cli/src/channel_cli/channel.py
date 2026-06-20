"""CLI channel — rich terminal interface with unified slash command registry."""

import asyncio
import logging
import signal

from jala import __version__
from typing import Any, Protocol

from agent_core.models import ChunkType
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

logger = logging.getLogger(__name__)


class BaseChannel(Protocol):
    async def send_message(self, text: str) -> None: ...
    async def send_approval_request(self, action: Any) -> bool: ...
    async def on_message(self, handler: Any) -> None: ...


class CLIChannel:
    """CLI channel with unified command registry dispatch."""

    def __init__(self, command_registry: Any = None) -> None:
        self._console = Console()
        self._running = False
        self._mode = "normal"
        self._registry = command_registry

    async def send_message(self, text: str) -> None:
        self._console.print(Markdown(text))

    async def send_approval_request(self, action: Any) -> bool:
        """Request approval — fail-closed: defaults to No (deny)."""
        self._console.print(Panel(
            f"[bold yellow]Approval Required[/]\n\nTool: [bold]{action.tool_name}[/]\nCategory: {action.tool_category}\nArgs: {action.arguments}",
            title="⚠️ Approval", border_style="yellow",
        ))
        return Confirm.ask("Approve?", default=False)  # default=No → fail-closed

    async def on_message(self, handler: Any) -> None:
        pass

    async def run(self, agent_loop: Any) -> None:
        self._running = True
        self._print_banner(agent_loop)
        self._setup_signal_handlers()
        while self._running:
            try:
                user_input = await self._get_input()
            except (EOFError, KeyboardInterrupt):
                self._console.print("\n[dim]Goodbye![/]")
                break
            if not user_input.strip():
                continue
            if user_input.startswith("/"):
                await self._dispatch_command(user_input.strip(), agent_loop)
                continue
            await self._stream_response(agent_loop, user_input)

    def _print_banner(self, agent_loop: Any) -> None:
        model = getattr(agent_loop, "_model", "default")
        skills = "66" if self._registry else "—"
        self._console.print(Panel(
            f"[bold cyan]🪼 JalaAgent v{__version__}[/] · {model}\n"
            f"Skills: {skills} bundled  |  MCP: filesystem ✓ shell ✓ fetch ✓\n"
            f"Type /help for commands, Ctrl+D to submit, Ctrl+C to quit",
            title="Welcome", border_style="cyan",
        ))

    def _setup_signal_handlers(self) -> None:
        # Prefer asyncio signal handlers, but they raise NotImplementedError
        # on Windows.  Fall back to the classic signal.signal() which works
        # everywhere (the callback is invoked from the main thread on SIGINT).
        try:
            loop = asyncio.get_event_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, self._handle_interrupt)
        except NotImplementedError:
            for sig in (signal.SIGINT, signal.SIGTERM):
                try:
                    signal.signal(sig, lambda _signum, _frame: self._handle_interrupt())
                except (ValueError, OSError):
                    pass

    def _handle_interrupt(self) -> None:
        self._running = False

    async def _get_input(self) -> str:
        self._console.print("[dim]You:[/]")
        try:
            line = await asyncio.to_thread(input, "  ")
            return line
        except EOFError:
            return "/quit"

    async def _stream_response(self, agent_loop: Any, user_input: str) -> None:
        accumulated: list[str] = []
        error_msg: str | None = None
        with Live(Panel("🤔 Thinking...", title="🤖 JalaAgent", border_style="green"), console=self._console, refresh_per_second=10, transient=False) as live:
            try:
                async for chunk in agent_loop.run(user_input, session_id=""):
                    if self._interrupted:
                        await agent_loop.interrupt()
                        break
                    if chunk.type == ChunkType.TEXT and chunk.content:
                        accumulated.append(chunk.content)
                        live.update(Panel(Markdown("".join(accumulated)), title="🤖 JalaAgent", border_style="green"))
                    elif chunk.type == ChunkType.THINKING and chunk.content:
                        live.console.print(f"[dim italic]{chunk.content}[/]", end="")
                    elif chunk.type == ChunkType.TOOL_START:
                        live.console.print(f"[dim]🔧 {chunk.content}...[/]")
                    elif chunk.type == ChunkType.TOOL_RESULT:
                        status = "❌" if chunk.metadata and chunk.metadata.get("is_error") else "✅"
                        live.console.print(f"[dim]{status} Done[/]")
                    elif chunk.type == ChunkType.DONE:
                        break
                    elif chunk.type == ChunkType.ERROR:
                        error_msg = chunk.content or "Unknown error"
                        live.update(Panel(
                            f"[red]{error_msg}[/]\n\n"
                            "[dim]Tip: Run 'jala setup' to configure a provider, "
                            "or check your API keys in ~/.jalaagent/auth.json[/]",
                            title="🤖 JalaAgent — Error", border_style="red",
                        ))
            except Exception as exc:
                error_msg = str(exc)
                live.update(Panel(f"[red]Provider error: {exc}[/]\n\n[dim]Run 'jala setup' to configure a working provider, or set a valid API key.[/]", title="🤖 JalaAgent — Error", border_style="red"))
        if accumulated:
            self._console.print(Panel(Markdown("".join(accumulated)), title="🤖 JalaAgent", border_style="green"))
        elif error_msg:
            self._console.print(Panel(f"[red]{error_msg}[/]\n\n[dim]Tip: Run 'jala setup' to configure a provider, or check DEEPSEEK_API_KEY / ANTHROPIC_API_KEY.[/]", title="⚠️ No Response", border_style="yellow"))
            self._console.print(Panel(Markdown("".join(accumulated)), title="🤖 JalaAgent", border_style="green"))

    async def _dispatch_command(self, raw: str, agent_loop: Any) -> None:
        if self._registry is None:
            self._console.print("[red]No command registry configured.[/]")
            return
        from agent_core.commands import CommandContext
        parts = raw.split()
        name = parts[0].lstrip("/").lower()
        if name == "quit":
            self._running = False
            return
        cmd = self._registry.get(name)
        if cmd is None:
            skills = self._registry.list_skills()
            if name in skills:
                body = self._registry.get_skill_body(name)
                prompt = f"<skill name=\"{name}\">\n{body}\n</skill>\n\n{raw}" if body else raw
                self._console.print(f"[green]Activating skill: {name}[/]")
                await self._stream_response(agent_loop, prompt)
                return
            self._console.print(f"[red]Unknown command: /{name}[/]. Type /help.")
            return
        ctx = CommandContext(channel="cli", args=parts[1:], raw=raw, agent_loop=agent_loop)
        try:
            result = await cmd.handler(ctx)
            if result and result.action == "show_model_picker":
                await self._show_model_picker(result)
                return
            if result and result.text:
                self._console.print(Markdown(result.text))
        except Exception as exc:
            self._console.print(f"[red]Error: {exc}[/]")

    async def _show_model_picker(self, result: Any) -> None:
        """Interactive model picker for CLI channel via rich prompts."""
        provider_info = result.keyboard.get("providers", {}) if result.keyboard else {}
        if not provider_info:
            self._console.print(result.text)
            return

        provider_list = sorted(provider_info.items(), key=lambda x: x[0])
        self._console.print()
        self._console.print(Panel(
            f"Current model: {getattr(self._agent_loop, 'model', 'unknown')}",
            title="⚙ Model Configuration", border_style="cyan",
        ))
        self._console.print("\nSelect a provider:")
        for i, (prov, count) in enumerate(provider_list, 1):
            self._console.print(f"  {i}. {prov} ({count} models)")

        choice = Prompt.ask("Provider number", default="1")
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(provider_list):
                provider = provider_list[idx][0]
                from agent_core.model_catalog import ModelCatalog
                catalog = ModelCatalog()
                models = catalog.get_models(provider)
                if models:
                    self._console.print(f"\n[bold]{provider}[/] — {len(models)} models")
                    for i, m in enumerate(models[:20], 1):
                        self._console.print(f"  {i}. {m}")
                    model_choice = Prompt.ask("Model number", default="1")
                    try:
                        midx = int(model_choice) - 1
                        if 0 <= midx < len(models):
                            model = models[midx]
                            model_id = f"{provider}/{model}" if "/" not in model else model
                            if self._agent_loop:
                                self._agent_loop.model = model_id
                            self._console.print(f"[green]✅ Switched to: {model_id}[/]")
                    except (ValueError, IndexError):
                        self._console.print("[red]Invalid model selection.[/]")
        except (ValueError, IndexError):
            self._console.print("[red]Invalid provider selection.[/]")

    @property
    def _interrupted(self) -> bool:
        return not self._running
