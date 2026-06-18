"""Telegram command handlers — unified slash command registry dispatch."""

import logging
from typing import Any

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


class TelegramHandlers:
    """Handlers for Telegram messages, commands, and callbacks — routed through unified registry."""

    def __init__(self, channel: Any, command_registry: Any = None) -> None:
        self._channel = channel
        self._registry = command_registry

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None or update.message.text is None:
            return
        user = update.effective_user
        if not self._channel.is_allowed(user):
            logger.warning("Blocked message from %s", user)
            return
        text = update.message.text.strip()
        if text.startswith("/"):
            await self._dispatch_command(update, text)
        else:
            await self._channel.process_message(update, text)

    async def _dispatch_command(self, update: Update, raw: str) -> None:
        if update.message is None or self._registry is None:
            return
        from agent_core.commands import CommandContext
        parts = raw.split()
        name = parts[0].lstrip("/").lower().split("@")[0]  # Strip bot username.
        cmd = self._registry.get(name)
        if cmd is None:
            skills = self._registry.list_skills()
            if name in skills:
                await self._channel.process_message(update, raw)
                return
            if update.message:
                await update.message.reply_text(f"Unknown: /{name}. Type /help.")
            return
        ctx = CommandContext(channel="telegram", args=parts[1:], raw=raw, agent_loop=self._channel._agent_loop)
        try:
            result = await cmd.handler(ctx)
            if result and result.text and update.message:
                await update.message.reply_text(result.text[:4000], reply_markup=result.keyboard)
        except Exception as exc:
            if update.message:
                await update.message.reply_text(f"Error: {exc}")

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None:
            return
        await query.answer()
        data = query.data or ""
        if data.startswith("approve:"):
            await query.edit_message_text(f"✅ Approved: {data.split(':', 1)[1]}")
        elif data.startswith("reject:"):
            await query.edit_message_text(f"❌ Rejected: {data.split(':', 1)[1]}")
        elif data.startswith("approve_all:"):
            await query.edit_message_text("✅ All approved.")
        elif data.startswith("mode:"):
            await query.edit_message_text(f"Mode: {data.split(':', 1)[1]}")
