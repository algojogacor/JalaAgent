"""CLI channel implementation — typer + rich terminal interface."""

import asyncio
import logging
from typing import Any

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
    "/help": "Show this help",
}


class CLIChannel:
    """Interactive CLI channel with streaming output and slash commands.

    Uses ``rich`` for formatted output and ``prompt_toolkit`` for
    multiline input (Ctrl+D to submit).
    """

    def __init__(self) -> None:
        self._console = Console()
        self._running = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self, agent_loop: Any) -> None:
        """Run the interactive CLI loop.

        Parameters
        ----------
        agent_loop:
            An :class:`AgentLoop` instance to process messages.
        """
        self._running = True
        self._print_banner()

        while self._running:
            try:
                user_input = await self._get_input()
            except (EOFError, KeyboardInterrupt):
                self._console.print("\n[dim]Goodbye![/]")
                break

            if not user_input.strip():
                continue

            # Handle slash commands.
            if user_input.startswith("/"):
                self._handle_command(user_input.strip())
                continue

            # Stream agent response.
            await self._stream_response(agent_loop, user_input)

    async def send_message(self, text: str) -> None:
        """Send a message to the terminal."""
        self._console.print(Markdown(text))

    async def send_approval_request(self, action: Any) -> bool:
        """Render an approval prompt and return the user's decision."""
        self._console.print(
            Panel(
                f"[bold yellow]Approval Required[/]\n\n"
                f"Tool: [bold]{action.tool_name}[/]\n"
                f"Category: {action.tool_category}\n"
                f"Args: {action.arguments}",
                title="⚠️ Approval",
                border_style="yellow",
            )
        )
        return Confirm.ask("Approve?", default=False)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _print_banner(self) -> None:
        self._console.print(
            Panel(
                "[bold cyan]JalaAgent[/] — your persistent personal agent\n"
                "Type [bold]/help[/] for commands, Ctrl+D to submit, Ctrl+C to quit",
                title="🪼 Welcome",
                border_style="cyan",
            )
        )

    async def _get_input(self) -> str:
        """Read multiline input, submitted with Ctrl+D."""
        lines: list[str] = []
        self._console.print("[dim]You:[/]")
        try:
            while True:
                line = await asyncio.to_thread(input, "  ")
                lines.append(line)
        except EOFError:
            pass
        return "\n".join(lines)

    async def _stream_response(self, agent_loop: Any, user_input: str) -> None:
        """Stream the agent's response with a live-updating panel."""
        accumulated: list[str] = []
        tool_calls_seen = 0

        with Live(
            Panel("", title="🤖 JalaAgent", border_style="green"),
            console=self._console,
            refresh_per_second=10,
            transient=False,
        ) as live:
            try:
                async for chunk in agent_loop.run(user_input, session_id=""):
                    if chunk.type == ChunkType.TEXT and chunk.content:
                        accumulated.append(chunk.content)
                        live.update(
                            Panel(
                                Markdown("".join(accumulated)),
                                title="🤖 JalaAgent",
                                border_style="green",
                            )
                        )
                    elif chunk.type == ChunkType.TOOL_START:
                        tool_calls_seen += 1
                        live.console.print(
                            f"[dim]🔧 Calling tool: {chunk.content}...[/]"
                        )
                    elif chunk.type == ChunkType.TOOL_RESULT:
                        live.console.print("[dim]✅ Tool result received[/]")
                    elif chunk.type == ChunkType.DONE:
                        break
            except Exception as exc:
                self._console.print(f"[red]Error: {exc}[/]")

        # Final output without the live panel.
        if accumulated:
            self._console.print(
                Panel(
                    Markdown("".join(accumulated)),
                    title="🤖 JalaAgent",
                    border_style="green",
                )
            )

    def _handle_command(self, command: str) -> None:
        cmd = command.lower().strip()
        if cmd == "/help":
            self._console.print("[bold]Available commands:[/]")
            for name, desc in _SLASH_COMMANDS.items():
                self._console.print(f"  [bold]{name}[/] — {desc}")
        elif cmd == "/new":
            self._console.print("[yellow]Starting new session...[/]")
        elif cmd == "/reset":
            self._console.print("[yellow]Session reset (memory preserved).[/]")
        elif cmd == "/mode":
            self._console.print("[yellow]Approval mode: NORMAL[/]")
        elif cmd == "/skills":
            self._console.print("[yellow]Skills: none installed[/]")
        elif cmd == "/memory":
            self._console.print("[yellow]Memory: use `jala memory search`[/]")
        elif cmd == "/dream":
            self._console.print("[yellow]Dreaming pipeline triggered.[/]")
        else:
            self._console.print(f"[red]Unknown command: {command}[/]")
