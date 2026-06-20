"""Tests for Anthropic provider (message/tool conversion, token estimation)."""

import pytest
from agent_core.models import AgentMessage
from provider_anthropic.provider import AnthropicProvider


@pytest.fixture
def provider() -> AnthropicProvider:
    return AnthropicProvider(api_key="test-key")


class TestMessageConversion:
    def test_simple_user_message(self, provider: AnthropicProvider) -> None:
        msgs = [AgentMessage(role="user", content="Hello")]
        result = provider._convert_messages(msgs)
        assert result == [{"role": "user", "content": "Hello"}]

    def test_tool_message(self, provider: AnthropicProvider) -> None:
        msgs = [AgentMessage(role="tool", content="result", tool_call_id="tc1")]
        result = provider._convert_messages(msgs)
        assert result[0]["role"] == "user"
        assert result[0]["content"][0]["tool_use_id"] == "tc1"


class TestToolConversion:
    def test_converts_tools(self, provider: AnthropicProvider) -> None:
        tools = [{"name": "echo", "description": "Echo", "input_schema": {"type": "object"}}]
        result = provider._convert_tools(tools)
        assert result[0]["name"] == "echo"


class TestTokenEstimation:
    def test_estimate_tokens(self, provider: AnthropicProvider) -> None:
        msgs = [AgentMessage(role="user", content="a" * 400)]
        tokens = provider._estimate_tokens(msgs, "sys")
        assert tokens == 100  # (400 + 3) // 4


class TestContextLimit:
    def test_known_model(self, provider: AnthropicProvider) -> None:
        provider._model = "claude-sonnet-4-6"
        assert provider.context_limit == 200_000
