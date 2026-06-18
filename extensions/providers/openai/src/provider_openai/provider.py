"""OpenAI / OpenAI-compatible provider — streaming via official SDK."""

import json as _json
import logging
import os
from collections.abc import AsyncGenerator
from typing import Any

from agent_core.models import (
    AgentMessage,
    ProviderChunk,
    ProviderChunkType,
    ToolCall,
)

logger = logging.getLogger(__name__)


class OpenAIProvider:
    """Provider for OpenAI and OpenAI-compatible API endpoints (GPT-4o, etc.)."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o",
        max_tokens: int = 8192,
    ) -> None:
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._model = model
        self._max_tokens = max_tokens
        self._client: Any = None

    @property
    def context_limit(self) -> int:
        return 128_000

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def stream_completion(
        self,
        messages: list[AgentMessage],
        tools: list[dict[str, Any]],
        system: str,
        model: str,
    ) -> AsyncGenerator[ProviderChunk, None]:
        client = self._get_client()
        model = model or self._model

        built = self._convert_messages(messages, system)
        converted_tools = self._convert_tools(tools) if tools else None

        try:
            stream = await client.chat.completions.create(
                model=model,
                messages=built,
                tools=converted_tools,
                max_tokens=self._max_tokens,
                stream=True,
            )
            async for event in stream:
                chunk = self._parse_event(event)
                if chunk:
                    yield chunk
        except Exception as exc:
            self._classify_and_raise(exc)

        yield ProviderChunk(type=ProviderChunkType.DONE)

    async def count_tokens(
        self, messages: list[AgentMessage], system: str = ""
    ) -> int:
        total = len(system)
        for msg in messages:
            if isinstance(msg.content, str):
                total += len(msg.content)
        return total // 4

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _convert_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for t in tools:
            result.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {}),
                },
            })
        return result

    @staticmethod
    def _convert_messages(
        messages: list[AgentMessage], system: str
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        if system:
            result.append({"role": "system", "content": system})
        for msg in messages:
            content = ""
            if isinstance(msg.content, str):
                content = msg.content
            elif isinstance(msg.content, list):
                content = " ".join(b.text for b in msg.content if b.text)
            entry: dict[str, Any] = {"role": msg.role, "content": content}
            if msg.tool_call_id:
                entry["tool_call_id"] = msg.tool_call_id
            if msg.tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": _json.dumps(tc.arguments)},
                    }
                    for tc in msg.tool_calls
                ]
            result.append(entry)
        return result

    @staticmethod
    def _parse_event(event: Any) -> ProviderChunk | None:
        choices = getattr(event, "choices", None)
        if not choices:
            return None
        choice = choices[0]
        delta = getattr(choice, "delta", None)
        if delta is None:
            return None

        if hasattr(delta, "content") and delta.content:
            return ProviderChunk(type=ProviderChunkType.TEXT, content=delta.content)

        tool_calls = getattr(delta, "tool_calls", None)
        if tool_calls:
            tc = tool_calls[0]
            fn = getattr(tc, "function", None)
            if fn:
                args = {}
                raw = getattr(fn, "arguments", "{}")
                if isinstance(raw, str):
                    try:
                        args = _json.loads(raw)
                    except _json.JSONDecodeError:
                        args = {}
                return ProviderChunk(
                    type=ProviderChunkType.TOOL_CALL,
                    tool_call=ToolCall(id=tc.id or "", name=fn.name or "", arguments=args),
                )
        return None

    @staticmethod
    def _classify_and_raise(exc: Exception) -> None:
        from agent_core.errors import (
            AuthError,
            ContentPolicyError,
            RateLimitError,
            TimeoutError,
            TransientError,
        )
        status = getattr(exc, "status_code", None)
        if status in (401, 403):
            raise AuthError(str(exc)) from exc
        if status == 429:
            raise RateLimitError(str(exc)) from exc
        if status == 400:
            raise ContentPolicyError(str(exc)) from exc
        if status and 500 <= status < 600:
            raise TransientError(str(exc)) from exc
        if "Timeout" in type(exc).__name__:
            raise TimeoutError(str(exc)) from exc
        raise TransientError(str(exc)) from exc

    def _get_client(self) -> Any:
        if self._client is None:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(api_key=self._api_key)
        return self._client
