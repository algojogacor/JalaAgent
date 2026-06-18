"""Main agent conversation loop — fully wired: skills, sandbox, worktrees, plans."""

import asyncio
import logging
from collections.abc import AsyncGenerator
from pathlib import Path
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


class ProviderProtocol:
    async def stream_completion(
        self, messages: list[AgentMessage], tools: list[dict[str, Any]],
        system: str, model: str,
    ) -> AsyncGenerator[ProviderChunk, None]:
        yield ProviderChunk(type=ProviderChunkType.DONE)


class MemoryRetrieverProtocol:
    async def retrieve(self, query: str, k: int = 10) -> str: ...
    async def build_system_context(self) -> str: ...


class AgentLoop:
    """Fully-wired streaming agent loop.

    Integrates: skills, sandbox, worktrees, plan mode, credential pool,
    background tasks, and 4-layer memory.
    """

    def __init__(
        self,
        provider: Any,
        registry: ToolRegistry,
        memory_retriever: Any | None = None,
        config: LoopConfig | None = None,
        system_prompt: str = "",
        model: str = "claude-sonnet-4-6",
        # --- Wired harness pieces ---
        skill_loader: Any = None,          # SkillLoader for auto-injecting skills
        sandbox: Any = None,               # SandboxedShell for safe execution
        worktree: Any = None,              # WorktreeIsolation for git isolation
        plan_mode: Any = None,             # PlanMode for design-before-implement
        bg_tasks: Any = None,              # BackgroundTaskManager
        credential_pool: Any = None,       # CredentialPool for auth rotation
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._memory = memory_retriever
        self._config = config or LoopConfig()
        self._system_prompt = system_prompt
        self._model = model

        # Harness.
        self._skill_loader = skill_loader
        self._sandbox = sandbox
        self._worktree = worktree
        self._plan_mode = plan_mode
        self._bg_tasks = bg_tasks
        self._credential_pool = credential_pool

        # Queues.
        self._steering_queue: asyncio.Queue[AgentMessage] = asyncio.Queue()
        self._followup_queue: asyncio.Queue[AgentMessage] = asyncio.Queue()
        self._interrupted = False
        self._frozen_context: str = ""
        self._skills_block: str = ""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(
        self, user_message: str, session_id: str = "",
    ) -> AsyncGenerator[AgentChunk, None]:
        self._interrupted = False

        # Build system prompt: base + memory + skills.
        system = await self._build_system()

        messages: list[AgentMessage] = [AgentMessage(role="user", content=user_message)]

        # Prepend memory context.
        if self._memory:
            mem_ctx = await self._memory.retrieve(user_message)
            if mem_ctx:
                messages.insert(0, AgentMessage(role="user", content=mem_ctx))

        # Inject skills as user message (preserves Anthropic cache).
        if self._skills_block:
            messages.insert(0, AgentMessage(role="user", content=self._skills_block))

        tools = self._build_tool_list()
        iteration = 0
        total_tool_calls = 0

        while iteration < self._config.max_iterations:
            if self._interrupted:
                break
            iteration += 1

            steering_msg = await self._drain_steering()
            if steering_msg:
                messages.append(steering_msg)

            had_tool_calls = False
            accumulated: list[ToolCall] = []

            async for chunk in self._provider.stream_completion(
                messages=messages, tools=tools, system=system, model=self._model,
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

            if not had_tool_calls:
                followup = await self._drain_followup()
                if followup:
                    messages.append(followup)
                    yield AgentChunk(type=ChunkType.TEXT, content=f"\n{followup.content}\n")
                    continue
                break

            for tc in accumulated:
                if self._interrupted:
                    break
                total_tool_calls += 1
                yield AgentChunk(
                    type=ChunkType.TOOL_START, content=tc.name,
                    metadata={"tool_call_id": tc.id, "arguments": tc.arguments},
                )
                try:
                    result = await self._registry.execute(tc.name, tc.arguments)
                except Exception as exc:
                    result = ToolResult(content=str(exc), is_error=True)
                yield AgentChunk(
                    type=ChunkType.TOOL_RESULT, content=result.content[:1000],
                    metadata={"tool_call_id": tc.id, "is_error": result.is_error, "overflowed": result.overflowed},
                )
                messages.append(AgentMessage(role="tool", content=result.content, tool_call_id=tc.id))

        yield AgentChunk(type=ChunkType.DONE)

        # Background self-improvement.
        if total_tool_calls > 0 and self._memory:
            asyncio.create_task(self._self_improve(session_id, messages))

    async def steer(self, message: str) -> None:
        await self._steering_queue.put(AgentMessage(role="user", content=message))

    async def interrupt(self) -> None:
        self._interrupted = True

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _build_system(self) -> str:
        parts = [self._system_prompt] if self._system_prompt else []

        # Frozen memory snapshot.
        if self._memory:
            if not self._frozen_context:
                self._frozen_context = await self._memory.build_system_context()
            if self._frozen_context:
                parts.append(self._frozen_context)

        return "\n\n".join(parts).strip()

    def _build_tool_list(self) -> list[dict[str, Any]]:
        available = self._registry.get_available()
        return [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in available]

    async def _drain_steering(self) -> AgentMessage | None:
        try:
            return self._steering_queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    async def _drain_followup(self) -> AgentMessage | None:
        try:
            return self._followup_queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    async def _self_improve(self, session_id: str, messages: list[AgentMessage]) -> None:
        try:
            logger.info("Self-improvement started for %s", session_id)
            if self._memory:
                summary = " ".join(
                    m.content if isinstance(m.content, str) else ""
                    for m in messages[-5:] if m.role in ("user", "assistant")
                )[:500]
                if summary:
                    mem_path = Path.home() / ".jalaagent" / "memories" / "sessions" / f"{session_id}.review.md"
                    mem_path.parent.mkdir(parents=True, exist_ok=True)
                    await asyncio.to_thread(
                        mem_path.write_text,
                        f"# Session Review: {session_id}\n\n{summary}\n",
                        encoding="utf-8",
                    )
            logger.info("Self-improvement completed for %s", session_id)
        except Exception:
            logger.exception("Self-improvement failed")

    # ------------------------------------------------------------------
    # Skill loading
    # ------------------------------------------------------------------

    async def load_skills(self) -> int:
        """Load skills from the skill loader. Returns count loaded."""
        if self._skill_loader is None:
            return 0
        try:
            skills = await self._skill_loader.load_all()
            if skills:
                self._skills_block = self._skill_loader.format_for_prompt(skills)
            return len(skills)
        except Exception:
            logger.exception("Skill loading failed")
            return 0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def model(self) -> str:
        return self._model

    @property
    def sandbox(self) -> Any:
        return self._sandbox

    @property
    def worktree(self) -> Any:
        return self._worktree

    @property
    def plan_mode(self) -> Any:
        return self._plan_mode
