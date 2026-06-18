"""Google Gemini provider — streaming via google-genai SDK."""

import logging
import os
from collections.abc import AsyncGenerator
from typing import Any

from agent_core.models import AgentMessage, ProviderChunk, ProviderChunkType

logger = logging.getLogger(__name__)


class GeminiProvider:
    """Google Gemini models via the google-genai SDK."""

    def __init__(self, api_key: str | None = None, model: str = "gemini-2.5-flash", max_tokens: int = 8192) -> None:
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self._model = model
        self._max_tokens = max_tokens
        self._client: Any = None

    @property
    def context_limit(self) -> int:
        return 1_000_000

    async def stream_completion(self, messages: list[AgentMessage], tools: list[dict[str, Any]], system: str, model: str) -> AsyncGenerator[ProviderChunk, None]:
        from google import genai
        if self._client is None:
            self._client = genai.Client(api_key=self._api_key)
        model = model or self._model
        contents = self._convert_messages(messages, system)
        try:
            response = self._client.models.generate_content_stream(model=model, contents=contents)
            for chunk in response:
                if chunk.text:
                    yield ProviderChunk(type=ProviderChunkType.TEXT, content=chunk.text)
        except Exception as exc:
            self._classify_and_raise(exc)
        yield ProviderChunk(type=ProviderChunkType.DONE)

    async def count_tokens(self, messages: list[AgentMessage], system: str = "") -> int:
        total = len(system)
        for msg in messages:
            if isinstance(msg.content, str):
                total += len(msg.content)
        return total // 4

    @staticmethod
    def _convert_messages(messages: list[AgentMessage], system: str) -> list[Any]:
        from google.genai import types
        parts: list[Any] = []
        if system:
            parts.append(types.Part.from_text(text=f"[System] {system}"))
        for msg in messages:
            text = msg.content if isinstance(msg.content, str) else ""
            parts.append(types.Part.from_text(text=f"[{msg.role}] {text}"))
        return parts

    @staticmethod
    def _classify_and_raise(exc: Exception) -> None:
        from agent_core.errors import AuthError, ContentPolicyError, RateLimitError, TransientError
        msg = str(exc).lower()
        if "429" in msg or "quota" in msg or "rate" in msg:
            raise RateLimitError(str(exc)) from exc
        if "401" in msg or "403" in msg or "auth" in msg:
            raise AuthError(str(exc)) from exc
        if "safety" in msg or "blocked" in msg:
            raise ContentPolicyError(str(exc)) from exc
        raise TransientError(str(exc)) from exc
