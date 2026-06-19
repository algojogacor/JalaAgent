"""Context compaction (5-phase compression) for JalaAgent.

Compression is triggered when messages exceed 80% of the model's context
window.  The 5-phase algorithm preserves recent context while summarising
older content.
"""

import logging
from typing import Any

from agent_core.models import AgentMessage, ContentBlock

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Approximate characters-per-token ratio for estimation.  Real token counting
# is done by the provider's ``count_tokens``; this is a fallback heuristic.
_CHARS_PER_TOKEN = 4

# Number of tokens to reserve for the most recent messages (protected zone).
_PROTECTED_TOKENS = 20_000


# ---------------------------------------------------------------------------
# ContextCompactor
# ---------------------------------------------------------------------------


class ContextCompactor:
    """5-phase context compression for long conversations.

    Algorithm (per CLAUDE.md):

    1. **Prune** old tool results — remove tool results older than the
       last N turns.
    2. **Deduplicate** — remove repeated identical messages.
    3. **Protect** recent — keep the last ~20K tokens untouched.
    4. **Budget tail** — retain a small portion of the oldest messages
       for continuity.
    5. **Summarize middle** — summarise the middle segment into a
       structured summary block.
    """

    def __init__(self, token_counter: Any | None = None) -> None:
        """Initialise with an optional provider token counter.

        Parameters
        ----------
        token_counter:
            A callable ``(messages, system) -> int`` that provides
            accurate token counts.  If *None*, a character-based
            heuristic (chars/4) is used as a fallback.
        """
        self._token_counter = token_counter

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def should_compact(
        messages: list[AgentMessage],
        model_context_limit: int,
        threshold: float = 0.8,
        token_counter: Any | None = None,
    ) -> bool:
        """Check whether compaction should be triggered.

        Parameters
        ----------
        messages:
            Current conversation messages.
        model_context_limit:
            The model's context window size in **tokens**.
        threshold:
            Fraction of the context limit at which to trigger compaction
            (default: 0.8).
        token_counter:
            Optional callable for accurate token counting.  Falls back
            to the char/4 heuristic if *None*.

        Returns
        -------
        bool
            ``True`` if the estimated token count exceeds the threshold.
        """
        estimated = ContextCompactor._estimate_tokens(messages, token_counter)
        return estimated > int(model_context_limit * threshold)

    @staticmethod
    async def compact(
        messages: list[AgentMessage],
        model_context_limit: int,
    ) -> list[AgentMessage]:
        """Compact *messages* to fit within *model_context_limit*.

        Parameters
        ----------
        messages:
            The full conversation history.
        model_context_limit:
            The model's context window size in **tokens**.

        Returns
        -------
        list[AgentMessage]
            A compressed message list that should fit within the limit.
        """
        if not messages:
            return messages

        # 1. Prune old tool results — keep only the most recent tool result
        #    per tool_call_id, and discard tool results older than the last
        #    N assistant turns.
        pruned = ContextCompactor._prune_old_tool_results(messages)

        # 2. Deduplicate — remove consecutive identical messages.
        deduped = ContextCompactor._deduplicate(pruned)

        # 3. Protect recent messages.
        protected, rest = ContextCompactor._split_protected(deduped)

        # 4. Budget tail — keep the first 1-2 messages for context.
        tail_count = min(2, len(rest))
        tail = rest[:tail_count]
        middle = rest[tail_count:]

        # 5. Summarize middle into a single system message.
        if middle:
            summary = ContextCompactor._build_summary(middle)
            result = tail + [summary] + protected
        else:
            result = tail + protected

        # Final safety: if still over limit, aggressively truncate middle.
        while (
            ContextCompactor._estimate_tokens(result) > model_context_limit
            and len(result) > len(protected) + len(tail)
        ):
            # Remove one message from just before the protected zone.
            remove_idx = len(result) - len(protected) - 1
            if remove_idx >= 0:
                result.pop(remove_idx)

        return result

    # ------------------------------------------------------------------
    # Phase helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _prune_old_tool_results(
        messages: list[AgentMessage],
    ) -> list[AgentMessage]:
        """Remove tool results not referenced by recent assistant turns."""
        # Find the last assistant message that has tool_calls.
        last_assistant_with_tools = -1
        for i in range(len(messages) - 1, -1, -1):
            msg = messages[i]
            if (
                msg.role == "assistant"
                and msg.tool_calls
                and len(msg.tool_calls) > 0
            ):
                last_assistant_with_tools = i
                break

        if last_assistant_with_tools == -1:
            return list(messages)

        # Collect referenced tool_call_ids from the last assistant.
        referenced_ids: set[str] = set()
        msg = messages[last_assistant_with_tools]
        if msg.tool_calls:
            for tc in msg.tool_calls:
                referenced_ids.add(tc.id)

        # Keep only tool messages referenced by the last assistant turn.
        kept: list[AgentMessage] = []
        for i, msg in enumerate(messages):
            if msg.role == "tool" and i < last_assistant_with_tools:
                if msg.tool_call_id and msg.tool_call_id in referenced_ids:
                    kept.append(msg)
                # else: prune this old tool result.
            else:
                kept.append(msg)

        return kept

    @staticmethod
    def _deduplicate(
        messages: list[AgentMessage],
    ) -> list[AgentMessage]:
        """Remove consecutive identical messages."""
        if not messages:
            return []
        result = [messages[0]]
        for msg in messages[1:]:
            prev = result[-1]
            if (
                prev.role == msg.role
                and prev.content == msg.content
                and prev.tool_calls == msg.tool_calls
            ):
                continue
            result.append(msg)
        return result

    @staticmethod
    def _split_protected(
        messages: list[AgentMessage],
    ) -> tuple[list[AgentMessage], list[AgentMessage]]:
        """Split *messages* into (protected_recent, rest).

        Protected: the last N messages that fit within ~PROTECTED_TOKENS.
        """
        protected: list[AgentMessage] = []
        token_budget = _PROTECTED_TOKENS

        for msg in reversed(messages):
            msg_tokens = ContextCompactor._estimate_tokens([msg])
            if token_budget - msg_tokens < 0 and protected:
                break
            protected.insert(0, msg)
            token_budget -= msg_tokens

        rest = messages[: len(messages) - len(protected)]
        return protected, rest

    @staticmethod
    def _build_summary(messages: list[AgentMessage]) -> AgentMessage:
        """Build a structured summary of the middle segment.

        Summary format (per CLAUDE.md):
        Goal, Completed Actions, Active State, Key Decisions, Remaining Work.
        """
        parts = [
            "## Context Summary (compacted)",
            "",
            "**Goal:** (inferred from conversation)",
            "**Completed Actions:** "
            + "; ".join(
                f"[{m.role}] {ContextCompactor._excerpt(m)}"
                for m in messages
                if m.role in ("user", "assistant")
            )[:500],
            "**Active State:** preserved in recent messages below.",
            "**Key Decisions:** see above actions.",
            "**Remaining Work:** continue from recent messages.",
        ]
        return AgentMessage(
            role="user",
            content="\n".join(parts),
        )

    @staticmethod
    def _excerpt(msg: AgentMessage, max_len: int = 80) -> str:
        """Return a brief excerpt of a message's content."""
        if isinstance(msg.content, str):
            text = msg.content
        else:
            text = " ".join(
                b.text for b in msg.content if isinstance(b, ContentBlock)
            )
        text = text.replace("\n", " ").strip()
        if len(text) > max_len:
            return text[: max_len - 3] + "..."
        return text

    # ------------------------------------------------------------------
    # Token estimation
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_tokens(
        messages: list[AgentMessage],
        token_counter: Any | None = None,
    ) -> int:
        """Token count estimate — uses provider counter when available.

        If *token_counter* is provided it is called with ``(messages, "")``
        and the return value is used directly.  Otherwise falls back to the
        character-count / 4 heuristic.
        """
        if token_counter is not None:
            try:
                return token_counter(messages, "")
            except Exception:
                logger.debug("Token counter failed, falling back to heuristic")

        total = 0
        for msg in messages:
            if isinstance(msg.content, str):
                total += len(msg.content)
            elif isinstance(msg.content, list):
                for block in msg.content:
                    total += len(block.text) if block.text else 0
        return total // _CHARS_PER_TOKEN
