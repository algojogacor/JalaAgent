"""Telegram channel implementation — python-telegram-bot async bot."""

import asyncio
import logging
from typing import Any

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from channel_telegram.handlers import TelegramHandlers

logger = logging.getLogger(__name__)

# Rate limiting: edit messages at most every 500ms.
_EDIT_INTERVAL = 0.5


class TelegramChannel:
    """Self-hosted Telegram bot channel for JalaAgent.

    Parameters
    ----------
    token:
        Telegram bot token from @BotFather.
    allowed_users:
        List of allowed user IDs. Empty list = allow all.
    agent_loop:
        An :class:`AgentLoop` instance for processing messages.
    """

    def __init__(
        self,
        token: str,
        allowed_users: list[int] | None = None,
        agent_loop: Any = None,
        command_registry: Any = None,
    ) -> None:
        self._token = token
        self._allowed_users = allowed_users or []
        self._agent_loop = agent_loop
        self._app: Application | None = None
        self._handlers = TelegramHandlers(self, command_registry)
        self._pending_approvals: dict[str, asyncio.Future[bool]] = {}
        self._registry = command_registry

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_allowed(self, user: Any) -> bool:
        """Check whether *user* is in the allowlist."""
        if not self._allowed_users:
            return True
        user_id = getattr(user, "id", None)
        return user_id in self._allowed_users

    async def start(self) -> None:
        """Build and start the Telegram bot application."""
        self._app = (
            Application.builder()
            .token(self._token)
            .build()
        )

        # Message handler.
        self._app.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                self._handlers.handle_message,
            )
        )

        # Command handlers — dynamically from registry.
        cmd_names = {"new", "help", "mode", "skills", "memory", "approve", "reject", "dream", "status", "stop", "agents", "version", "commands"}
        if self._registry:
            for cmd_def in self._registry.list_all():
                cmd_names.add(cmd_def.name)
                for a in cmd_def.aliases:
                    cmd_names.add(a)
        for cmd in sorted(cmd_names):
            self._app.add_handler(CommandHandler(cmd, self._handlers.handle_message))

        # Callback handler.
        self._app.add_handler(
            CallbackQueryHandler(self._handlers.handle_callback)
        )

        await self._app.initialize()
        await self._app.start()
        logger.info("Telegram bot started")

    async def stop(self) -> None:
        """Stop the bot gracefully."""
        if self._app:
            await self._app.stop()
            await self._app.shutdown()
            logger.info("Telegram bot stopped")

    async def send_message(self, chat_id: int, text: str) -> Any:
        """Send a message to a Telegram chat."""
        if self._app and self._app.bot:
            return await self._app.bot.send_message(
                chat_id=chat_id, text=text
            )
        return None

    async def send_approval_request(self, action: Any, chat_id: int) -> bool:
        """Send an approval request with inline keyboard and wait for response."""
        from channel_telegram.keyboards import approval_keyboard

        if not self._app or not self._app.bot:
            return False

        msg = await self._app.bot.send_message(
            chat_id=chat_id,
            text=(
                f"⚠️ **Approval Required**\n\n"
                f"Tool: `{action.tool_name}`\n"
                f"Category: {action.tool_category}\n"
                f"Args: `{action.arguments}`"
            ),
            reply_markup=approval_keyboard(action.id),
        )

        # Wait for callback.
        future: asyncio.Future[bool] = asyncio.Future()
        self._pending_approvals[action.id] = future
        try:
            result = await asyncio.wait_for(future, timeout=300.0)
        except asyncio.TimeoutError:
            result = False
        self._pending_approvals.pop(action.id, None)
        return result

    async def process_message(self, update: Update, text: str) -> None:
        """Process a user message through the agent loop."""
        if update.message is None or self._agent_loop is None:
            return

        chat_id = update.message.chat_id
        # Send a placeholder message.
        placeholder = await update.message.reply_text("🤔 Thinking...")

        accumulated: list[str] = []
        last_edit = asyncio.get_event_loop().time()

        try:
            async for chunk in self._agent_loop.run(text, session_id=str(chat_id)):
                if hasattr(chunk, "type") and str(chunk.type) == "text" and chunk.content:
                    accumulated.append(chunk.content)
                    now = asyncio.get_event_loop().time()
                    if now - last_edit >= _EDIT_INTERVAL:
                        await placeholder.edit_text("".join(accumulated))
                        last_edit = now
        except Exception as exc:
            logger.exception("Agent loop error")
            await placeholder.edit_text(f"❌ Error: {exc}")
            return

        # Final edit.
        if accumulated:
            await placeholder.edit_text("".join(accumulated))
        else:
            await placeholder.edit_text("(no response)")

    async def run_polling(self) -> None:
        """Start polling for updates (blocking)."""
        if self._app and self._app.updater:
            await self._app.updater.start_polling()
            logger.info("Telegram polling started")
