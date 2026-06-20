"""Provider model catalog — static curated lists, base_url defaults.

Three-layer sourcing:
1. Static bundled catalog (always available, offline fallback)
2. Live API fetch (GET /v1/models, disk-cached with 1h TTL)
3. User config override (config.yaml providers.<name>.models)

Context7 source: DashScope endpoints — https://dashscope.aliyuncs.com/compatible-mode/v1 (China)
and https://dashscope-intl.aliyuncs.com/compatible-mode/v1 (International).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_CACHE_DIR = Path.home() / ".jalaagent" / "cache"
_CACHE_FILE = _CACHE_DIR / "provider_models.json"
_DEFAULT_TTL_SECONDS = 3600  # 1 hour


PROVIDER_BASE_URLS: dict[str, str] = {
    # Tier 1: Major native
    "openai":     "https://api.openai.com/v1",
    "deepseek":   "https://api.deepseek.com/v1",
    "anthropic":  "https://api.anthropic.com",
    "google":     "https://generativelanguage.googleapis.com/v1beta",
    "gemini":     "https://generativelanguage.googleapis.com/v1beta",
    # Tier 2: OpenAI-compatible
    "qwen":       "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    "groq":       "https://api.groq.com/openai/v1",
    "mistral":    "https://api.mistral.ai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "together":   "https://api.together.xyz/v1",
    "perplexity": "https://api.perplexity.ai",
    "xai":        "https://api.x.ai/v1",
    "cohere":     "https://api.cohere.ai/v1",
    "fireworks":  "https://api.fireworks.ai/inference/v1",
    "cerebras":   "https://api.cerebras.ai/v1",
    "sambanova":  "https://api.sambanova.ai/v1",
    "nvidia":     "https://integrate.api.nvidia.com/v1",
    # Tier 3: Regional & specialized
    "alibaba":    "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "doubao":     "https://ark.cn-beijing.volces.com/api/v3",
    "kimi":       "https://api.moonshot.cn/v1",
    "minimax":    "https://api.minimax.chat/v1",
    "zai":        "https://api.z.ai/api/paas/v4",
    "jina":       "https://api.jina.ai/v1",
    "alibaba-coding": "https://coding-intl.dashscope.aliyuncs.com/v1",
    # Tier 4: Local
    "ollama":     "http://localhost:11434/v1",
    "ollama-cloud": "http://localhost:11434/v1",
}

PROVIDER_MODELS: dict[str, list[str]] = {
    "qwen": [
        "qwen-plus", "qwen-max", "qwen-turbo", "qwen-plus-latest",
        "qwen3-235b-a22b", "qwen2.5-72b-instruct", "qwen2.5-32b-instruct",
        "qwen2.5-14b-instruct", "qwen2.5-7b-instruct", "qwq-32b",
    ],
    "openai": [
        "gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini",
        "o4-mini", "o3-mini",
    ],
    "deepseek": ["deepseek-v4-flash-260425", "deepseek-v4-pro-260425", "deepseek-v3-2-251201", "deepseek-chat", "deepseek-reasoner"],
    "anthropic": [
        "claude-sonnet-4-6", "claude-opus-4-8", "claude-haiku-4-5",
    ],
    "ollama": ["qwen3:0.6b", "llama3.2", "mistral"],
    "openrouter": [
        "openai/gpt-4o", "anthropic/claude-sonnet-4-6",
        "google/gemini-2.5-pro", "deepseek/deepseek-v4-flash-260425",
        "meta-llama/llama-4-maverick", "qwen/qwen-plus",
    ],
    "groq": [
        "llama-3.3-70b-versatile", "mixtral-8x7b-32768",
        "gemma2-9b-it", "deepseek-r1-distill-llama-70b",
    ],
    "mistral": [
        "mistral-large-latest", "mistral-medium-latest",
        "mistral-small-latest", "codestral-latest",
    ],
    "together": [
        "meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo",
        "mistralai/Mixtral-8x22B-Instruct-v0.1",
    ],
    "perplexity": [
        "sonar-pro", "sonar", "sonar-reasoning-pro", "sonar-reasoning",
    ],
    "xai": ["grok-3", "grok-3-mini"],
    "cohere": ["command-r-plus", "command-r", "command"],
    "fireworks": ["accounts/fireworks/models/llama-v3p1-70b-instruct"],
    "cerebras": ["llama3.1-8b", "llama3.1-70b"],
    "sambanova": ["Meta-Llama-3.1-405B-Instruct"],
    "nvidia": ["meta/llama-3.1-405b-instruct"],
    "gemini": ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash"],
    "google": ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash"],
    "alibaba": ["qwen3.7-max", "qwen3.6-plus", "qwen3.6-flash"],
    "doubao": ["doubao-pro", "doubao-lite"],
    "kimi": ["kimi-k2.6", "moonshot-v1-128k"],
    "minimax": ["MiniMax-M3", "MiniMax-M2.7", "MiniMax-M2.5"],
    "zai": ["glm-4-plus", "glm-4-flash"],
    "jina": ["jina-embeddings-v3", "jina-reranker-v2"],
    "alibaba-coding": ["qwen3-coder-plus", "qwen3-coder-turbo"],
    "ollama-cloud": ["qwen3-coder:480b-cloud", "minimax-m3:cloud", "glm-4.7:cloud"],
}

BASE_URL_ENV_VARS: dict[str, str] = {
    "openai":     "OPENAI_BASE_URL",
    "deepseek":   "DEEPSEEK_BASE_URL",
    "anthropic":  "ANTHROPIC_BASE_URL",
    "google":     "GOOGLE_BASE_URL",
    "gemini":     "GEMINI_BASE_URL",
    "qwen":       "DASHSCOPE_BASE_URL",
    "groq":       "GROQ_BASE_URL",
    "mistral":    "MISTRAL_BASE_URL",
    "ollama":     "OLLAMA_BASE_URL",
    "openrouter": "OPENROUTER_BASE_URL",
    "together":   "TOGETHER_BASE_URL",
    "perplexity": "PERPLEXITY_BASE_URL",
    "xai":        "XAI_BASE_URL",
    "cohere":     "COHERE_BASE_URL",
    "fireworks":  "FIREWORKS_BASE_URL",
    "cerebras":   "CEREBRAS_BASE_URL",
    "sambanova":  "SAMBANOVA_BASE_URL",
    "nvidia":     "NVIDIA_BASE_URL",
    "alibaba":    "ALIBABA_BASE_URL",
    "doubao":     "DOUBAO_BASE_URL",
    "kimi":       "KIMI_BASE_URL",
    "minimax":    "MINIMAX_BASE_URL",
    "zai":        "ZAI_BASE_URL",
    "jina":       "JINA_BASE_URL",
    "alibaba-coding": "ALIBABA_CODING_BASE_URL",
    "ollama-cloud":   "OLLAMA_CLOUD_BASE_URL",
    "gemini":     "GEMINI_BASE_URL",
}


# ---------------------------------------------------------------------------
# Layer 2 + 3 — base_url resolution + model discovery
# ---------------------------------------------------------------------------


def resolve_base_url(
    provider: str,
    cli_base_url: str | None = None,
    config_providers: dict[str, Any] | None = None,
) -> str:
    """Resolve base_url for a provider through the 4-tier priority chain.

    Tier 1: CLI flag (--base-url)
    Tier 2: Env var (<PROVIDER>_BASE_URL)
    Tier 3: config.yaml providers.<name>.base_url
    Tier 4: Static default from PROVIDER_BASE_URLS
    """
    # Tier 1: CLI flag wins.
    if cli_base_url:
        return cli_base_url

    # Tier 2: Env var override.
    env_var = BASE_URL_ENV_VARS.get(provider)
    if env_var:
        env_val = os.environ.get(env_var, "")
        if env_val:
            return env_val

    # Tier 3: config.yaml.
    cfg = config_providers or {}
    cfg_url = cfg.get(provider, {}).get("base_url", "")
    if cfg_url:
        return cfg_url

    # Tier 4: Static default.
    if provider not in PROVIDER_BASE_URLS:
        raise KeyError(f"Unknown provider '{provider}'. Known: {list(PROVIDER_BASE_URLS)}")
    return PROVIDER_BASE_URLS[provider]


class ModelCatalog:
    """Provider model catalog with disk-cached live API fetch.

    Parameters
    ----------
    cache_ttl_seconds:
        How long disk cache entries are valid.  Default 3600 (1 hour).
    """

    def __init__(self, cache_ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> None:
        self._ttl = cache_ttl_seconds
        self._cache: dict[str, dict[str, Any]] = {}
        self._http: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_models(
        self,
        provider: str,
        base_url: str | None = None,
        api_key: str | None = None,
        force_refresh: bool = False,
    ) -> list[str]:
        """Return model list for *provider*, preferring live fetch with disk cache fallback.

        Synchronous wrapper — use ``aget_models()`` in async contexts.
        """
        if force_refresh:
            return self._fetch_and_cache_sync(provider, base_url, api_key)

        # 1. In-memory cache.
        cache_key = self._cache_key(provider, base_url or "", api_key or "")
        if cache_key in self._cache:
            entry = self._cache[cache_key]
            if not self._is_expired(entry):
                return entry["models"]

        # 2. Disk cache.
        disk_entry = self._read_disk_cache(cache_key)
        if disk_entry and not self._is_expired(disk_entry):
            self._cache[cache_key] = disk_entry
            return disk_entry["models"]

        # 3. Static fallback (live fetch happens in aget_models).
        return self._static_models(provider)

    async def aget_models(
        self,
        provider: str,
        base_url: str | None = None,
        api_key: str | None = None,
        force_refresh: bool = False,
    ) -> list[str]:
        """Async version: tries live API fetch, falls back to static."""
        resolved_url = base_url or PROVIDER_BASE_URLS.get(provider, "")
        if not resolved_url:
            return self._static_models(provider)

        cache_key = self._cache_key(provider, resolved_url, api_key or "")

        # Check caches first (unless forced refresh).
        if not force_refresh:
            if cache_key in self._cache:
                entry = self._cache[cache_key]
                if not self._is_expired(entry):
                    return entry["models"]
            disk_entry = self._read_disk_cache(cache_key)
            if disk_entry and not self._is_expired(disk_entry):
                self._cache[cache_key] = disk_entry
                return disk_entry["models"]

        # Live fetch.
        try:
            models = await self._fetch_live_models(resolved_url, api_key or "")
            if models:
                entry = {"models": models, "ts": time.time(), "provider": provider}
                self._cache[cache_key] = entry
                self._write_disk_cache(cache_key, entry)
                return models
        except Exception:
            logger.debug("Live fetch failed for %s, falling back to static", provider)

        return self._static_models(provider)

    def list_providers(self) -> list[str]:
        """Return all known provider slugs."""
        return sorted(PROVIDER_BASE_URLS.keys())

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _cache_key(self, provider: str, base_url: str, api_key: str) -> str:
        """Deterministic cache key based on provider + endpoint + credential fingerprint."""
        fingerprint = hashlib.sha256(
            f"{base_url}:{api_key[:8]}".encode()
        ).hexdigest()[:16]
        return f"{provider}:{fingerprint}"

    @staticmethod
    def _static_models(provider: str) -> list[str]:
        return PROVIDER_MODELS.get(provider, [])

    def _is_expired(self, entry: dict[str, Any]) -> bool:
        return (time.time() - entry.get("ts", 0)) > self._ttl

    async def _fetch_live_models(self, base_url: str, api_key: str) -> list[str] | None:
        """Probe GET /v1/models (OpenAI-compatible endpoint)."""
        http = self._get_http()
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        try:
            resp = await http.get(
                f"{base_url}/models",
                headers=headers,
                timeout=15.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                models: list[str] = []
                for m in data.get("data", []):
                    mid = m.get("id", "")
                    if mid:
                        models.append(mid)
                return models[:100]
        except Exception:
            pass
        return None

    def _fetch_and_cache_sync(
        self, provider: str, base_url: str | None, api_key: str | None
    ) -> list[str]:
        """Sync fallback for get_models(force_refresh=True) — returns cached or static."""
        cache_key = self._cache_key(provider, base_url or "", api_key or "")
        self._cache.pop(cache_key, None)
        self._remove_disk_cache(cache_key)
        return self._static_models(provider)

    # -- Disk cache helpers --

    def _read_disk_cache(self, cache_key: str) -> dict[str, Any] | None:
        try:
            if _CACHE_FILE.exists():
                data = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
                return data.get(cache_key)
        except Exception:
            pass
        return None

    def _write_disk_cache(self, cache_key: str, entry: dict[str, Any]) -> None:
        try:
            _CACHE_DIR.mkdir(parents=True, exist_ok=True)
            data: dict[str, Any] = {}
            if _CACHE_FILE.exists():
                data = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
            data[cache_key] = entry
            data = {k: v for k, v in data.items() if not self._is_expired(v)}
            _CACHE_FILE.write_text(json.dumps(data), encoding="utf-8")
        except Exception:
            logger.debug("Failed to write disk cache", exc_info=True)

    def _remove_disk_cache(self, cache_key: str) -> None:
        try:
            if _CACHE_FILE.exists():
                data = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
                data.pop(cache_key, None)
                _CACHE_FILE.write_text(json.dumps(data), encoding="utf-8")
        except Exception:
            pass

    def _get_http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=httpx.Timeout(15.0))
        return self._http

    async def close(self) -> None:
        if self._http:
            await self._http.aclose()
            self._http = None
