"""CLI channel — rich terminal interface with unified slash command registry."""

import asyncio
import logging
import signal
from typing import Any, Protocol

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm

from agent_core.models import ChunkType

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
            f"[bold cyan]🪼 JalaAgent v2026.6.18[/] · {model}\n"
            f"Skills: {skills} bundled  |  MCP: filesystem ✓ shell ✓ fetch ✓\n"
            f"Type /help for commands, Ctrl+D to submit, Ctrl+C to quit",
            title="Welcome", border_style="cyan",
        ))

    def _setup_signal_handlers(self) -> None:
        try:
            loop = asyncio.get_event_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, self._handle_interrupt)
        except NotImplementedError:
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
        with Live(Panel("", title="🤖 JalaAgent", border_style="green"), console=self._console, refresh_per_second=10, transient=False) as live:
            try:
                async for chunk in agent_loop.run(user_input, session_id=""):
                    if self._interrupted:
                        await agent_loop.interrupt()
                        break
                    if chunk.type == ChunkType.TEXT and chunk.content:
                        accumulated.append(chunk.content)
                        live.update(Panel(Markdown("".join(accumulated)), title="🤖 JalaAgent", border_style="green"))
                    elif chunk.type == ChunkType.TOOL_START:
                        live.console.print(f"[dim]🔧 {chunk.content}...[/]")
                    elif chunk.type == ChunkType.TOOL_RESULT:
                        live.console.print("[dim]✅ Done[/]")
                    elif chunk.type == ChunkType.DONE:
                        break
            except Exception as exc:
                self._console.print(f"[red]Error: {exc}[/]")
        if accumulated:
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
            # Try skill auto-dispatch.
            skills = self._registry.list_skills()
            if name in skills:
                self._console.print(f"[green]Activating skill: {name}[/]")
                await self._stream_response(agent_loop, raw)
                return
            self._console.print(f"[red]Unknown command: /{name}[/]. Type /help.")
            return
        ctx = CommandContext(channel="cli", args=parts[1:], raw=raw, agent_loop=agent_loop)
        try:
            result = await cmd.handler(ctx)
            if result and result.text:
                self._console.print(Markdown(result.text))
        except Exception as exc:
            self._console.print(f"[red]Error: {exc}[/]")

    @property
    def _interrupted(self) -> bool:
        return not self._running
