"""Tests for OpenRouter provider (message/tool conversion, token estimation)."""

import pytest
from provider_openrouter.provider import OpenRouterProvider
from agent_core.models import AgentMessage


@pytest.fixture
def provider() -> OpenRouterProvider:
    return OpenRouterProvider(api_key="test-key")


class TestMessageConversion:
    def test_system_included(self, provider: OpenRouterProvider) -> None:
        msgs = [AgentMessage(role="user", content="Hello")]
        result = provider._convert_messages(msgs, "System prompt")
        assert result[0]["role"] == "system"
        assert result[1]["role"] == "user"


class TestToolConversion:
    def test_openai_format(self, provider: OpenRouterProvider) -> None:
        tools = [{"name": "echo", "description": "E", "input_schema": {}}]
        result = provider._convert_tools(tools)
        assert result[0]["type"] == "function"


@pytest.mark.asyncio
class TestTokenEstimation:
    async def test_count_tokens_fallback(self, provider: OpenRouterProvider) -> None:
        msgs = [AgentMessage(role="user", content="a" * 400)]
        tokens = await provider.count_tokens(msgs, "")
        assert tokens == 100


class TestContextLimit:
    def test_limit(self, provider: OpenRouterProvider) -> None:
        assert provider.context_limit == 200_000
