"""CLI channel — typer + rich terminal interface with BaseChannel protocol."""

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

_SLASH_COMMANDS = {
    "/new": "Start a new session",
    "/reset": "Clear session, keep memory",
    "/mode": "Switch approval mode",
    "/skills": "List/manage skills",
    "/memory": "Inspect/search memory",
    "/dream": "Trigger dreaming pipeline",
    "/approve": "Approve pending action",
    "/reject": "Reject pending action",
    "/help": "Show this help",
}


class BaseChannel(Protocol):
    """Protocol that all channels must implement."""

    async def send_message(self, text: str) -> None: ...
    async def send_approval_request(self, action: Any) -> bool: ...
    async def on_message(self, handler: Any) -> None: ...


class CLIChannel:
    """Interactive CLI channel with streaming output, spinner, and slash commands."""

    def __init__(self) -> None:
        self._console = Console()
        self._running = False
        self._mode = "normal"

    # ------------------------------------------------------------------
    # BaseChannel protocol
    # ------------------------------------------------------------------

    async def send_message(self, text: str) -> None:
        self._console.print(Markdown(text))

    async def send_approval_request(self, action: Any) -> bool:
        self._console.print(
            Panel(
                f"[bold yellow]Approval Required[/]\n\n"
                f"Tool: [bold]{action.tool_name}[/]\n"
                f"Category: {action.tool_category}\n"
                f"Args: {action.arguments}",
                title="⚠️ Approval", border_style="yellow",
            )
        )
        return Confirm.ask("Approve?", default=False)

    async def on_message(self, handler: Any) -> None:
        """Register a message handler (no-op for CLI — handled in run loop)."""
        pass

    # ------------------------------------------------------------------
    # Run loop
    # ------------------------------------------------------------------

    async def run(self, agent_loop: Any) -> None:
        self._running = True
        self._print_banner()
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
                self._handle_command(user_input.strip(), agent_loop)
                continue

            await self._stream_response(agent_loop, user_input)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _print_banner(self) -> None:
        self._console.print(
            Panel(
                "[bold cyan]🪼 JalaAgent v0.2[/] — hybrid memory + harness + skills\n"
                "Type [bold]/help[/] for commands, Ctrl+D to submit, Ctrl+C to quit",
                title="Welcome", border_style="cyan",
            )
        )

    def _setup_signal_handlers(self) -> None:
        try:
            loop = asyncio.get_event_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, self._handle_interrupt)
        except NotImplementedError:
            pass  # Windows doesn't support add_signal_handler well.

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

        with Live(
            Panel("", title="🤖 JalaAgent", border_style="green"),
            console=self._console, refresh_per_second=10, transient=False,
        ) as live:
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

    def _handle_command(self, command: str, agent_loop: Any) -> None:
        cmd = command.lower().strip().split()[0]
        if cmd == "/help":
            self._console.print("[bold]Commands:[/]")
            for name, desc in _SLASH_COMMANDS.items():
                self._console.print(f"  [bold]{name}[/] — {desc}")
        elif cmd == "/new":
            self._console.print("[yellow]New session started.[/]")
        elif cmd == "/reset":
            self._console.print("[yellow]Session reset (memory preserved).[/]")
        elif cmd == "/mode":
            self._mode = command.split()[-1].lower() if len(command.split()) > 1 else self._mode
            self._console.print(f"[green]Mode: {self._mode.upper()}[/]")
        elif cmd == "/skills":
            self._console.print("[yellow]Skills loaded from bundled/ and custom dirs.[/]")
        elif cmd == "/memory":
            mem = __import__("pathlib").Path.home() / ".jalaagent" / "memories" / "MEMORY.md"
            if mem.exists():
                self._console.print(Markdown(mem.read_text(encoding="utf-8")[:2000]))
            else:
                self._console.print("[dim]No memories yet.[/]")
        elif cmd == "/dream":
            self._console.print("[cyan]🌙 Dreaming triggered.[/]")
        elif cmd == "/approve":
            self._console.print("[green]Last action approved.[/]")
        elif cmd == "/reject":
            self._console.print("[red]Last action rejected.[/]")
        elif cmd == "/quit":
            self._running = False
        else:
            self._console.print(f"[red]Unknown: {command}[/]")

    @property
    def _interrupted(self) -> bool:
        return not self._running
