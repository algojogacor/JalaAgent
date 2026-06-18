"""Tests for OpenAI provider (message/tool conversion, token estimation)."""

import pytest
from provider_openai.provider import OpenAIProvider
from agent_core.models import AgentMessage, ToolCall


@pytest.fixture
def provider() -> OpenAIProvider:
    return OpenAIProvider(api_key="test-key")


class TestMessageConversion:
    def test_system_included(self, provider: OpenAIProvider) -> None:
        msgs = [AgentMessage(role="user", content="Hello")]
        result = provider._convert_messages(msgs, "You are helpful")
        assert result[0]["role"] == "system"
        assert result[1]["role"] == "user"

    def test_tool_call_included(self, provider: OpenAIProvider) -> None:
        tc = ToolCall(id="tc1", name="echo", arguments={"text": "hi"})
        msg = AgentMessage(role="assistant", content="", tool_calls=[tc])
        result = provider._convert_messages([msg], "")
        assert "tool_calls" in result[0]


class TestToolConversion:
    def test_openai_format(self, provider: OpenAIProvider) -> None:
        tools = [{"name": "echo", "description": "E", "input_schema": {}}]
        result = provider._convert_tools(tools)
        assert result[0]["type"] == "function"


@pytest.mark.asyncio
class TestTokenEstimation:
    async def test_count_tokens_fallback(self, provider: OpenAIProvider) -> None:
        msgs = [AgentMessage(role="user", content="a" * 400)]
        tokens = await provider.count_tokens(msgs, "")
        assert tokens == 100  # 400/4
