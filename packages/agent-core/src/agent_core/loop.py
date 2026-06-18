"""Main agent conversation loop for JalaAgent — streaming-first asyncio."""

import asyncio
import logging
from collections.abc import AsyncGenerator
from typing import Any

from agent_core.models import (
    AgentChunk,
    AgentMessage,
    ChunkType,
    LoopConfig,
    ProviderChunk,
    ProviderChunkType,
    ToolCall,
    ToolResult,
)
from agent_core.registry import ToolRegistry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provider protocol (avoids hard import dependency)
# ---------------------------------------------------------------------------


class ProviderProtocol:
    """Protocol that all LLM providers must satisfy for the agent loop."""

    async def stream_completion(
        self,
        messages: list[AgentMessage],
        tools: list[dict[str, Any]],
        system: str,
        model: str,
    ) -> AsyncGenerator[ProviderChunk, None]:
        """Stream completion chunks from the provider."""
        yield ProviderChunk(type=ProviderChunkType.DONE)  # pragma: no cover


class MemoryRetrieverProtocol:
    """Protocol for memory context injection."""

    async def retrieve(self, query: str, k: int = 10) -> str:
        """Return a ``<memory-context>`` block."""
        ...  # pragma: no cover

    async def build_system_context(self) -> str:
        """Return the frozen snapshot for the system prompt."""
        ...  # pragma: no cover


# ---------------------------------------------------------------------------
# AgentLoop
# ---------------------------------------------------------------------------


