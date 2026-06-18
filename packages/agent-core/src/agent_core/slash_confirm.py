"""Slash confirm — module-level pending approval store.

Inspired by Hermes' slash_confirm.py: register/resolve/clear
with timeout, confirm_id matching, and thread-safe storage.
"""

import threading
import time
from typing import Any, Callable

_pending: dict[str, dict[str, Any]] = {}
_lock = threading.RLock()
DEFAULT_TIMEOUT = 300


def register(session_key: str, confirm_id: str, handler: Callable[[str], Any]) -> None:
    with _lock:
        _pending[session_key] = {
            "confirm_id": confirm_id,
            "handler": handler,
            "timestamp": time.monotonic(),
        }


def resolve(session_key: str, choice: str) -> str:
    with _lock:
        entry = _pending.pop(session_key, None)
        if entry is None:
            return "No pending confirmation."
        if time.monotonic() - entry["timestamp"] > DEFAULT_TIMEOUT:
            return "Confirmation expired."
        try:
            return entry["handler"](choice)
        except Exception as exc:
            return f"Error: {exc}"


def clear_if_stale(session_key: str) -> None:
    with _lock:
        entry = _pending.get(session_key)
        if entry and time.monotonic() - entry["timestamp"] > DEFAULT_TIMEOUT:
            _pending.pop(session_key, None)
