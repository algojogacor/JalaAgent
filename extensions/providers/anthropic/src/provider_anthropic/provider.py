"""Anthropic (Claude) provider — streaming via official SDK."""

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

_MODEL_CONTEXT_LIMITS: dict[str, int] = {
    "claude-sonnet-4-6": 200_000,
    "claude-opus-4-6": 200_000,
    "claude-haiku-4-5": 200_000,
}


class AnthropicProvider:
    """Claude models via the official Anthropic Python SDK (AsyncAnthropic)."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 8192,
    ) -> None:
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._model = model
        self._max_tokens = max_tokens
        self._client: Any = None

    @property
    def context_limit(self) -> int:
        return _MODEL_CONTEXT_LIMITS.get(self._model, 200_000)

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

        system_parts = self.apply_cache_control(system) if system else []

        try:
            async with client.messages.stream(
                model=model,
                max_tokens=self._max_tokens,
                system=system_parts or None,
                messages=self._convert_messages(messages),
                tools=self._convert_tools(tools) if tools else None,
            ) as stream:
                async for event in stream:
                    chunk = self._parse_event(event)
                    if chunk:
                        yield chunk
            yield ProviderChunk(type=ProviderChunkType.DONE)
        except Exception as exc:
            self._classify_and_raise(exc)

    async def count_tokens(
        self, messages: list[AgentMessage], system: str = ""
    ) -> int:
        client = self._get_client()
        try:
            resp = await client.messages.count_tokens(
                model=self._model,
                messages=self._convert_messages(messages),
            )
            return resp.input_tokens
        except Exception:
            return self._estimate_tokens(messages, system)

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _convert_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for t in tools:
            converted: dict[str, Any] = {
                "name": t["name"],
                "description": t.get("description", ""),
            }
            schema = t.get("input_schema")
            if schema and isinstance(schema, dict):
                # Ensure valid JSON Schema — Anthropic requires at minimum
                # {"type": "object", "properties": {}}.
                if "type" not in schema:
                    schema = {"type": "object", "properties": schema}
                converted["input_schema"] = schema
            else:
                # Always provide a valid minimal schema.
                converted["input_schema"] = {"type": "object", "properties": {}}
            result.append(converted)
        return result

    @staticmethod
    def _convert_messages(messages: list[AgentMessage]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for msg in messages:
            if msg.role == "system":
                continue
            if msg.role == "tool":
                # Anthropic API requires tool_result blocks inside a user message.
                converted = {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": msg.tool_call_id or "",
                            "content": msg.content if isinstance(msg.content, str) else "",
                        }
                    ],
                }
            else:
                converted = {"role": msg.role}
                # Build content blocks — include tool_use blocks when present.
                blocks: list[dict[str, Any]] = []
                if isinstance(msg.content, str) and msg.content:
                    blocks.append({"type": "text", "text": msg.content})
                elif isinstance(msg.content, list):
                    for b in msg.content:
                        if b.text:
                            blocks.append({"type": "text", "text": b.text})
                # Attach tool_use blocks from tool_calls.
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        blocks.append({
                            "type": "tool_use",
                            "id": tc.id,
                            "name": tc.name,
                            "input": tc.arguments,
                        })
                converted["content"] = blocks if blocks else ""
            result.append(converted)
        return result

    @staticmethod
    def _parse_event(event: Any) -> ProviderChunk | None:
        etype = getattr(event, "type", None)
        if etype == "content_block_delta":
            delta = getattr(event, "delta", None)
            if delta and getattr(delta, "type", None) == "text_delta":
                return ProviderChunk(type=ProviderChunkType.TEXT, content=delta.text)
            if delta and getattr(delta, "type", None) == "thinking_delta":
                return ProviderChunk(type=ProviderChunkType.THINKING, content=delta.thinking)
        elif etype == "content_block_start":
            block = getattr(event, "content_block", None)
            if block and getattr(block, "type", None) == "tool_use":
                return ProviderChunk(
                    type=ProviderChunkType.TOOL_CALL,
                    tool_call=ToolCall(id=block.id, name=block.name, arguments=block.input or {}),
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

    @staticmethod
    def _estimate_tokens(messages: list[AgentMessage], system: str = "") -> int:
        total = len(system)
        for msg in messages:
            if isinstance(msg.content, str):
                total += len(msg.content)
        return total // 4

    def _get_client(self) -> Any:
        if self._client is None:
            from anthropic import AsyncAnthropic
            self._client = AsyncAnthropic(
                api_key=self._api_key,
                default_headers={
                    "anthropic-beta": "prompt-caching-2024-07-31",
                },
            )
        return self._client

    @staticmethod
    def apply_cache_control(system: str, max_tokens: int = 4) -> list[dict[str, Any]]:
        """Build Anthropic cache-control breakpoints for the system prompt.

        Places ephemeral cache markers on the first *max_tokens* tokens
        of each system content block, enabling Anthropic's prompt caching
        to keep the frozen system context warm between turns.
        """
        ttl_seconds = _get_cache_ttl()
        system_blocks: list[dict[str, Any]] = []
        if system:
            system_blocks = [{
                "type": "text", "text": system,
                "cache_control": {"type": "ephemeral"},
            }]
        return system_blocks


def _get_cache_ttl() -> int:
    """Read prompt_caching.cache_ttl from config, default 3600s (1h)."""
    try:
        from jala.config import load_config
        cfg = load_config()
        raw = cfg.get("prompt_caching", {}).get("cache_ttl", "60m")
        if isinstance(raw, str):
            if raw.endswith("m"):
                return int(raw[:-1]) * 60
            if raw.endswith("h"):
                return int(raw[:-1]) * 3600
            if raw.endswith("s"):
                return int(raw[:-1])
        return int(raw) if raw else 3600
    except Exception:
        return 3600
