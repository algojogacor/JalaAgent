"""Telegram channel implementation — python-telegram-bot async bot."""

import asyncio
import logging
from typing import Any

from agent_core.models import ChunkType

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
_APPROVAL_TIMEOUT = 60.0  # seconds — fail-closed (auto-deny on timeout)


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
        self._model_picker_state: dict[int, dict[str, Any]] = {}
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

        _ = await self._app.bot.send_message(
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
            result = await asyncio.wait_for(future, timeout=_APPROVAL_TIMEOUT)
        except TimeoutError:
            # Fail-closed: auto-deny on timeout. Never auto-approve.
            logger.warning("Approval for %s timed out after %.0fs — auto-deny", action.id, _APPROVAL_TIMEOUT)
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
                ctype = str(chunk.type) if hasattr(chunk, "type") else ""
                if chunk.type == ChunkType.TEXT and chunk.content:
                    accumulated.append(chunk.content)
                    now = asyncio.get_event_loop().time()
                    if now - last_edit >= _EDIT_INTERVAL:
                        await placeholder.edit_text("".join(accumulated))
                        last_edit = now
                elif chunk.type == ChunkType.THINKING and chunk.content:
                    # Append reasoning as italic prefix.
                    accumulated.append(f"\n_{chunk.content}_\n")
                elif chunk.type == ChunkType.TOOL_START:
                    accumulated.append(f"\n🔧 {chunk.content}...\n")
                elif chunk.type == ChunkType.ERROR and chunk.content:
                    accumulated.append(f"\n❌ {chunk.content}\n")
                elif chunk.type == ChunkType.DONE:
                    break
        except Exception as exc:
            logger.exception("Agent loop error")
            await placeholder.edit_text(f"❌ Error: {exc}")
            return

        # Final edit.
        if accumulated:
            await placeholder.edit_text("".join(accumulated))
        else:
            await placeholder.edit_text("(no response)")

    # ------------------------------------------------------------------
    # Model picker (interactive provider → model selection)
    # ------------------------------------------------------------------

    async def show_model_picker(self, chat_id: int, message_id: int | None = None) -> None:
        """Render the provider selection keyboard."""
        from agent_core.model_catalog import ModelCatalog
        catalog = ModelCatalog()
        providers = catalog.list_providers()

        provider_info: dict[str, int] = {}
        for prov in providers:
            try:
                provider_info[prov] = len(catalog.get_models(prov))
            except Exception:
                provider_info[prov] = 0

        keyboard = self._build_provider_keyboard(provider_info)
        text = (
            "⚙ **Model Configuration**\n\n"
            f"Current model: `{getattr(self._agent_loop, 'model', 'unknown')}`\n\n"
            "Select a provider:"
        )
        if message_id:
            await self._app.bot.edit_message_text(
                chat_id=chat_id, message_id=message_id,
                text=text, reply_markup=keyboard, parse_mode="Markdown",
            )
        else:
            await self._app.bot.send_message(
                chat_id=chat_id, text=text, reply_markup=keyboard, parse_mode="Markdown",
            )

    @staticmethod
    def _build_provider_keyboard(provider_info: dict[str, int]) -> Any:
        """Build provider selection inline keyboard."""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        buttons: list[list[Any]] = []
        row: list[Any] = []
        for prov, count in sorted(provider_info.items(), key=lambda x: x[0]):
            label = f"{prov} ({count})"
            row.append(InlineKeyboardButton(label, callback_data=f"mp:{prov}"))
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        buttons.append([InlineKeyboardButton("✕ Cancel", callback_data="mx:")])
        return InlineKeyboardMarkup(buttons)

    @staticmethod
    def _build_model_keyboard(
        provider: str, models: list[str], page: int = 0
    ) -> Any:
        """Build model selection inline keyboard with pagination."""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        per_page = 8
        start = page * per_page
        page_models = models[start:start + per_page]
        total_pages = (len(models) + per_page - 1) // per_page

        buttons: list[list[Any]] = []
        for i, m in enumerate(page_models):
            idx = start + i
            buttons.append([InlineKeyboardButton(m, callback_data=f"mm:{provider}:{idx}")])

        nav: list[Any] = []
        if page > 0:
            nav.append(InlineKeyboardButton("◀ Prev", callback_data=f"mg:{provider}:{page - 1}"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton("Next ▶", callback_data=f"mg:{provider}:{page + 1}"))
        if nav:
            buttons.append(nav)
        buttons.append([
            InlineKeyboardButton("◀ Back", callback_data="mb:"),
            InlineKeyboardButton("✕ Cancel", callback_data="mx:"),
        ])
        return InlineKeyboardMarkup(buttons)

    async def _handle_model_selected(
        self, chat_id: int, provider: str, model: str, message_id: int
    ) -> None:
        """Execute model switch and show confirmation."""
        from agent_core.model_catalog import resolve_base_url

        model_id = f"{provider}/{model}" if "/" not in model else model
        if self._agent_loop:
            self._agent_loop.model = model_id

        base_url = ""
        try:
            base_url = resolve_base_url(provider)
        except KeyError:
            pass

        text = (
            f"✅ **Switched to:** `{model_id}`\n"
            f"Provider: {provider}\n"
            + (f"Endpoint: {base_url}\n" if base_url else "")
            + "\nUse `/model --save` to make this permanent."
        )
        await self._app.bot.edit_message_text(
            chat_id=chat_id, message_id=message_id,
            text=text, parse_mode="Markdown",
        )
        self._model_picker_state.pop(chat_id, None)

    async def run_polling(self) -> None:
        """Start polling for updates (blocking)."""
        if self._app:
            await self._app.run_polling(drop_pending_updates=True)
            logger.info("Telegram polling started")
