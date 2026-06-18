"""Central tool registry for JalaAgent with fuzzy name repair, loop detection, overflow handling."""

import asyncio
import difflib
import logging
import tempfile
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agent_core.models import (
    ActionCategory,
    LoopConfig,
    ToolDescriptor,
    ToolResult,
)
from agent_core.errors import ToolLoopError
from agent_core.policy import PolicyPipeline

logger = logging.getLogger(__name__)

# Handler signature: async callable receiving (arguments: dict) → ToolResult or str.
ToolHandler = Callable[[dict[str, Any]], Any]
CheckFn = Callable[[], bool]


class ToolRegistry:
    """Registry for tool definitions and dispatch.

    Features (per CLAUDE.md):

    * **Fuzzy name repair** — exact → case-insensitive → snake_case → difflib 0.7.
    * **Loop detection** — repeated identical calls → warning → hard stop.
    * **Overflow handling** — results > max chars → persist to temp file.
    * **Untrusted wrapping** — results from web/MCP → ``<untrusted_tool_result>`` XML.

    Parameters
    ----------
    loop_config:
        Configuration for loop detection thresholds.
    """

    def __init__(self, loop_config: LoopConfig | None = None) -> None:
        self._tools: dict[str, ToolDescriptor] = {}
        self._handlers: dict[str, ToolHandler] = {}
        self._check_fns: dict[str, CheckFn] = {}
        self._loop_config = loop_config or LoopConfig()
        # Call history for loop detection: (tool_name, arguments_hash).
        self._call_history: deque[tuple[str, int]] = deque(
            maxlen=self._loop_config.loop_detection_window
        )
        self._policy: PolicyPipeline | None = None

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        descriptor: ToolDescriptor,
        handler: ToolHandler,
        *,
        check_fn: CheckFn | None = None,
    ) -> None:
        """Register a tool with its handler.

        Parameters
        ----------
        descriptor:
            Tool metadata (name, description, schema, category).
        handler:
            Async callable that executes the tool.
        check_fn:
            Optional availability check — if it returns ``False`` the tool
            is hidden from ``get_available``.
        """
        self._tools[descriptor.name] = descriptor
        self._handlers[descriptor.name] = handler
        if check_fn is not None:
            self._check_fns[descriptor.name] = check_fn

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, name: str) -> ToolDescriptor | None:
        """Look up a tool by *name* with fuzzy repair.

        Returns ``None`` if the tool is not found.

        Repair pipeline (in order):

        1. Exact match.
        2. Case-insensitive match.
        3. snake_case ↔ camelCase normalisation.
        4. ``difflib.get_close_matches`` with 0.7 cutoff.
        """
        try:
            normalized = self._repair_name(name)
        except ValueError:
            return None
        return self._tools.get(normalized)

    def get_available(self) -> list[ToolDescriptor]:
        """Return all tools whose optional ``check_fn`` returns ``True``."""
        available: list[ToolDescriptor] = []
        for name, desc in self._tools.items():
            check = self._check_fns.get(name)
            if check is None or check():
                available.append(desc)
        return available

    # ------------------------------------------------------------------
    # Policy
    # ------------------------------------------------------------------

    def set_policy(self, policy: PolicyPipeline) -> None:
        self._policy = policy

    @property
    def policy(self) -> PolicyPipeline | None:
        return self._policy

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        is_untrusted: bool = False,
    ) -> ToolResult:
        """Execute a tool by *name* with *arguments*.

        Pipeline:

        1. Resolve tool name (with fuzzy repair).
        2. Check policy (if wired).
        3. Check for loop detection.
        4. Call the handler.
        5. Handle overflow (> max chars → temp file).
        6. Wrap untrusted results.

        Parameters
        ----------
        name:
            Tool name (fuzzy-repaired).
        arguments:
            Keyword arguments for the tool.
        is_untrusted:
            Mark the result as untrusted (web/MCP sources).

        Returns
        -------
        ToolResult
            The result with overflow/untrusted flags set as needed.

        Raises
        ------
        ToolLoopError
            If the loop hard-stop threshold is reached.
        ValueError
            If the tool name cannot be resolved.
        """
        # 1. Resolve tool.
        normalized = self._repair_name(name)
        if normalized not in self._handlers:
            raise ValueError(f"Unknown tool: {name!r}")

        descriptor = self._tools[normalized]
        handler = self._handlers[normalized]

        # 2. Policy check.
        if self._policy is not None:
            decision = self._policy.check(descriptor.category)
            if decision.value == "deny":
                return ToolResult(
                    content=f"Tool {name!r} denied by policy.",
                    is_error=True,
                )
            if decision.value == "ask":
                return ToolResult(
                    content=f"Tool {name!r} requires user approval — not available in unattended mode.",
                    is_error=True,
                )

        # 3. Loop detection.
        self._check_loop(normalized, arguments)

        # 3. Call handler (sync or async).
        try:
            result_or_coro = handler(arguments)
            if asyncio.iscoroutine(result_or_coro):
                raw = await result_or_coro
            else:
                raw = result_or_coro
        except Exception as exc:
            return ToolResult(
                content=str(exc),
                is_error=True,
                is_untrusted=is_untrusted,
            )

        # Coerce str → ToolResult.
        if isinstance(raw, str):
            result = ToolResult(content=raw)
        elif isinstance(raw, ToolResult):
            result = raw
        else:
            result = ToolResult(content=str(raw))

        # 4. Overflow handling.
        max_chars = descriptor.max_result_chars
        if len(result.content) > max_chars:
            result.overflowed = True
            result.overflow_path = await self._write_overflow(result.content)
            result.content = (
                f"Result too large ({len(result.content)} chars). "
                f"Written to: {result.overflow_path}"
            )

        # 5. Untrusted wrapping.
        if is_untrusted or result.is_untrusted:
            result.is_untrusted = True
            result.content = (
                f"<untrusted_tool_result>\n{result.content}\n"
                f"</untrusted_tool_result>"
            )

        return result

    # ------------------------------------------------------------------
    # Fuzzy name repair
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_snake_camel(name: str) -> str:
        """Convert between snake_case and camelCase for comparison."""
        # snake → camel: split on _, capitalise after first.
        if "_" in name:
            parts = name.split("_")
            return parts[0] + "".join(p.title() for p in parts[1:])
        # camel → snake: insert _ before uppercase.
        result: list[str] = []
        for ch in name:
            if ch.isupper() and result:
                result.append("_")
            result.append(ch.lower())
        return "".join(result)

    def _repair_name(self, name: str) -> str:
        """Repair *name* and return the canonical tool name.

        Raises ``ValueError`` if the name cannot be resolved.
        """
        # 1. Exact match.
        if name in self._tools:
            return name

        # 2. Case-insensitive.
        lower = name.lower()
        for key in self._tools:
            if key.lower() == lower:
                return key

        # 3. snake_case ↔ camelCase normalisation.
        alt = self._normalize_snake_camel(name)
        alt_lower = alt.lower()
        for key in self._tools:
            if key.lower() == alt_lower:
                return key
            if self._normalize_snake_camel(key).lower() == lower:
                return key

        # 4. difflib with 0.7 cutoff.
        matches = difflib.get_close_matches(
            name, list(self._tools.keys()), n=1, cutoff=0.7
        )
        if matches:
            return matches[0]

        raise ValueError(f"Unknown tool: {name!r}")

    # ------------------------------------------------------------------
    # Loop detection
    # ------------------------------------------------------------------

    @staticmethod
    def _hash_args(arguments: dict[str, Any]) -> int:
        """Simple hash of arguments for loop detection."""
        return hash(str(sorted(arguments.items())))

    def _check_loop(self, name: str, arguments: dict[str, Any]) -> None:
        """Check for repeated identical calls.  Raises :class:`ToolLoopError` on hard stop."""
        key = (name, self._hash_args(arguments))
        self._call_history.append(key)

        # Count consecutive identical calls.
        identical = 0
        for entry in reversed(self._call_history):
            if entry == key:
                identical += 1
            else:
                break

        cfg = self._loop_config
        if identical >= cfg.loop_hard_stop_threshold:
            raise ToolLoopError(
                f"Tool {name!r} called {identical} times in a row with the same "
                f"arguments — hard stop triggered"
            )
        if identical >= cfg.loop_warning_threshold:
            logger.warning(
                "Tool %r called %d times in a row — potential loop", name, identical
            )

    # ------------------------------------------------------------------
    # Overflow helper
    # ------------------------------------------------------------------

    @staticmethod
    async def _write_overflow(content: str) -> Path:
        """Write *content* to a temp file and return its path."""

        def _sync() -> Path:
            tmp = tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", suffix=".txt", delete=False
            )
            tmp.write(content)
            tmp.close()
            return Path(tmp.name)

        return await asyncio.to_thread(_sync)


# ---------------------------------------------------------------------------
# Default destructive categories (used by approval policies)
# ---------------------------------------------------------------------------

DESTRUCTIVE_CATEGORIES: set[ActionCategory] = {
    ActionCategory.FILE_WRITE,
    ActionCategory.FILE_DELETE,
    ActionCategory.SHELL_EXEC,
    ActionCategory.NETWORK_POST,
    ActionCategory.MESSAGING_SEND,
    ActionCategory.MEMORY_WRITE,
}
