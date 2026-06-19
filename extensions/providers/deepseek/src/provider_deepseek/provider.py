"""DeepSeek provider — OpenAI-compatible SDK."""

import logging
import os
from collections.abc import AsyncGenerator
from typing import Any

from agent_core.models import AgentMessage, ProviderChunk, ProviderChunkType

logger = logging.getLogger(__name__)


class DeepSeekProvider:
    """DeepSeek models (v3, r1) via OpenAI-compatible API."""

    def __init__(self, api_key: str | None = None, model: str = "deepseek-chat", max_tokens: int = 8192) -> None:
        self._api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        self._model = model
        self._max_tokens = max_tokens
        self._client: Any = None

    @property
    def context_limit(self) -> int:
        return 128_000

    async def stream_completion(self, messages: list[AgentMessage], tools: list[dict[str, Any]], system: str, model: str) -> AsyncGenerator[ProviderChunk, None]:
        from openai import AsyncOpenAI
        if self._client is None:
            self._client = AsyncOpenAI(api_key=self._api_key, base_url="https://api.deepseek.com/v1")
        model = model or self._model
        built = self._convert_messages(messages, system)
        try:
            stream = await self._client.chat.completions.create(model=model, messages=built, max_tokens=self._max_tokens, stream=True)
            async for event in stream:
                c = self._parse_event(event)
                if c:
                    yield c
        except Exception as exc:
            self._classify_and_raise(exc)
        yield ProviderChunk(type=ProviderChunkType.DONE)

    async def count_tokens(self, messages: list[AgentMessage], system: str = "") -> int:
        return (len(system) + sum(len(m.content) if isinstance(m.content, str) else 0 for m in messages)) // 4

    @staticmethod
    def _convert_messages(messages: list[AgentMessage], system: str) -> list[dict]:
        result: list[dict] = []
        if system:
            result.append({"role": "system", "content": system})
        for msg in messages:
            content = msg.content if isinstance(msg.content, str) else ""
            if isinstance(msg.content, list):
                content = " ".join(b.text for b in msg.content if b.text)
            entry: dict[str, Any] = {"role": msg.role, "content": content}
            if msg.tool_call_id:
                entry["tool_call_id"] = msg.tool_call_id
            result.append(entry)
        return result

    @staticmethod
    def _parse_event(event: Any) -> ProviderChunk | None:
        choices = getattr(event, "choices", None)
        if choices and choices[0].delta and hasattr(choices[0].delta, "content") and choices[0].delta.content:
            return ProviderChunk(type=ProviderChunkType.TEXT, content=choices[0].delta.content)
        return None

    @staticmethod
    def _classify_and_raise(exc: Exception) -> None:
        from agent_core.errors import AuthError, RateLimitError, TransientError
        status = getattr(exc, "status_code", None)
        if status in (401, 403): raise AuthError(str(exc)) from exc
        if status == 429: raise RateLimitError(str(exc)) from exc
        raise TransientError(str(exc)) from exc
