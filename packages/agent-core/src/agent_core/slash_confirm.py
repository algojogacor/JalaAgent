"""Slash confirm — module-level pending approval store.

Inspired by Hermes' slash_confirm.py: register/resolve/clear
with timeout, confirm_id matching, and async-safe storage.
"""

import asyncio
import time
from collections.abc import Callable
from typing import Any

_pending: dict[str, dict[str, Any]] = {}
_lock = asyncio.Lock()
DEFAULT_TIMEOUT = 300


async def register(session_key: str, confirm_id: str, handler: Callable[[str], Any]) -> None:
    async with _lock:
        _pending[session_key] = {
            "confirm_id": confirm_id,
            "handler": handler,
            "timestamp": time.monotonic(),
        }


async def resolve(session_key: str, choice: str) -> str:
    async with _lock:
        entry = _pending.pop(session_key, None)
        if entry is None:
            return "No pending confirmation."
        if time.monotonic() - entry["timestamp"] > DEFAULT_TIMEOUT:
            return "Confirmation expired."
        try:
            return entry["handler"](choice)
        except Exception as exc:
            return f"Error: {exc}"


async def clear_if_stale(session_key: str) -> None:
    async with _lock:
        entry = _pending.get(session_key)
        if entry and time.monotonic() - entry["timestamp"] > DEFAULT_TIMEOUT:
            _pending.pop(session_key, None)
