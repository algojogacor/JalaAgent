"""Tests for Ollama provider (message/tool conversion, token estimation)."""

import pytest
from provider_ollama.provider import OllamaProvider
from agent_core.models import AgentMessage


@pytest.fixture
def provider() -> OllamaProvider:
    return OllamaProvider(base_url="http://localhost:11434", model="test-model")


class TestMessageConversion:
    def test_system_included(self, provider: OllamaProvider) -> None:
        msgs = [AgentMessage(role="user", content="Hello")]
        result = provider._convert_messages(msgs, "You are helpful")
        assert result[0]["role"] == "system"
        assert result[1]["role"] == "user"

    def test_no_system_when_empty(self, provider: OllamaProvider) -> None:
        msgs = [AgentMessage(role="user", content="Hi")]
        result = provider._convert_messages(msgs, "")
        assert result[0]["role"] == "user"


class TestToolConversion:
    def test_openai_format(self, provider: OllamaProvider) -> None:
        tools = [{"name": "echo", "description": "Echo", "input_schema": {"type": "object"}}]
        result = provider._convert_tools(tools)
        assert result[0]["type"] == "function"
        assert result[0]["function"]["name"] == "echo"


@pytest.mark.asyncio
class TestTokenEstimation:
    async def test_count_tokens_fallback(self, provider: OllamaProvider) -> None:
        # Without a running Ollama, falls back to char/4 estimate.
        msgs = [AgentMessage(role="user", content="a" * 40)]
        tokens = await provider.count_tokens(msgs, "sys")
        assert tokens >= 10  # rough estimate


class TestContextLimit:
    def test_default_limit(self, provider: OllamaProvider) -> None:
        assert provider.context_limit == 128_000