class AgentLoop:
    """Streaming-first asyncio agent conversation loop.

    Features (per CLAUDE.md):

    * **Frozen snapshot** — memory context captured once at session start.
    * **Two-tier queue** — steering (mid-run) + followup (post-stop).
    * **Background self-improvement** — daemon task after session.
    * **Max iterations** — configurable hard cap (default: 100).

    Parameters
    ----------
    provider:
        An LLM provider conforming to :class:`ProviderProtocol`.
    registry:
        A :class:`ToolRegistry` for executing tool calls.
    memory_retriever:
        Optional memory retriever for context injection.
    config:
        Loop configuration (iterations, etc.).
    system_prompt:
        Base system prompt (instructions for the agent).
    skills_formatter:
        Optional callable that returns a formatted skills block from a list
        of messages.
    model:
        The model name passed to the provider.
    """

    def __init__(
        self,
        provider: ProviderProtocol,
        registry: ToolRegistry,
        memory_retriever: MemoryRetrieverProtocol | None = None,
        config: LoopConfig | None = None,
        system_prompt: str = "",
        model: str = "claude-sonnet-4-6",
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._memory = memory_retriever
        self._config = config or LoopConfig()
        self._system_prompt = system_prompt
        self._model = model

        # Two-tier queue (per CLAUDE.md).
        self._steering_queue: asyncio.Queue[AgentMessage] = asyncio.Queue()
        self._followup_queue: asyncio.Queue[AgentMessage] = asyncio.Queue()

        # Interrupt flag.
        self._interrupted = False

        # Frozen snapshot — captured once at session start.
        self._frozen_context: str = ""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(
        self,
        user_message: str,
        session_id: str = "",
    ) -> AsyncGenerator[AgentChunk, None]:
        """Run the agent loop for a single user turn.

        Parameters
        ----------
        user_message:
            The user's input message.
        session_id:
            Identifier for the current session.

        Yields
        ------
        AgentChunk
            Streaming chunks representing the agent's response.
        """
        self._interrupted = False

        # 1. Build system prompt: base + frozen memory context.
        system = await self._build_system()

        # 2. Build messages.
        messages: list[AgentMessage] = [AgentMessage(role="user", content=user_message)]

        # 2b. Prepend memory context as user message if available.
        if self._memory:
            mem_ctx = await self._memory.retrieve(user_message)
            if mem_ctx:
                messages.insert(0, AgentMessage(role="user", content=mem_ctx))

        # 3. Get available tools.
        tools = self._build_tool_list()

        # 4. Main loop.
        iteration = 0
        total_tool_calls = 0

        while iteration < self._config.max_iterations:
            if self._interrupted:
                break

            iteration += 1

            # 4a. Check steering queue.
            steering_msg = await self._drain_steering()
            if steering_msg:
                messages.append(steering_msg)

            # 4b. Call provider.
            had_tool_calls = False
            accumulated: list[ToolCall] = []

            async for chunk in self._provider.stream_completion(
                messages=messages,
                tools=tools,
                system=system,
                model=self._model,
            ):
                if self._interrupted:
                    break

                if chunk.type == ProviderChunkType.TEXT and chunk.content:
                    yield AgentChunk(type=ChunkType.TEXT, content=chunk.content)

                elif chunk.type == ProviderChunkType.THINKING and chunk.content:
                    yield AgentChunk(type=ChunkType.THINKING, content=chunk.content)

                elif chunk.type == ProviderChunkType.TOOL_CALL and chunk.tool_call:
                    had_tool_calls = True
                    accumulated.append(chunk.tool_call)

                elif chunk.type == ProviderChunkType.DONE:
                    break

            if self._interrupted:
                break

            # 4c. If no tool calls, check followup queue.
            if not had_tool_calls:
                followup = await self._drain_followup()
                if followup:
                    messages.append(followup)
                    yield AgentChunk(
                        type=ChunkType.TEXT,
                        content=f"\n{followup.content}\n",
                    )
                    continue
                break

            # 4d. Execute tool calls.
            for tc in accumulated:
                if self._interrupted:
                    break
                total_tool_calls += 1
                yield AgentChunk(
                    type=ChunkType.TOOL_START,
                    content=tc.name,
                    metadata={"tool_call_id": tc.id, "arguments": tc.arguments},
                )

                try:
                    result = await self._registry.execute(tc.name, tc.arguments)
                except Exception as exc:
                    result = ToolResult(content=str(exc), is_error=True)

                yield AgentChunk(
                    type=ChunkType.TOOL_RESULT,
                    content=result.content[:1000],  # Truncate for streaming.
                    metadata={
                        "tool_call_id": tc.id,
                        "is_error": result.is_error,
                        "overflowed": result.overflowed,
                    },
                )

                # Add tool result to conversation.
                messages.append(
                    AgentMessage(
                        role="tool",
                        content=result.content,
                        tool_call_id=tc.id,
                    )
                )

        # 5. Done.
        yield AgentChunk(type=ChunkType.DONE)

        # 6. Background self-improvement (daemon task — do NOT await).
        if total_tool_calls > 0:
            asyncio.create_task(self._self_improve(session_id, messages))

    async def steer(self, message: str) -> None:
        """Inject a message into the steering queue for mid-run injection.

        The message will be injected before the next LLM call in the loop.
        """
        await self._steering_queue.put(AgentMessage(role="user", content=message))

    async def interrupt(self) -> None:
        """Signal the agent to stop at the next safe point."""
        self._interrupted = True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _build_system(self) -> str:
        """Assemble the system prompt."""
        parts = [self._system_prompt]

        if self._memory:
            if not self._frozen_context:
                # Capture frozen snapshot once.
                self._frozen_context = await self._memory.build_system_context()
            if self._frozen_context:
                parts.append(self._frozen_context)

        return "\n\n".join(parts).strip()

    def _build_tool_list(self) -> list[dict[str, Any]]:
        """Build the provider-native tool list from the registry."""
        available = self._registry.get_available()
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
            }
            for t in available
        ]

    async def _drain_steering(self) -> AgentMessage | None:
        """Drain at most one message from the steering queue."""
        try:
            return self._steering_queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    async def _drain_followup(self) -> AgentMessage | None:
        """Check the followup queue and return at most one message."""
        try:
            return self._followup_queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    async def _self_improve(
        self, session_id: str, messages: list[AgentMessage]
    ) -> None:
        """Background daemon task — reviews session and updates memory/skills.

        This runs as a detached ``asyncio.Task``.  It must NOT block the
        main session.  All writes go through the normal approval pipeline.
        """
        try:
            logger.info("Background self-improvement started for session %s", session_id)
            # Defer to the memory retriever's own logic, or run a mini-loop
            # with a restricted registry.  For v1 this is a hook point.
            await asyncio.sleep(0)  # placeholder — will be extended in v2.
            logger.info("Background self-improvement completed for session %s", session_id)
        except Exception:
            logger.exception("Self-improvement task failed")
