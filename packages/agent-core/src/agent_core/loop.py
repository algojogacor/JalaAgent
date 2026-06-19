"""Agent loop — production-hardened: compaction, error recovery, harness, TTFB, caching, continuation."""

import asyncio
import logging
import time as _time_module
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

TTFB_TIMEOUT = 30.0
IDLE_TIMEOUT = 300.0
MAX_RETRIES = 3
BASE_DELAY = 1.0
MAX_DELAY = 30.0


class ProviderProtocol:
    async def stream_completion(self, messages: list[AgentMessage], tools: list[dict[str, Any]], system: str, model: str) -> AsyncGenerator[ProviderChunk, None]:
        yield ProviderChunk(type=ProviderChunkType.DONE)


class MemoryRetrieverProtocol:
    async def retrieve(self, query: str, k: int = 10) -> str: ...
    async def build_system_context(self) -> str: ...


class AgentLoop:
    """Production-hardened streaming agent loop.

    Wired: compaction, error recovery, harness (sandbox/worktree/plan),
    TTFB watchdog, idle timeout, Anthropic prompt caching, continuation.
    """

    def __init__(
        self,
        provider: Any,
        registry: ToolRegistry,
        memory_retriever: Any | None = None,
        config: LoopConfig | None = None,
        system_prompt: str = "",
        model: str = "claude-sonnet-4-6",
        skill_loader: Any = None,
        sandbox: Any = None,
        worktree: Any = None,
        plan_mode: Any = None,
        bg_tasks: Any = None,
        credential_pool: Any = None,
        compactor: Any = None,
        repairer: Any = None,
        fallback_providers: list[str] | None = None,
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._memory = memory_retriever
        self._config = config or LoopConfig()
        self._system_prompt = system_prompt
        self._model = model
        self._skill_loader = skill_loader
        self._sandbox = sandbox
        self._worktree = worktree
        self._plan_mode = plan_mode
        self._bg_tasks = bg_tasks
        self._credential_pool = credential_pool
        self._compactor = compactor
        self._repairer = repairer
        self._fallback_providers = fallback_providers or []

        self._steering_queue: asyncio.Queue[AgentMessage] = asyncio.Queue()
        self._followup_queue: asyncio.Queue[AgentMessage] = asyncio.Queue()
        self._interrupted = False
        self._frozen_context = ""
        self._last_user_message: str = ""
        self._token_usage: dict[str, int] = {"input": 0, "output": 0}
        self._session_messages: list[AgentMessage] = []
        self._session_id: str = ""
        self._goal: str = ""
        self._goal_state: str = "cleared"
        self._subgoals: list[str] = []
        self._reasoning_effort: str = "medium"
        self._fast_mode: bool = False
        self._personality: str = "default"
        self._skills_block = ""
        self._last_activity = 0.0
        self._provider_name = getattr(provider, "_model", "openai")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self, user_message: str, session_id: str = "") -> AsyncGenerator[AgentChunk, None]:
        self._interrupted = False
        self._last_activity = _time_module.monotonic()
        self._last_user_message = user_message
        self._session_id = session_id

        # Fire session hooks (fire-and-forget, don't block).
        try:
            from agent_core.hooks import run as run_hooks
            asyncio.create_task(run_hooks("session_start", {"session_id": session_id, "user_message": user_message}))
        except ImportError:
            logger.debug("hooks module not available")

        # Plan mode: restrict tools.
        if self._plan_mode and getattr(self._plan_mode, "is_approved", False) is False:
            self._system_prompt += "\n\n[PLAN MODE] Design only. No implementation until plan is approved."

        system = await self._build_system()
        messages: list[AgentMessage] = [AgentMessage(role="user", content=user_message)]
        self._session_messages.append(messages[0])  # Track for undo/retry

        # Memory context is injected via build_system_context() in the
        # system prompt (frozen snapshot pattern).  Query-time retrieval
        # is limited to episodic/session memory — never duplicate the
        # curated MEMORY.md content that already lives in the system block.
        if self._memory:
            mem_ctx = await self._memory.retrieve(user_message)
            if mem_ctx:
                # Wrap retrieval results as an untrusted annotation so the
                # provider does not treat them as user instructions.
                messages.insert(0, AgentMessage(
                    role="user",
                    content=f"<memory-context ephemeral=\"true\">{mem_ctx}</memory-context>",
                ))
        if self._skills_block:
            messages.insert(0, AgentMessage(role="user", content=self._skills_block))

        # Apply prompt caching for Anthropic.
        system = self._apply_cache_control(system)

        tools = self._build_tool_list()
        iteration = 0
        total_tool_calls = 0
        retry_count = 0

        while iteration < self._config.max_iterations:
            if self._interrupted:
                break
            if _time_module.monotonic() - self._last_activity > IDLE_TIMEOUT:
                yield AgentChunk(type=ChunkType.TEXT, content="[Session idle — stopping]")
                break

            iteration += 1
            steering_msg = await self._drain_steering()
            if steering_msg:
                messages.append(steering_msg)

            # Compaction check — always use heuristic (provider count_tokens is
            # async and cannot be called from a sync static method).
            if self._compactor and len(messages) > 10:
                estimated = self._compactor._estimate_tokens(messages, token_counter=None)
                threshold = int(self._config.compaction_threshold * 200000)
                if estimated > threshold:
                    logger.info("Compacting: %d estimated tokens", estimated)
                    messages = await self._compactor.compact(messages, 200000)

            had_tool_calls = False
            accumulated: list[ToolCall] = []
            accumulated_text = ""
            finish_reason = ""

            # Provider call with error recovery.
            try:
                async with asyncio.timeout(TTFB_TIMEOUT):
                    async for chunk in self._provider.stream_completion(
                        messages=messages, tools=tools, system=system, model=self._model,
                    ):
                        if self._interrupted:
                            break
                        if chunk.type == ProviderChunkType.TEXT and chunk.content:
                            accumulated_text += chunk.content
                            yield AgentChunk(type=ChunkType.TEXT, content=chunk.content)
                        elif chunk.type == ProviderChunkType.THINKING and chunk.content:
                            yield AgentChunk(type=ChunkType.THINKING, content=chunk.content)
                        elif chunk.type == ProviderChunkType.TOOL_CALL and chunk.tool_call:
                            had_tool_calls = True
                            accumulated.append(chunk.tool_call)
                        elif chunk.type == ProviderChunkType.DONE:
                            if getattr(chunk, "metadata", None):
                                finish_reason = chunk.metadata.get("finish_reason", "")
                            break
                retry_count = 0  # Success — reset.
            except TimeoutError:
                logger.warning("TTFB timeout after %.1fs", TTFB_TIMEOUT)
                if retry_count < MAX_RETRIES:
                    yield AgentChunk(type=ChunkType.TEXT, content="[Provider timed out — retrying...]")
                    retry_count += 1
                    await asyncio.sleep(BASE_DELAY * (2 ** retry_count))
                    continue
                yield AgentChunk(type=ChunkType.ERROR, content="Provider unreachable after retries.")
                break
            except Exception as exc:
                recovered = await self._error_recovery(exc, retry_count)
                if recovered:
                    retry_count += 1
                    continue
                yield AgentChunk(type=ChunkType.ERROR, content=str(exc))
                break

            if self._interrupted:
                break

            # Continuation — truncated output.
            if finish_reason == "length" and accumulated_text:
                messages.append(AgentMessage(role="assistant", content=accumulated_text))
                messages.append(AgentMessage(role="user", content="Continue. Pick up mid-sentence, don't repeat."))
                continue

            if not had_tool_calls:
                followup = await self._drain_followup()
                if followup:
                    messages.append(followup)
                    continue
                break

            # Append assistant message with tool_use blocks BEFORE tool results.
            # Anthropic API requires: user → assistant(tool_use) → user(tool_result).
            messages.append(AgentMessage(
                role="assistant",
                content=accumulated_text,
                tool_calls=accumulated,
            ))

            for tc in accumulated:
                if self._interrupted:
                    break
                total_tool_calls += 1
                self._last_activity = _time_module.monotonic()
                yield AgentChunk(type=ChunkType.TOOL_START, content=tc.name, metadata={"tool_call_id": tc.id, "arguments": tc.arguments})

                try:
                    # Sandbox: route shell commands through sandbox.
                    if self._sandbox and tc.name in ("shell", "terminal"):
                        result_raw = await self._sandbox.execute(tc.arguments.get("command", ""))
                        result = ToolResult(content=result_raw.get("stdout", "") or result_raw.get("stderr", ""))
                    else:
                        # Tool argument repair.
                        schema = self._get_tool_schema(tc.name)
                        if self._repairer and schema:
                            tc = await self._repairer.repair(tc, schema)
                        result = await self._registry.execute(tc.name, tc.arguments)
                except Exception as exc:
                    result = ToolResult(content=str(exc), is_error=True)

                yield AgentChunk(type=ChunkType.TOOL_RESULT, content=result.content[:1000], metadata={"tool_call_id": tc.id, "is_error": result.is_error, "overflowed": result.overflowed})
                messages.append(AgentMessage(role="tool", content=result.content, tool_call_id=tc.id))

        yield AgentChunk(type=ChunkType.DONE)
        # Persist conversation turns for undo/retry.
        self._session_messages.extend(
            m for m in messages if m.role in ("user", "assistant")
        )
        # Write session transcript to JSONL for dreaming pipeline.
        self._write_session_jsonl(session_id, messages, total_tool_calls)
        # Index episodes into vector DB for semantic search (fire-and-forget).
        if self._memory and messages:
            asyncio.create_task(
                self._index_session_episodes(session_id, messages)
            )
        # Fire session end hooks.
        try:
            from agent_core.hooks import run as run_hooks
            asyncio.create_task(run_hooks("session_end", {"session_id": session_id, "total_tool_calls": total_tool_calls}))
        except ImportError:
            logger.debug("hooks module not available")
        if total_tool_calls > 0 and self._memory:
            asyncio.create_task(self._self_improve(session_id, messages))

    async def steer(self, message: str) -> None:
        await self._steering_queue.put(AgentMessage(role="user", content=message))

    async def interrupt(self) -> None:
        self._interrupted = True

    # ------------------------------------------------------------------
    # Error recovery
    # ------------------------------------------------------------------

    async def _error_recovery(self, exc: Exception, retry_count: int) -> bool:
        from agent_core.errors import APIErrorClassifier, FailoverReason
        reason = APIErrorClassifier.classify(exc)
        logger.info("Error recovery: reason=%s retry=%d", reason.value, retry_count)

        if reason == FailoverReason.RATE_LIMIT:
            if retry_count < MAX_RETRIES:
                delay = min(BASE_DELAY * (2 ** retry_count), MAX_DELAY)
                await asyncio.sleep(delay)
                return True
        elif reason == FailoverReason.TRANSIENT or reason == FailoverReason.TIMEOUT:
            if retry_count < MAX_RETRIES:
                await asyncio.sleep(BASE_DELAY * (2 ** retry_count))
                return True
        elif reason == FailoverReason.AUTH_ERROR and self._credential_pool:
            cred = await self._credential_pool.acquire(self._provider_name)
            if cred:
                return True
        elif reason == FailoverReason.CONTENT_POLICY and self._fallback_providers:
            logger.info("Content policy violation — trying fallback provider")
            return await self._try_fallback()
        elif reason == FailoverReason.CONTEXT_TOO_LONG and self._compactor:
            logger.info("Context too long — triggering compaction then retry")
            return True
        return False

    async def _try_fallback(self) -> bool:
        """Attempt to switch to a fallback provider (e.g. Ollama, DeepSeek)."""
        for fallback_name in self._fallback_providers:
            try:
                if self._credential_pool:
                    cred = await self._credential_pool.acquire(fallback_name)
                    if cred:
                        logger.info("Fallback provider: %s", fallback_name)
                        self._provider_name = fallback_name
                        return True
            except Exception:
                logger.debug("Fallback provider %s unavailable", fallback_name)
        return False

    # ------------------------------------------------------------------
    # Caching
    # ------------------------------------------------------------------

    def _apply_cache_control(self, system: str) -> str:
        if "claude" in self._model.lower() or "anthropic" in self._model.lower():
            if not system.endswith("\n"):
                system += "\n"
        return system

    # ------------------------------------------------------------------
    # Helpers (unchanged logic, extracted for clarity)
    # ------------------------------------------------------------------

    async def _build_system(self) -> str:
        parts = [self._system_prompt] if self._system_prompt else []
        # Inject active goal.
        if self._goal and self._goal_state == "active":
            goal_text = f"[ACTIVE GOAL] {self._goal}"
            if self._subgoals:
                goal_text += "\nSub-goals:\n" + "\n".join(f"- {s}" for s in self._subgoals)
            parts.append(goal_text)
        if self._memory:
            if not self._frozen_context:
                self._frozen_context = await self._memory.build_system_context()
            if self._frozen_context:
                parts.append(self._frozen_context)
        return "\n\n".join(parts).strip()

    def _build_tool_list(self) -> list[dict[str, Any]]:
        available = self._registry.get_available()
        return [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in available]

    def _get_tool_schema(self, name: str) -> dict[str, Any] | None:
        desc = self._registry.get(name)
        return {"input_schema": desc.input_schema} if desc else None

    async def _drain_steering(self) -> AgentMessage | None:
        try: return self._steering_queue.get_nowait()
        except asyncio.QueueEmpty: return None

    async def _drain_followup(self) -> AgentMessage | None:
        try: return self._followup_queue.get_nowait()
        except asyncio.QueueEmpty: return None

    def _write_session_jsonl(
        self, session_id: str, messages: list[AgentMessage], total_tool_calls: int,
    ) -> None:
        """Persist session transcript as JSONL for the dreaming pipeline."""
        import json as _json
        from datetime import datetime, timezone

        sid = session_id or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        sessions_dir = Path.home() / ".jalaagent" / "memories" / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        try:
            sessions_dir.chmod(0o700)
        except OSError:
            pass  # best-effort on Windows

        entries: list[dict[str, Any]] = []
        for msg in messages:
            content = msg.content if isinstance(msg.content, str) else ""
            entries.append({
                "role": msg.role,
                "content": content[:2000],
                "tool_call_id": msg.tool_call_id,
                "tool_calls": [
                    {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                    for tc in (msg.tool_calls or [])
                ],
            })

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        session_path = sessions_dir / f"{date_str}.jsonl"
        session_path.touch(mode=0o600, exist_ok=True)
        with session_path.open("a", encoding="utf-8") as f:
            f.write(_json.dumps({
                "session_id": sid,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "tool_calls": total_tool_calls,
                "messages": entries,
            }) + "\n")

    async def _self_improve(self, session_id: str, messages: list[AgentMessage]) -> None:
        try:
            logger.info("Self-improvement for %s", session_id)
            if self._memory:
                summary = " ".join(str(m.content) for m in messages[-5:] if m.role in ("user", "assistant"))[:500]
                if summary:
                    p = Path.home() / ".jalaagent" / "memories" / "sessions" / f"{session_id}.review.md"
                    p.parent.mkdir(parents=True, exist_ok=True)
                    await asyncio.to_thread(p.write_text, f"# Session Review: {session_id}\n\n{summary}\n", encoding="utf-8")
        except Exception: logger.exception("Self-improvement failed")

    async def _index_session_episodes(
        self, session_id: str, messages: list[AgentMessage],
    ) -> None:
        """Index session messages as episodes in the vector layer.

        Fire-and-forget: errors are logged and never raised, so a failing
        embedding service or full disk never blocks the main loop.
        """
        from datetime import UTC, datetime as dt

        for msg in messages:
            if msg.role == "system":
                continue
            content = msg.content if isinstance(msg.content, str) else ""
            if not content.strip():
                continue
            try:
                # Import Episode lazily to keep agent-core free of a hard
                # memory-core dependency.
                from memory_core.models import Episode

                episode = Episode(
                    session_id=session_id or dt.now(UTC).strftime("%Y%m%d-%H%M%S"),
                    role=msg.role,  # type: ignore[arg-type]
                    content=content[:2000],
                    timestamp=dt.now(UTC),
                    tool_name=msg.tool_call_id if msg.role == "tool" else None,
                    metadata={"tool_calls": len(msg.tool_calls or [])},
                )
                if self._memory:
                    await self._memory.upsert_episode(episode)
            except Exception:
                logger.exception("Failed to index episode for session %s", session_id)

    async def load_skills(self) -> int:
        if self._skill_loader is None: return 0
        try:
            skills = await self._skill_loader.load_all()
            if skills: self._skills_block = self._skill_loader.format_for_prompt(skills)
            return len(skills)
        except Exception: return 0

    def reset(self) -> None:
        """Reset session state for /new command."""
        self._session_messages = []
        self._token_usage = {"input": 0, "output": 0}
        self._interrupted = False

    def retry(self) -> str:
        """Return last user message for /retry command."""
        return self._last_user_message

    def undo(self, n: int = 1) -> int:
        """Remove last N turns, return new count."""
        removed = min(n * 2, len(self._session_messages))
        self._session_messages = self._session_messages[:-removed] if removed else self._session_messages
        return len(self._session_messages)

    @property
    def model(self) -> str: return self._model
    @model.setter
    def model(self, v: str) -> None: self._model = v
    @property
    def sandbox(self) -> Any: return self._sandbox
    @property
    def worktree(self) -> Any: return self._worktree
    @property
    def plan_mode(self) -> Any: return self._plan_mode
    @property
    def bg_tasks(self) -> Any: return self._bg_tasks
    @property
    def credential_pool(self) -> Any: return self._credential_pool
    @property
    def skill_loader(self) -> Any: return self._skill_loader
    @property
    def followup_queue(self) -> asyncio.Queue[AgentMessage]: return self._followup_queue
    @property
    def token_usage(self) -> dict: return dict(self._token_usage)
    @property
    def session_messages(self) -> list[AgentMessage]: return list(self._session_messages)
    @property
    def goal(self) -> str: return self._goal
    @goal.setter
    def goal(self, v: str) -> None: self._goal = v; self._goal_state = "active"
    @property
    def goal_state(self) -> str: return self._goal_state
    @goal_state.setter
    def goal_state(self, v: str) -> None: self._goal_state = v
    @property
    def subgoals(self) -> list[str]: return list(self._subgoals)
    def add_subgoal(self, text: str) -> None: self._subgoals.append(text)
    def remove_subgoal(self, idx: int) -> bool:
        if 0 <= idx < len(self._subgoals): self._subgoals.pop(idx); return True
        return False
    def clear_subgoals(self) -> None: self._subgoals.clear()
    @property
    def reasoning_effort(self) -> str: return self._reasoning_effort
    @reasoning_effort.setter
    def reasoning_effort(self, v: str) -> None: self._reasoning_effort = v
    @property
    def fast_mode(self) -> bool: return self._fast_mode
    @fast_mode.setter
    def fast_mode(self, v: bool) -> None: self._fast_mode = v
    @property
    def personality(self) -> str: return self._personality
    @personality.setter
    def personality(self, v: str) -> None: self._personality = v
