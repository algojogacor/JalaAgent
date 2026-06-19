"""Dreaming pipeline runner — cron-based scheduling with manual trigger."""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from memory_core.dreaming import DreamingPipeline
from memory_core.file_layer import FileLayer
from memory_core.models import DreamReport, MemoryConfig
from memory_core.vector_layer import VectorLayer

logger = logging.getLogger(__name__)


class AutoApproveCallback:
    """Auto-approves all facts (YOLO/automated mode)."""

    async def request_approval(self, facts: list[Any]) -> list[str]:
        return [str(f.id) for f in facts]


class ProviderLLMAdapter:
    """Wraps the agent's provider as a DreamingLLMAdapter."""

    def __init__(self, provider: Any) -> None:
        self._provider = provider

    async def generate(self, prompt: str) -> str:
        from agent_core.models import AgentMessage
        messages = [AgentMessage(role="user", content=prompt)]
        result: list[str] = []
        async for chunk in self._provider.stream_completion(
            messages=messages, tools=[], system="", model="",
        ):
            if hasattr(chunk, "content") and chunk.content:
                result.append(chunk.content)
        return "".join(result)


class DreamingRunner:
    """Manages the dreaming pipeline lifecycle.

    - Schedules dreaming runs via cron-like sleep loop.
    - Supports manual triggering via `/dream` command.
    - Writes dream-diary.md after each run.
    - Respects agent idle state to avoid competing for LLM resources.
    """

    agent_is_idle: Any | None = None
    """Optional callable ``() -> bool`` — when set, dreaming only fires if idle."""

    def __init__(
        self,
        config: MemoryConfig,
        file_layer: FileLayer,
        vector_layer: VectorLayer,
        provider: Any | None = None,
    ) -> None:
        self._config = config
        self._file_layer = file_layer
        self._vector_layer = vector_layer
        self._provider = provider
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._last_run: datetime | None = None

    async def run_once(self) -> DreamReport:
        """Run the dreaming pipeline once and return the report."""
        llm = ProviderLLMAdapter(self._provider) if self._provider else None
        approval = AutoApproveCallback()

        pipeline = DreamingPipeline(
            config=self._config,
            file_layer=self._file_layer,
            vector_layer=self._vector_layer,
            llm=llm,  # type: ignore[arg-type]
            approval_callback=approval,  # type: ignore[arg-type]
        )

        report = await pipeline.run()
        self._last_run = datetime.now(UTC)
        logger.info(
            "Dreaming complete: %d signals, %d patterns, %d promoted",
            report.light_sleep_signals,
            report.rem_patterns,
            report.deep_sleep_promotions,
        )
        return report

    async def start_scheduler(self) -> None:
        """Start the cron-like scheduler loop."""
        if not self._config.dreaming_enabled:
            logger.info("Dreaming scheduler disabled")
            return
        self._running = True
        self._task = asyncio.create_task(self._schedule_loop())
        logger.info("Dreaming scheduler started (schedule=%s)", self._config.dreaming_schedule)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()

    async def _schedule_loop(self) -> None:
        while self._running:
            await asyncio.sleep(3600)  # Check every hour.
            if not self._running:
                break
            try:
                now = datetime.now(UTC)
                if now.hour == 3 and (self._last_run is None or self._last_run.date() < now.date()):
                    # Respect agent idle state — don't compete for LLM resources.
                    if self.agent_is_idle and not self.agent_is_idle():
                        logger.info("Skipping scheduled dreaming — agent is active")
                        continue
                    logger.info("Scheduled dreaming starting...")
                    await self.run_once()
            except Exception:
                logger.exception("Scheduled dreaming failed")

    @property
    def last_run(self) -> datetime | None:
        return self._last_run
