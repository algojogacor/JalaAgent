"""Ollama (local models) provider — httpx-based with NDJSON streaming."""

import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from agent_core.models import (
    AgentMessage,
    ProviderChunk,
    ProviderChunkType,
    ToolCall,
)

logger = logging.getLogger(__name__)


class OllamaProvider:
    """Provider for local models via the Ollama HTTP API.

    Supports streaming chat completions, tool calling, and token counting
    via the native Ollama endpoints.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen3:0.6b",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._http: httpx.AsyncClient | None = None

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
        http = self._get_http()
        model = model or self._model

        payload: dict[str, Any] = {
            "model": model,
            "messages": self._convert_messages(messages, system),
            "stream": True,
        }
        if tools:
            payload["tools"] = self._convert_tools(tools)

        try:
            async with http.stream(
                "POST", f"{self._base_url}/api/chat", json=payload, timeout=120.0
            ) as resp:
                if resp.status_code != 200:
                    text = await resp.aread()
                    self._raise_for_status(resp.status_code, text.decode())
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    chunk = self._parse_chunk(data)
                    if chunk:
                        yield chunk
        except httpx.ConnectError as exc:
            from agent_core.errors import TransientError
            raise TransientError(
                f"Cannot connect to Ollama at {self._base_url}. Is it running?"
            ) from exc

        yield ProviderChunk(type=ProviderChunkType.DONE)

    async def count_tokens(
        self, messages: list[AgentMessage], system: str = ""
    ) -> int:
        http = self._get_http()
        all_text = system + " " + " ".join(
            msg.content if isinstance(msg.content, str) else "" for msg in messages
        )
        try:
            resp = await http.post(
                f"{self._base_url}/api/tokenize",
                json={"model": self._model, "text": all_text},
            )
            if resp.status_code == 200:
                data = resp.json()
                return len(data.get("tokens", []))
        except Exception:
            pass
        return len(all_text) // 4

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _convert_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for t in tools:
            converted: dict[str, Any] = {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {}),
                },
            }
            result.append(converted)
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
            result.append({"role": msg.role, "content": content,
                           **({"tool_call_id": msg.tool_call_id} if msg.tool_call_id else {})})
        return result

    @staticmethod
    def _parse_chunk(data: dict[str, Any]) -> ProviderChunk | None:
        msg = data.get("message", {})
        if "content" in msg and msg["content"]:
            return ProviderChunk(type=ProviderChunkType.TEXT, content=msg["content"])
        tool_calls = msg.get("tool_calls", [])
        for tc in tool_calls:
            fn = tc.get("function", {})
            return ProviderChunk(
                type=ProviderChunkType.TOOL_CALL,
                tool_call=ToolCall(
                    id=tc.get("id", ""),
                    name=fn.get("name", ""),
                    arguments=fn.get("arguments", {}),
                ),
            )
        return None

    @staticmethod
    def _raise_for_status(status: int, text: str) -> None:
        from agent_core.errors import AuthError, RateLimitError, TransientError

        if status == 429:
            raise RateLimitError(text)
        if status in (401, 403):
            raise AuthError(text)
        raise TransientError(f"Ollama error {status}: {text}")

    def _get_http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=httpx.Timeout(120.0))
        return self._http

    async def close(self) -> None:
        if self._http:
            await self._http.aclose()
            self._http = None
