"""Telegram inline keyboard builders for approval requests."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def approval_keyboard(action_id: str) -> InlineKeyboardMarkup:
    """Build an inline keyboard with Approve / Reject / Approve All buttons.

    Parameters
    ----------
    action_id:
        Unique identifier for the action being approved.
    """
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve:{action_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject:{action_id}"),
        ],
        [
            InlineKeyboardButton(
                "✅ Approve All", callback_data=f"approve_all:{action_id}"
            ),
        ],
    ])


def mode_keyboard() -> InlineKeyboardMarkup:
    """Build a mode-selection keyboard."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔒 Paranoid", callback_data="mode:paranoid"),
            InlineKeyboardButton("🛡️ Normal", callback_data="mode:normal"),
        ],
        [
            InlineKeyboardButton("⚡ YOLO", callback_data="mode:yolo"),
            InlineKeyboardButton("⚙️ Custom", callback_data="mode:custom"),
        ],
    ])
