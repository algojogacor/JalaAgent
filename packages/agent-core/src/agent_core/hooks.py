"""Hook registry — pre/post tool execution, session lifecycle hooks."""

import asyncio
import logging
from collections import defaultdict
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

HookCallback = Callable[[str, dict[str, Any]], Any]

_registry: dict[str, list[HookCallback]] = defaultdict(list)


def register(event: str, callback: HookCallback) -> None:
    """Register a hook callback for an event."""
    _registry[event].append(callback)


async def run(event: str, context: dict[str, Any] | None = None) -> list[Any]:
    """Run all hooks for an event. Returns list of results (exceptions logged, not raised)."""
    ctx = context or {}
    results = []
    for cb in _registry.get(event, []):
        try:
            result = cb(event, ctx)
            if asyncio.iscoroutine(result):
                result = await result
            results.append(result)
        except Exception:
            logger.exception("Hook %s failed", event)
    return results


# ── Convenience decorators ──

def on_pre_tool(func: HookCallback) -> HookCallback:
    register("pre_tool_execute", func)
    return func

def on_post_tool(func: HookCallback) -> HookCallback:
    register("post_tool_execute", func)
    return func

def on_tool_failure(func: HookCallback) -> HookCallback:
    register("post_tool_failure", func)
    return func

def on_session_start(func: HookCallback) -> HookCallback:
    register("session_start", func)
    return func

def on_session_end(func: HookCallback) -> HookCallback:
    register("session_end", func)
    return func
