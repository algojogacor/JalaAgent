"""Universal OpenAI-compatible provider — 16+ APIs via a single adapter.

Receives base_url from ProviderRouter (4-tier resolution). No embedded
provider catalog — all endpoint knowledge lives in agent_core.model_catalog.
"""

import json
import logging
import os
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import httpx
import yaml
from agent_core.credentials import CredentialPool
from agent_core.model_catalog import PROVIDER_BASE_URLS
from agent_core.models import AgentMessage, ProviderChunk, ProviderChunkType, ToolCall

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_PATH = Path.home() / ".jalaagent" / "config.yaml"
_DEFAULT_AUTH_PATH = Path.home() / ".jalaagent" / "auth.json"


class OpenAICompatibleProvider:
    """Single provider for all OpenAI-compatible APIs.

    base_url is resolved by ProviderRouter via the 4-tier priority chain
    (CLI flag → env var → config.yaml → static default). The provider
    itself is now a pure transport layer.
    """

    def __init__(
        self,
        config_path: Path | None = None,
        auth_path: Path | None = None,
        default_provider: str = "deepseek",
        default_model: str = "deepseek-chat",
        api_key: str = "",
        base_url: str = "",
        model: str = "",
    ) -> None:
        self._config_path = config_path or _DEFAULT_CONFIG_PATH
        self._auth_path = auth_path or _DEFAULT_AUTH_PATH
        self._default_provider = default_provider
        self._default_model = default_model
        self._base_url = base_url
        self._model = model
        self._http: httpx.AsyncClient | None = None

        # Load config + auth.
        self._config = self._load_config()
        self._auth = self._load_auth()
        self._pool = CredentialPool()
        self._load_keys_into_pool()
        self._last_usage: dict[str, int] = {}

    @property
    def context_limit(self) -> int:
        return 200_000

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------

    async def stream_completion(
        self,
        messages: list[AgentMessage],
        tools: list[dict[str, Any]],
        system: str,
        model: str,
    ) -> AsyncGenerator[ProviderChunk, None]:
        provider_name, model_name = self._resolve_model(model)
        base_url = self._get_base_url(provider_name)
        api_key = await self._pool.acquire(provider_name)
        key_str = api_key.key if api_key else ""
        headers = self._build_headers(provider_name, key_str)

        http = self._get_http()
        built = self._build_messages(messages, system)
        body: dict[str, Any] = {
            "model": model_name, "messages": built, "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            body["tools"] = self._convert_tools(tools)

        try:
            async with http.stream(
                "POST", f"{base_url}/chat/completions",
                json=body, headers=headers, timeout=120.0,
            ) as resp:
                if resp.status_code != 200:
                    text = await resp.aread()
                    self._raise_status(provider_name, resp.status_code, text.decode())
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    chunk = self._parse_chunk(data)
                    if chunk:
                        yield chunk
                if api_key:
                    await self._pool.report_success(provider_name, api_key)
                yield ProviderChunk(type=ProviderChunkType.DONE)
        except httpx.TimeoutException:
            from agent_core.errors import TimeoutError as JalaTimeout
            raise JalaTimeout(f"Provider {provider_name} timed out") from None
        except Exception as exc:
            if api_key:
                await self._pool.report_failure(provider_name, api_key, str(exc))
            self._classify_and_raise(exc)

    async def count_tokens(self, messages: list[AgentMessage], system: str = "") -> int:
        total = len(system)
        for m in messages:
            if isinstance(m.content, str):
                total += len(m.content)
        return total // 4

    # ------------------------------------------------------------------
    # Model routing
    # ------------------------------------------------------------------

    def _resolve_model(self, model: str) -> tuple[str, str]:
        """Resolve model string to (provider, model_name)."""
        model = model or self._model or f"{self._default_provider}/{self._default_model}"
        if "/" in model:
            prov, name = model.split("/", 1)
            return prov, name
        return self._default_provider, model

    def _get_base_url(self, provider: str) -> str:
        # Use constructor-provided base_url (from ProviderRouter) if available.
        if self._base_url:
            return self._base_url
        # Fallback: config.yaml providers.<name>.base_url.
        cfg = self._config.get("providers", {}).get(provider, {})
        return cfg.get("base_url", "") or PROVIDER_BASE_URLS.get(provider, "https://api.openai.com/v1")

    def _build_headers(self, provider: str, api_key: str) -> dict[str, str]:
        h = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        # config.yaml providers.<name>.extra_headers.
        cfg_extra = self._config.get("providers", {}).get(provider, {}).get("extra_headers", {})
        h.update(cfg_extra)
        return h

    # ------------------------------------------------------------------
    # Config + auth loading
    # ------------------------------------------------------------------

    def _load_config(self) -> dict[str, Any]:
        if self._config_path.exists():
            return yaml.safe_load(self._config_path.read_text(encoding="utf-8")) or {}
        return {}

    def _load_auth(self) -> dict[str, list[dict[str, Any]]]:
        if self._auth_path.exists():
            return json.loads(self._auth_path.read_text(encoding="utf-8"))
        # Fall back to env vars.
        result: dict[str, list[dict[str, Any]]] = {}
        _ENV_MAP: dict[str, str] = {
            "openai": "OPENAI_API_KEY", "deepseek": "DEEPSEEK_API_KEY",
            "openrouter": "OPENROUTER_API_KEY", "groq": "GROQ_API_KEY",
            "mistral": "MISTRAL_API_KEY", "qwen": "DASHSCOPE_API_KEY",
            "together": "TOGETHER_API_KEY", "perplexity": "PERPLEXITY_API_KEY",
            "xai": "XAI_API_KEY", "cohere": "COHERE_API_KEY",
            "fireworks": "FIREWORKS_API_KEY", "cerebras": "CEREBRAS_API_KEY",
        }
        for prov, env_var in _ENV_MAP.items():
            val = os.environ.get(env_var, "")
            if val:
                for key in val.split(","):
                    key = key.strip()
                    if key:
                        result.setdefault(prov, []).append(
                            {"key": key, "label": f"env:{env_var}", "priority": 1})
        return result

    def _load_keys_into_pool(self) -> None:
        # auth.json has a top-level "providers" key mapping provider → [keys].
        providers = self._auth.get("providers", {})
        if not providers:
            # Backward-compat: auth.json might be flat provider → [keys].
            providers = {k: v for k, v in self._auth.items() if isinstance(v, list)}
        for provider, keys in providers.items():
            for entry in keys:
                key = entry.get("key", "")
                if key:
                    self._pool.add(provider, key, {
                        "label": entry.get("label", ""),
                        "priority": entry.get("priority", 1),
                    })

    # ------------------------------------------------------------------
    # Message + tool conversion
    # ------------------------------------------------------------------

    @staticmethod
    def _build_messages(messages: list[AgentMessage], system: str) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        if system:
            result.append({"role": "system", "content": system})
        for msg in messages:
            content = msg.content if isinstance(msg.content, str) else ""
            if isinstance(msg.content, list):
                content = " ".join(b.text for b in msg.content if b.text)
            entry: dict[str, Any] = {"role": msg.role, "content": content}
            if msg.tool_call_id:
                entry["tool_call_id"] = msg.tool_call_id
            if msg.tool_calls:
                entry["tool_calls"] = [
                    {"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)}}
                    for tc in msg.tool_calls
                ]
            result.append(entry)
        return result

    @staticmethod
    def _convert_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {"type": "function", "function": {"name": t["name"], "description": t.get("description", ""), "parameters": t.get("input_schema", {})}}
            for t in tools
        ]

    @staticmethod
    def _parse_chunk(data: dict[str, Any]) -> ProviderChunk | None:
        choices = data.get("choices", [])
        if not choices:
            return None
        delta = choices[0].get("delta", {})
        if "content" in delta and delta["content"]:
            return ProviderChunk(type=ProviderChunkType.TEXT, content=delta["content"])
        if "reasoning_content" in delta and delta["reasoning_content"]:
            return ProviderChunk(type=ProviderChunkType.THINKING, content=delta["reasoning_content"])
        tool_calls = delta.get("tool_calls", [])
        for tc in tool_calls:
            fn = tc.get("function", {})
            args_raw = fn.get("arguments", "{}")
            try:
                args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
            except json.JSONDecodeError:
                args = {}
            return ProviderChunk(type=ProviderChunkType.TOOL_CALL, tool_call=ToolCall(id=tc.get("id", ""), name=fn.get("name", ""), arguments=args))
        return None

    @staticmethod
    def _raise_status(provider: str, status: int, text: str) -> None:
        from agent_core.errors import AuthError, ContentPolicyError, RateLimitError, TransientError
        if status in (401, 403): raise AuthError(f"{provider}: {text}")
        if status == 429: raise RateLimitError(f"{provider}: {text}")
        if status == 400: raise ContentPolicyError(f"{provider}: {text}")
        if 500 <= status < 600: raise TransientError(f"{provider}: {text}")
        raise TransientError(f"{provider} error {status}: {text}")

    @staticmethod
    def _classify_and_raise(exc: Exception) -> None:
        from agent_core.errors import AuthError, ContentPolicyError, RateLimitError, TransientError
        s = getattr(exc, "status_code", None)
        if s in (401, 403): raise AuthError(str(exc)) from exc
        if s == 429: raise RateLimitError(str(exc)) from exc
        if s == 400: raise ContentPolicyError(str(exc)) from exc
        if s and 500 <= s < 600: raise TransientError(str(exc)) from exc
        raise TransientError(str(exc)) from exc

    def _get_http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=httpx.Timeout(120.0))
        return self._http

    async def close(self) -> None:
        if self._http:
            await self._http.aclose()
            self._http = None
