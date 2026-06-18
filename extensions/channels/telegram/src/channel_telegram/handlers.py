"""Telegram message and command handlers."""

import logging
from typing import Any

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


class TelegramHandlers:
    """Handlers for Telegram messages, commands, and callback queries."""

    def __init__(self, channel: Any) -> None:
        self._channel = channel

    # ------------------------------------------------------------------
    # Message handler
    # ------------------------------------------------------------------

    async def handle_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Process incoming text messages."""
        if update.message is None or update.message.text is None:
            return

        user = update.effective_user
        if not self._channel.is_allowed(user):
            logger.warning("Blocked message from non-allowed user %s", user)
            return

        text = update.message.text.strip()
        if text.startswith("/"):
            await self._handle_command(update, context)
        else:
            await self._channel.process_message(update, text)

    # ------------------------------------------------------------------
    # Command handlers
    # ------------------------------------------------------------------

    async def _handle_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Route a command to the appropriate handler."""
        if update.message is None:
            return
        text = (update.message.text or "").strip()
        cmd = text.lower().split()[0] if text else ""

        handlers = {
            "/new": self.cmd_new,
            "/reset": self.cmd_reset,
            "/mode": self.cmd_mode,
            "/skills": self.cmd_skills,
            "/memory": self.cmd_memory,
            "/approve": self.cmd_approve,
            "/reject": self.cmd_reject,
            "/dream": self.cmd_dream,
            "/help": self.cmd_help,
        }

        handler = handlers.get(cmd, self.cmd_unknown)
        await handler(update, context)

    async def cmd_new(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message:
            await update.message.reply_text("🆕 Starting a new session...")

    async def cmd_reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message:
            await update.message.reply_text("🔄 Session reset (memory preserved).")

    async def cmd_mode(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        from channel_telegram.keyboards import mode_keyboard

        if update.message:
            await update.message.reply_text(
                "Select approval mode:",
                reply_markup=mode_keyboard(),
            )

    async def cmd_skills(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message:
            await update.message.reply_text("🔧 Installed skills: (none)")

    async def cmd_memory(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message:
            await update.message.reply_text("🧠 Memory: use /memory search <query>")

    async def cmd_approve(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message:
            await update.message.reply_text("✅ No pending approvals.")

    async def cmd_reject(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message:
            await update.message.reply_text("❌ No pending approvals to reject.")

    async def cmd_dream(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message:
            await update.message.reply_text("🌙 Dreaming pipeline triggered...")

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message:
            await update.message.reply_text(
                "🪼 **JalaAgent Commands**\n\n"
                "/new — Start new session\n"
                "/reset — Reset session\n"
                "/mode — Switch approval mode\n"
                "/skills — List skills\n"
                "/memory — Search memory\n"
                "/approve — Approve pending\n"
                "/reject — Reject pending\n"
                "/dream — Run dreaming pipeline\n"
                "/help — This help",
            )

    async def cmd_unknown(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message:
            await update.message.reply_text("Unknown command. Type /help for commands.")

    # ------------------------------------------------------------------
    # Callback handler
    # ------------------------------------------------------------------

    async def handle_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle inline keyboard button presses."""
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
            await query.edit_message_text("✅ All pending actions approved.")
        elif data.startswith("mode:"):
            mode = data.split(":", 1)[1]
            await query.edit_message_text(f"Mode set to: {mode}")
