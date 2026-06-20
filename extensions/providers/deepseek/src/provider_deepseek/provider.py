"""DeepSeek provider — OpenAI-compatible SDK."""

import json
import logging
import os
from collections.abc import AsyncGenerator
from typing import Any

from agent_core.models import AgentMessage, ProviderChunk, ProviderChunkType, ToolCall

logger = logging.getLogger(__name__)


class DeepSeekProvider:
    """DeepSeek models (v3, r1) via OpenAI-compatible API."""

    def __init__(self, api_key: str | None = None, model: str = "deepseek-v4-flash-260425", max_tokens: int = 8192) -> None:
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
            # Serialize tool_calls for assistant messages (OpenAI-compatible format).
            if msg.tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                    }
                    for tc in msg.tool_calls
                ]
            result.append(entry)
        return result

    @staticmethod
    def _parse_event(event: Any) -> ProviderChunk | None:
        choices = getattr(event, "choices", None)
        if choices and choices[0].delta:
            delta = choices[0].delta
            # Text content
            if getattr(delta, "content", None):
                return ProviderChunk(type=ProviderChunkType.TEXT, content=delta.content)
            # Tool call deltas
            tool_calls = getattr(delta, "tool_calls", None)
            if tool_calls:
                tc = tool_calls[0]
                fn = getattr(tc, "function", None)
                if fn:
                    args = {}
                    raw = getattr(fn, "arguments", "{}")
                    if isinstance(raw, str):
                        try:
                            args = json.loads(raw)
                        except json.JSONDecodeError:
                            args = {}
                    return ProviderChunk(
                        type=ProviderChunkType.TOOL_CALL,
                        tool_call=ToolCall(id=tc.id or "", name=fn.name or "", arguments=args),
                    )
        return None

    @staticmethod
    def _classify_and_raise(exc: Exception) -> None:
        from agent_core.errors import AuthError, RateLimitError, TransientError
        status = getattr(exc, "status_code", None)
        if status in (401, 403): raise AuthError(str(exc)) from exc
        if status == 429: raise RateLimitError(str(exc)) from exc
        raise TransientError(str(exc)) from exc
