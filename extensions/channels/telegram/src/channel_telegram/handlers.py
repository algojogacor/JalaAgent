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
            if result and result.action == "show_model_picker":
                # Send a placeholder then show the model picker on it.
                if update.message:
                    message = await update.message.reply_text("⚙ Loading model picker...")
                    await self._channel.show_model_picker(
                        update.message.chat_id, message.message_id,
                    )
                return
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
        # ── Model picker callbacks ──
        elif data.startswith("mp:"):
            await self._handle_model_picker_provider(query, data)
        elif data.startswith("mm:"):
            await self._handle_model_picker_select(query, data)
        elif data.startswith("mg:"):
            await self._handle_model_picker_page(query, data)
        elif data in ("mb:", "mx:"):
            await self._handle_model_picker_dismiss(query, data)

    async def _handle_model_picker_provider(self, query: Any, data: str) -> None:
        """User tapped a provider button (mp:<slug>). Show model list."""
        provider = data.split(":", 1)[1]
        from agent_core.model_catalog import ModelCatalog
        catalog = ModelCatalog()
        try:
            models = catalog.get_models(provider)
        except Exception:
            models = []

        chat_id = query.message.chat_id
        self._channel._model_picker_state[chat_id] = {
            "provider": provider, "models": models, "page": 0,
        }
        keyboard = self._channel._build_model_keyboard(provider, models, 0)
        text = f"**{provider}** — {len(models)} models\n\nSelect a model:"
        await query.edit_message_text(text=text, reply_markup=keyboard, parse_mode="Markdown")

    async def _handle_model_picker_select(self, query: Any, data: str) -> None:
        """User tapped a model button (mm:<provider>:<index>). Execute switch."""
        parts = data.split(":", 2)
        provider = parts[1]
        idx = int(parts[2]) if len(parts) > 2 else 0
        chat_id = query.message.chat_id
        state = self._channel._model_picker_state.get(chat_id, {})
        models = state.get("models", [])
        if idx < len(models):
            model = models[idx]
            await self._channel._handle_model_selected(
                chat_id, provider, model, query.message.message_id,
            )

    async def _handle_model_picker_page(self, query: Any, data: str) -> None:
        """User tapped pagination (mg:<provider>:<page>)."""
        parts = data.split(":", 2)
        provider = parts[1]
        page = int(parts[2]) if len(parts) > 2 else 0
        chat_id = query.message.chat_id
        state = self._channel._model_picker_state.get(chat_id, {})
        models = state.get("models", [])
        self._channel._model_picker_state[chat_id]["page"] = page
        keyboard = self._channel._build_model_keyboard(provider, models, page)
        await query.edit_message_reply_markup(reply_markup=keyboard)

    async def _handle_model_picker_dismiss(self, query: Any, data: str) -> None:
        """User tapped Cancel or Back."""
        if data == "mb:":
            # Back to provider selection.
            await self._channel.show_model_picker(
                query.message.chat_id, query.message.message_id,
            )
        else:
            # Cancel — dismiss.
            await query.edit_message_text("⚙ Model picker dismissed.")
