"""WhatsApp message parsing and dispatch.

Mirrors the Telegram handlers pattern — parses incoming WhatsApp messages,
dispatches slash commands through the CommandRegistry, and routes plain
text to the agent loop.
"""

from __future__ import annotations

import logging
from typing import Any

from agent_core.commands import CommandContext, CommandResult

logger = logging.getLogger(__name__)


class WhatsAppHandlers:
    """Parse WhatsApp messages and dispatch to agent loop or command handlers."""

    def __init__(self, channel: Any, command_registry: Any = None) -> None:
        self._channel = channel
        self._registry = command_registry

    async def handle_message(self, sender: str, text: str) -> str | None:
        """Process an incoming WhatsApp message.

        Returns the agent's response text, or None if the message was
        handled internally (e.g. a command).
        """
        if not text.strip():
            return None

        # Slash command dispatch
        if text.startswith("/"):
            return await self._dispatch_command(sender, text)

        # Raw message → agent loop
        return await self._channel.process_message(sender, text)

    async def _dispatch_command(self, sender: str, raw: str) -> str | None:
        """Look up and execute a slash command."""
        if not self._registry:
            logger.warning("No command registry — cannot dispatch '%s'", raw)
            return None

        parts = raw[1:].split(None, 1)  # strip leading /
        name = parts[0].lower()
        args_str = parts[1] if len(parts) > 1 else ""

        cmd = self._registry.get(name)
        if cmd:
            ctx = CommandContext(
                channel="whatsapp",
                args=args_str.split() if args_str else [],
                raw=raw,
            )
            try:
                result: CommandResult = await cmd.handler(ctx)
                return result.text if result else None
            except Exception:
                logger.exception("Command '%s' failed", name)
                return f"Command '{name}' failed — check logs."

        # Not a command — check skills
        skills = self._registry.list_skills()
        if name in skills:
            return await self._channel.process_message(
                sender, f"<skill name=\"{name}\">{skills[name]}</skill>"
            )

        logger.debug("Unknown command or skill: '%s'", name)
        return None
