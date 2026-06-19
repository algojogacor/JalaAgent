"""Tests for agent-core context compaction."""

import pytest
from agent_core.compaction import ContextCompactor
from agent_core.models import AgentMessage


class TestShouldCompact:
    def test_false_for_short_messages(self) -> None:
        msgs = [AgentMessage(role="user", content="hi")]
        # 100K token context, 2 char message → way under 80%.
        assert not ContextCompactor.should_compact(msgs, 100_000)

    def test_true_when_over_threshold(self) -> None:
        # Build a message list that exceeds 80% of a small limit.
        msgs = [AgentMessage(role="user", content="x" * 10_000)]
        assert ContextCompactor.should_compact(msgs, 1000, threshold=0.8)


class TestDeduplicate:
    def test_removes_consecutive_duplicates(self) -> None:
        msgs = [
            AgentMessage(role="user", content="hello"),
            AgentMessage(role="user", content="hello"),
            AgentMessage(role="assistant", content="hi"),
        ]
        result = ContextCompactor._deduplicate(msgs)
        assert len(result) == 2

    def test_keeps_non_consecutive(self) -> None:
        msgs = [
            AgentMessage(role="user", content="hello"),
            AgentMessage(role="assistant", content="hi"),
            AgentMessage(role="user", content="hello"),
        ]
        result = ContextCompactor._deduplicate(msgs)
        assert len(result) == 3


class TestSplitProtected:
    def test_protects_recent(self) -> None:
        msgs = [
            AgentMessage(role="user", content="x" * 5000),
            AgentMessage(role="assistant", content="y" * 5000),
            AgentMessage(role="user", content="z" * 1000),
        ]
        protected, rest = ContextCompactor._split_protected(msgs)
        assert len(protected) >= 1
        assert protected[-1].content == "z" * 1000


@pytest.mark.asyncio
class TestCompact:
    async def test_returns_same_for_short(self) -> None:
        msgs = [AgentMessage(role="user", content="hi")]
        result = await ContextCompactor.compact(msgs, 100_000)
        assert len(result) == 1

    async def test_compresses_large(self) -> None:
        # Build many messages to force compaction.
        msgs = [
            AgentMessage(role="user", content="x" * 2000)
            for _ in range(50)
        ]
        result = await ContextCompactor.compact(msgs, 8000)
        # Should be shorter than original.
        assert len(result) < 50

    async def test_empty_messages(self) -> None:
        result = await ContextCompactor.compact([], 100_000)
        assert result == []


class TestEstimateTokens:
    def test_char_ratio(self) -> None:
        msgs = [AgentMessage(role="user", content="a" * 400)]
        tokens = ContextCompactor._estimate_tokens(msgs)
        assert tokens == 100  # 400 / 4
