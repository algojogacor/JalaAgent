"""Tests for agent-core conversation loop."""

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import pytest

from agent_core.loop import AgentLoop
from agent_core.models import (
    ActionCategory,
    AgentMessage,
    ChunkType,
    LoopConfig,
    ProviderChunk,
    ProviderChunkType,
    ToolCall,
    ToolDescriptor,
)
from agent_core.registry import ToolRegistry


# ---------------------------------------------------------------------------
# Mock provider
# ---------------------------------------------------------------------------


class MockProvider:
    """Simulates a streaming LLM provider."""

    def __init__(self, responses: list[list[ProviderChunk]]) -> None:
        self._responses = responses
        self._call_count = 0
        self.last_messages: list[AgentMessage] = []
        self.last_system: str = ""
        self.last_tools: list[dict] = []

    async def stream_completion(
        self,
        messages: list[AgentMessage],
        tools: list[dict[str, Any]],
        system: str,
        model: str,
    ) -> AsyncGenerator[ProviderChunk, None]:
        self.last_messages = messages
        self.last_system = system
        self.last_tools = tools

        idx = min(self._call_count, len(self._responses) - 1)
        self._call_count += 1

        for chunk in self._responses[idx]:
            yield chunk


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(
        ToolDescriptor(
            name="echo",
            description="Echo back the input",
            category=ActionCategory.FILE_READ,
        ),
        handler=lambda args: f"echo: {args.get('text', '')}",
    )
    return reg


def make_text_chunk(text: str) -> ProviderChunk:
    return ProviderChunk(type=ProviderChunkType.TEXT, content=text)


def make_tool_chunk(name: str, args: dict, tc_id: str = "tc1") -> ProviderChunk:
    return ProviderChunk(
        type=ProviderChunkType.TOOL_CALL,
        tool_call=ToolCall(id=tc_id, name=name, arguments=args),
    )


DONE = ProviderChunk(type=ProviderChunkType.DONE)


# ---------------------------------------------------------------------------
# Loop tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAgentLoop:
    async def test_text_only_response(self, registry: ToolRegistry) -> None:
        provider = MockProvider([
            [make_text_chunk("Hello, "), make_text_chunk("world!"), DONE],
        ])
        loop = AgentLoop(provider=provider, registry=registry)

        chunks = []
        async for chunk in loop.run("test message"):
            chunks.append(chunk)

        texts = [c.content for c in chunks if c.type == ChunkType.TEXT]
        assert "Hello, " in texts
        assert "world!" in texts
        assert any(c.type == ChunkType.DONE for c in chunks)

    async def test_tool_call_execution(self, registry: ToolRegistry) -> None:
        provider = MockProvider([
            [
                make_text_chunk("Let me check..."),
                make_tool_chunk("echo", {"text": "hello world"}),
                DONE,
            ],
            [make_text_chunk("I got: hello world"), DONE],
        ])
        loop = AgentLoop(provider=provider, registry=registry)

        chunks = []
        async for chunk in loop.run("echo test"):
            chunks.append(chunk)

        types = {c.type for c in chunks}
        assert ChunkType.TOOL_START in types
        assert ChunkType.TOOL_RESULT in types
        assert ChunkType.DONE in types

    async def test_max_iterations(self, registry: ToolRegistry) -> None:
        """Agent stops after max_iterations even with tool calls."""
        provider = MockProvider([
            # Always return a tool call to force another iteration.
            [make_tool_chunk("echo", {"text": "loop"}), DONE],
        ] * 10)  # way more than max_iterations
        config = LoopConfig(max_iterations=3)
        loop = AgentLoop(provider=provider, registry=registry, config=config)

        chunks = []
        async for chunk in loop.run("loop test"):
            chunks.append(chunk)

        tool_starts = [c for c in chunks if c.type == ChunkType.TOOL_START]
        assert len(tool_starts) <= 3

    async def test_interrupt(self, registry: ToolRegistry) -> None:
        provider = MockProvider([
            [make_text_chunk("Starting...")],
        ])
        loop = AgentLoop(provider=provider, registry=registry)

        chunks = []
        async for chunk in loop.run("interrupt me"):
            chunks.append(chunk)
            await loop.interrupt()

        # Should stop after interrupt.
        assert any(c.type == ChunkType.DONE for c in chunks)

    async def test_steer_injects_mid_run(self, registry: ToolRegistry) -> None:
        provider = MockProvider([
            [make_tool_chunk("echo", {"text": "first"}), DONE],
            [make_text_chunk("After steer."), DONE],
        ])
        loop = AgentLoop(provider=provider, registry=registry)

        chunks = []
        async for chunk in loop.run("initial"):
            chunks.append(chunk)
            if chunk.type == ChunkType.TOOL_RESULT:
                await loop.steer("New instruction mid-run")

        texts = [c.content for c in chunks if c.type == ChunkType.TEXT]
        assert any("After steer" in (t or "") for t in texts)
