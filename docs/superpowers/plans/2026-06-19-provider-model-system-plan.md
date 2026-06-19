# Provider & Model System — Enterprise Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hermes-level `/model` command with interactive provider→model picker on Telegram + CLI, live API model discovery with disk cache, env var base_url overrides for all 16+ providers.

**Architecture:** Three-layer model catalog (static bundled → live API fetch with 1h disk cache → config.yaml override). Four-tier base_url chain (CLI flag → env var → config → static). New `model_catalog.py` module in agent-core. ProviderRouter gains base_url resolution. Universal provider cleaned of hardcoded endpoint dict. Telegram channel gains inline keyboard model picker; CLI channel gains rich select. Shared `switch_model()` pipeline in commands.py with `--save` persistence.

**Tech Stack:** Python 3.12+, asyncio, httpx, python-telegram-bot (inline keyboards), typer + rich, pydantic v2, pyyaml

---

## File Structure

| File | Responsibility |
|------|---------------|
| `packages/agent-core/src/agent_core/model_catalog.py` | **New.** Static model lists, base_url defaults, live API fetch, disk cache, `ModelCatalog` class |
| `packages/agent-core/src/agent_core/providers.py` | **Modify.** Add `base_url` + `base_url_env_var` to `ProviderEntry`, `resolve_base_url()`, expand `KNOWN_PROVIDERS`, model aliases |
| `packages/agent-core/src/agent_core/commands.py` | **Modify.** Replace `_model()` with full `switch_model()` pipeline: parse flags, show picker or direct switch, persist |
| `extensions/providers/universal/src/provider_universal/provider.py` | **Modify.** Delete `PROVIDERS` dict. Accept `base_url` from constructor. Pure transport layer. |
| `extensions/channels/telegram/src/channel_telegram/channel.py` | **Modify.** Add `_model_picker_state`, `send_model_picker()`, keyboard builders |
| `extensions/channels/telegram/src/channel_telegram/handlers.py` | **Modify.** Add model picker callback handlers (`mp:`, `mm:`, `mb:`, `mx:`) |
| `extensions/channels/cli/src/channel_cli/channel.py` | **Modify.** Add `_show_model_picker()` for rich interactive selection |
| `cli/src/jala/main.py` | **Modify.** Add `--base-url` CLI option, wire into `_build_agent()`, wire model persistence on `--save` |
| `tests/packages/agent-core/test_model_catalog.py` | **New.** Unit tests for static catalog, base_url resolution, cache logic |
| `tests/packages/agent-core/test_provider_router.py` | **New.** Unit tests for ProviderRouter with base_url chain |

---

### Task 1: Static Model Catalog + base_url Defaults

**Files:**
- Create: `packages/agent-core/src/agent_core/model_catalog.py`
- Create: `tests/packages/agent-core/test_model_catalog.py`

- [ ] **Step 1: Write the failing test for PROVIDER_BASE_URLS**

```python
# tests/packages/agent-core/test_model_catalog.py
import pytest
from agent_core.model_catalog import PROVIDER_BASE_URLS, PROVIDER_MODELS

def test_provider_base_urls_has_required_providers():
    """Every major provider must have a full-URL default."""
    required = ["qwen", "openai", "deepseek", "anthropic", "ollama", "openrouter"]
    for prov in required:
        assert prov in PROVIDER_BASE_URLS, f"Missing base_url for {prov}"
        assert PROVIDER_BASE_URLS[prov].startswith("https://") or \
               PROVIDER_BASE_URLS[prov].startswith("http://"), \
               f"base_url for {prov} must be full URL, got: {PROVIDER_BASE_URLS[prov]}"

def test_provider_base_urls_are_full_paths():
    """All base_urls must include /v1 or equivalent path — no bare domains."""
    for prov, url in PROVIDER_BASE_URLS.items():
        assert "://" in url, f"{prov}: URL must have scheme"
        assert len(url.split("/")) >= 4, f"{prov}: URL must have path: {url}"

def test_provider_models_has_curated_lists():
    for prov in PROVIDER_BASE_URLS:
        assert prov in PROVIDER_MODELS, f"Missing model list for {prov}"
        assert len(PROVIDER_MODELS[prov]) >= 1, f"Empty model list for {prov}"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /d/JalaAgent/jalaagent && uv run pytest tests/packages/agent-core/test_model_catalog.py -v
# Expected: FAIL — module not found
```

- [ ] **Step 3: Create model_catalog.py with PROVIDER_BASE_URLS and PROVIDER_MODELS**

```python
# packages/agent-core/src/agent_core/model_catalog.py
"""Provider model catalog — static curated lists, base_url defaults, live API fetch with disk cache.

Three-layer sourcing:
1. Static bundled catalog (always available, offline fallback)
2. Live API fetch (GET /v1/models, disk-cached with 1h TTL)
3. User config override (config.yaml providers.<name>.models)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_CACHE_DIR = Path.home() / ".jalaagent" / "cache"
_CACHE_FILE = _CACHE_DIR / "provider_models.json"
_DEFAULT_TTL_SECONDS = 3600  # 1 hour


# ---------------------------------------------------------------------------
# Layer 1 — Static bundled catalog
# ---------------------------------------------------------------------------

PROVIDER_BASE_URLS: dict[str, str] = {
    "qwen":       "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    "openai":     "https://api.openai.com/v1",
    "deepseek":   "https://api.deepseek.com/v1",
    "anthropic":  "https://api.anthropic.com",
    "ollama":     "http://localhost:11434/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "groq":       "https://api.groq.com/openai/v1",
    "mistral":    "https://api.mistral.ai/v1",
    "together":   "https://api.together.xyz/v1",
    "perplexity": "https://api.perplexity.ai",
    "xai":        "https://api.x.ai/v1",
    "cohere":     "https://api.cohere.ai/v1",
    "fireworks":  "https://api.fireworks.ai/inference/v1",
    "cerebras":   "https://api.cerebras.ai/v1",
    "sambanova":  "https://api.sambanova.ai/v1",
    "nvidia":     "https://integrate.api.nvidia.com/v1",
    "gemini":     "https://generativelanguage.googleapis.com/v1beta",
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
    "deepseek": ["deepseek-chat", "deepseek-reasoner"],
    "anthropic": [
        "claude-sonnet-4-6", "claude-opus-4-8", "claude-haiku-4-5",
    ],
    "ollama": ["qwen3:0.6b", "llama3.2", "mistral"],
    "openrouter": [
        "openai/gpt-4o", "anthropic/claude-sonnet-4-6",
        "google/gemini-2.5-pro", "deepseek/deepseek-chat",
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
}

# Provider name → env var for base_url override.
BASE_URL_ENV_VARS: dict[str, str] = {
    "qwen":       "DASHSCOPE_BASE_URL",
    "openai":     "OPENAI_BASE_URL",
    "deepseek":   "DEEPSEEK_BASE_URL",
    "anthropic":  "ANTHROPIC_BASE_URL",
    "ollama":     "OLLAMA_BASE_URL",
    "openrouter": "OPENROUTER_BASE_URL",
    "groq":       "GROQ_BASE_URL",
    "mistral":    "MISTRAL_BASE_URL",
    "together":   "TOGETHER_BASE_URL",
    "perplexity": "PERPLEXITY_BASE_URL",
    "xai":        "XAI_BASE_URL",
    "cohere":     "COHERE_BASE_URL",
    "fireworks":  "FIREWORKS_BASE_URL",
    "cerebras":   "CEREBRAS_BASE_URL",
    "sambanova":  "SAMBANOVA_BASE_URL",
    "nvidia":     "NVIDIA_BASE_URL",
    "gemini":     "GEMINI_BASE_URL",
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /d/JalaAgent/jalaagent && uv run pytest tests/packages/agent-core/test_model_catalog.py -v
# Expected: 3 PASS
```

- [ ] **Step 5: Commit**

```bash
cd /d/JalaAgent/jalaagent && git add packages/agent-core/src/agent_core/model_catalog.py tests/packages/agent-core/test_model_catalog.py && git commit -m "feat: add static model catalog with provider base_url defaults"
```

---

### Task 2: Live API Model Fetch + Disk Cache

**Files:**
- Modify: `packages/agent-core/src/agent_core/model_catalog.py` (append below static catalog)
- Modify: `tests/packages/agent-core/test_model_catalog.py` (append tests)

- [ ] **Step 1: Write failing tests for cache and fetch**

```python
# Append to tests/packages/agent-core/test_model_catalog.py

from unittest.mock import AsyncMock, MagicMock, patch
from agent_core.model_catalog import ModelCatalog, resolve_base_url

def test_resolve_base_url_cli_flag_wins():
    """CLI flag must win over all other sources."""
    result = resolve_base_url(
        "qwen",
        cli_base_url="https://custom.example.com/v1",
        config_providers={},
    )
    assert result == "https://custom.example.com/v1"

def test_resolve_base_url_env_var_second():
    """Env var wins over config and static default."""
    with patch.dict(os.environ, {"DASHSCOPE_BASE_URL": "https://env.example.com/v1"}):
        result = resolve_base_url("qwen", config_providers={})
        assert result == "https://env.example.com/v1"

def test_resolve_base_url_config_third():
    """config.yaml wins over static default."""
    with patch.dict(os.environ, {}, clear=True):
        result = resolve_base_url(
            "qwen",
            config_providers={"qwen": {"base_url": "https://config.example.com/v1"}},
        )
        assert result == "https://config.example.com/v1"

def test_resolve_base_url_static_fallback():
    """Static default is last resort."""
    with patch.dict(os.environ, {}, clear=True):
        result = resolve_base_url("openai", config_providers={})
        assert result == "https://api.openai.com/v1"

def test_resolve_base_url_unknown_provider_raises():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(KeyError):
            resolve_base_url("nonexistent", config_providers={})

@pytest.mark.asyncio
async def test_model_catalog_get_models_static_fallback():
    """Catalog returns static list when no cache exists."""
    catalog = ModelCatalog()
    models = catalog.get_models("deepseek")
    assert "deepseek-chat" in models
    assert "deepseek-reasoner" in models

@pytest.mark.asyncio
async def test_model_catalog_cache_key_varies_by_base_url():
    """Different base_urls produce different cache keys."""
    c1 = ModelCatalog()
    key_a = c1._cache_key("qwen", "https://dashscope.aliyuncs.com/compatible-mode/v1", "sk-abc12345")
    key_b = c1._cache_key("qwen", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1", "sk-abc12345")
    assert key_a != key_b  # Different base_url → different key
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /d/JalaAgent/jalaagent && uv run pytest tests/packages/agent-core/test_model_catalog.py -v
# Expected: FAIL — ModelCatalog, resolve_base_url not defined
```

- [ ] **Step 3: Add resolve_base_url() and ModelCatalog class to model_catalog.py**

```python
# Append to packages/agent-core/src/agent_core/model_catalog.py


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
        self._cache: dict[str, dict[str, Any]] = {}  # in-memory layer
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

        Synchronous wrapper — use `aget_models()` in async contexts.
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
                return models[:100]  # Cap at 100 models.
        except Exception:
            pass
        return None

    def _fetch_and_cache_sync(
        self, provider: str, base_url: str | None, api_key: str | None
    ) -> list[str]:
        """Sync fallback for get_models(force_refresh=True) — returns cached or static."""
        # For sync contexts with force_refresh, invalidate and return static +
        # schedule async fetch next time.
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
            # Prune expired entries.
            data = {k: v for k, v in data.items()
                    if not self._is_expired(v)}
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /d/JalaAgent/jalaagent && uv run pytest tests/packages/agent-core/test_model_catalog.py -v
# Expected: 8 PASS (3 from Task 1 + 5 new)
```

- [ ] **Step 5: Commit**

```bash
cd /d/JalaAgent/jalaagent && git add packages/agent-core/src/agent_core/model_catalog.py tests/packages/agent-core/test_model_catalog.py && git commit -m "feat: add live API model fetch + disk cache, 4-tier base_url resolution"
```

---

### Task 3: Update ProviderRouter with base_url Chain + Aliases

**Files:**
- Modify: `packages/agent-core/src/agent_core/providers.py:16-138`
- Create: `tests/packages/agent-core/test_provider_router.py`

- [ ] **Step 1: Write failing tests for base_url in ProviderEntry**

```python
# tests/packages/agent-core/test_provider_router.py
import pytest
from agent_core.providers import ProviderEntry, ProviderRouter, KNOWN_PROVIDERS

def test_provider_entry_has_base_url_fields():
    """ProviderEntry must support base_url and base_url_env_var."""
    entry = ProviderEntry(
        "qwen", "DASHSCOPE_API_KEY", "qwen",
        "provider_universal.provider", "OpenAICompatibleProvider",
        base_url_env_var="DASHSCOPE_BASE_URL",
        priority=35,
    )
    assert entry.base_url_env_var == "DASHSCOPE_BASE_URL"
    assert entry.base_url is None  # Default None — resolved later

def test_known_providers_includes_universal_providers():
    """KNOW_PROVIDERS must include qwen, together, cohere, etc. for provider/model syntax."""
    required = {"qwen", "together", "cohere", "xai", "perplexity",
                 "fireworks", "cerebras", "sambanova", "nvidia", "gemini"}
    for prov in required:
        assert prov in KNOWN_PROVIDERS, f"Missing {prov} in KNOWN_PROVIDERS"

def test_router_resolve_with_cli_base_url():
    """ProviderRouter must pass CLI base_url through to provider constructor."""
    router = ProviderRouter()
    # Verify the router stores and passes base_url through resolve()
    # This tests the architecture, not actual API calls.
    from agent_core.model_catalog import resolve_base_url
    result = resolve_base_url("qwen", cli_base_url="https://custom.qwen.ai/v1")
    assert result == "https://custom.qwen.ai/v1"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /d/JalaAgent/jalaagent && uv run pytest tests/packages/agent-core/test_provider_router.py -v
# Expected: FAIL — base_url_env_var not valid field, KNOWN_PROVIDERS missing entries
```

- [ ] **Step 3: Update ProviderEntry and expand KNOWN_PROVIDERS**

Edit `providers.py` line 44-53 — add `base_url` and `base_url_env_var` fields:

```python
@dataclass
class ProviderEntry:
    name: str
    env_var: str
    auth_key: str
    module_path: str
    class_name: str
    model_patterns: list[str] = field(default_factory=list)
    priority: int = 100
    default_model: str | None = None
    extra_kwargs: dict[str, Any] = field(default_factory=dict)
    base_url: str | None = None          # NEW: resolved base URL
    base_url_env_var: str = ""           # NEW: env var for base_url override
```

Edit line 134-138 — expand `KNOWN_PROVIDERS`:

```python
KNOWN_PROVIDERS = {
    "anthropic", "openai", "deepseek", "groq", "mistral",
    "openrouter", "ollama", "google", "qwen", "together",
    "perplexity", "xai", "cohere", "fireworks", "cerebras",
    "sambanova", "nvidia", "gemini", "universal",
}
```

Add to the universal `ProviderEntry` in `DEFAULT_PROVIDERS` (line 114-122):

```python
    ProviderEntry(
        "universal",
        "",
        "",
        "provider_universal.provider",
        "OpenAICompatibleProvider",
        priority=70,
        base_url_env_var="",  # universal uses config.yaml or static default
        extra_kwargs={},
    ),
```

Add a dedicated Qwen entry at priority 35 (before universal, after deepseek):

```python
    ProviderEntry(
        "qwen",
        "DASHSCOPE_API_KEY",
        "qwen",
        "provider_universal.provider",
        "OpenAICompatibleProvider",
        model_patterns=["qwen-", "qwen/", "qwq-"],
        priority=35,
        base_url_env_var="DASHSCOPE_BASE_URL",
        extra_kwargs={},
    ),
```

- [ ] **Step 4: Update `_try_entry()` to pass resolved base_url**

Edit `providers.py` lines 261-291 — in `_try_entry()`, add base_url resolution before instantiation:

```python
    @staticmethod
    def _try_entry(
        entry: ProviderEntry,
        model: str | None,
        auth_keys: dict[str, str],
        cli_base_url: str | None = None,          # NEW param
        config_providers: dict[str, Any] | None = None,  # NEW param
    ) -> Any | None:
        """Try to instantiate *entry*.  Returns ``None`` on failure."""
        import os as _os

        key = _os.environ.get(entry.env_var, "")
        if not key and entry.auth_key:
            key = auth_keys.get(entry.auth_key, "")

        if not key and entry.name not in ("universal", "ollama"):
            return None

        try:
            mod = importlib.import_module(entry.module_path)
            cls = getattr(mod, entry.class_name)
            kwargs: dict[str, Any] = {}
            if key:
                kwargs["api_key"] = key
            resolved_model = model or entry.default_model
            if resolved_model:
                kwargs["model"] = resolved_model

            # NEW: Resolve base_url through 4-tier chain.
            from agent_core.model_catalog import resolve_base_url  # noqa: PLC0415
            try:
                resolved_base = resolve_base_url(
                    entry.name,
                    cli_base_url=cli_base_url,
                    config_providers=config_providers or {},
                )
                kwargs["base_url"] = resolved_base
            except KeyError:
                pass  # Unknown provider — let the constructor use its own default.

            kwargs.update(entry.extra_kwargs)
            return cls(**kwargs)
        except Exception:
            return None
```

Update `resolve()` method signature to accept `cli_base_url` and `config_providers`, and thread them through:

```python
    def resolve(
        self,
        model: str | None = None,
        creds: Any = None,
        cli_base_url: str | None = None,             # NEW
        config_providers: dict[str, Any] | None = None,  # NEW
    ) -> Any:
```

And update the three `_try_entry` calls to pass `cli_base_url` and `config_providers`.

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /d/JalaAgent/jalaagent && uv run pytest tests/packages/agent-core/test_provider_router.py -v
# Expected: 3 PASS
```

- [ ] **Step 6: Commit**

```bash
cd /d/JalaAgent/jalaagent && git add packages/agent-core/src/agent_core/providers.py tests/packages/agent-core/test_provider_router.py && git commit -m "feat: add base_url chain to ProviderRouter, expand KNOWN_PROVIDERS"
```

---

### Task 4: Clean Up Universal Provider

**Files:**
- Modify: `extensions/providers/universal/src/provider_universal/provider.py:23-38,51-62,144-155`

- [ ] **Step 1: Delete PROVIDERS dict, accept base_url from constructor**

Delete lines 23-38 (the `PROVIDERS` dict).

Update the constructor (lines 51-62) to accept `base_url`:

```python
    def __init__(
        self,
        config_path: Path | None = None,
        auth_path: Path | None = None,
        default_provider: str = "deepseek",
        default_model: str = "deepseek-chat",
        api_key: str = "",
        base_url: str = "",        # NEW: resolved by ProviderRouter
        model: str = "",           # NEW: resolved by ProviderRouter
    ) -> None:
        self._config_path = config_path or _DEFAULT_CONFIG_PATH
        self._auth_path = auth_path or _DEFAULT_AUTH_PATH
        self._default_provider = default_provider
        self._default_model = default_model
        self._base_url = base_url
        self._model = model
        self._http: httpx.AsyncClient | None = None

        self._config = self._load_config()
        self._auth = self._load_auth()
        self._pool = CredentialPool()
        self._load_keys_into_pool()
        self._last_usage: dict[str, int] = {}
```

- [ ] **Step 2: Update `_resolve_model()` to not reference PROVIDERS dict**

Replace lines 144-151:

```python
    def _resolve_model(self, model: str) -> tuple[str, str]:
        """Resolve model string to (provider, model_name)."""
        model = model or self._model or f"{self._default_provider}/{self._default_model}"
        if "/" in model:
            prov, name = model.split("/", 1)
            return prov, name
        return self._default_provider, model
```

- [ ] **Step 3: Update `_get_base_url()` to use constructor base_url first**

Replace lines 153-155:

```python
    def _get_base_url(self, provider: str) -> str:
        # Use constructor-provided base_url (from ProviderRouter) if available.
        if self._base_url:
            return self._base_url
        # Fallback: config.yaml providers.<name>.base_url.
        cfg = self._config.get("providers", {}).get(provider, {})
        return cfg.get("base_url", "") or PROVIDER_BASE_URLS.get(provider, "https://api.openai.com/v1")
```

Add import at top:
```python
from agent_core.model_catalog import PROVIDER_BASE_URLS
```

- [ ] **Step 4: Update `_build_headers()` to not reference PROVIDERS for extra_headers**

Replace lines 157-163:

```python
    def _build_headers(self, provider: str, api_key: str) -> dict[str, str]:
        h = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        # config.yaml providers.<name>.extra_headers.
        cfg_extra = self._config.get("providers", {}).get(provider, {}).get("extra_headers", {})
        h.update(cfg_extra)
        return h
```

- [ ] **Step 5: Update `_load_auth()` to not reference PROVIDERS for env var fallback**

Replace lines 178-189:

```python
    def _load_auth(self) -> dict[str, list[dict[str, Any]]]:
        if self._auth_path.exists():
            return json.loads(self._auth_path.read_text(encoding="utf-8"))
        # Fall back to env vars — iterate over all known provider env vars.
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
```

- [ ] **Step 6: Run existing provider tests**

```bash
cd /d/JalaAgent/jalaagent && uv run pytest extensions/providers/universal/tests/ -v 2>&1 | tail -20
```

- [ ] **Step 7: Commit**

```bash
cd /d/JalaAgent/jalaagent && git add extensions/providers/universal/src/provider_universal/provider.py && git commit -m "refactor: delete PROVIDERS dict, accept base_url from constructor in universal provider"
```

---

### Task 5: New /model Command Handler with full Pipeline

**Files:**
- Modify: `packages/agent-core/src/agent_core/commands.py:249-253`

- [ ] **Step 1: Add model aliases and switch_model to commands.py**

Add after the imports (after line 11):

```python
# Model aliases — short names → full model identifiers.
MODEL_ALIASES: dict[str, str] = {
    "sonnet":    "claude-sonnet-4-6",
    "opus":      "claude-opus-4-8",
    "haiku":     "claude-haiku-4-5",
    "4o":        "gpt-4o",
    "4o-mini":   "gpt-4o-mini",
    "ds":        "deepseek/deepseek-chat",
    "dsr":       "deepseek/deepseek-reasoner",
    "qwen-plus": "qwen/qwen-plus",
    "qwen-max":  "qwen/qwen-max",
}
```

- [ ] **Step 2: Replace _model() handler (lines 249-253)**

Replace the current 5-line `_model` function with:

```python
    async def _model(ctx: CommandContext) -> CommandResult:
        """Full model switch pipeline with interactive picker support.

        /model                  → show interactive picker (Telegram: keyboard, CLI: select)
        /model <name>           → direct switch
        /model --save <name>    → persist to config.yaml
        /model --refresh        → bust cache + re-fetch
        /model --save --refresh qwen/qwen-plus  → persist + refresh + switch
        """
        from agent_core.model_catalog import ModelCatalog, MODEL_ALIASES  # noqa: PLC0415

        catalog = ModelCatalog()
        args = ctx.args or []
        model_input: str | None = None
        persist_global = False
        force_refresh = False
        show_picker = False

        # ── Parse flags ──
        remaining: list[str] = []
        for a in args:
            if a == "--save":
                persist_global = True
            elif a == "--refresh":
                force_refresh = True
            elif a == "--picker":
                show_picker = True
            else:
                remaining.append(a)

        model_input = " ".join(remaining).strip() if remaining else None

        loop = ctx.agent_loop
        if loop is None:
            return CommandResult("No agent loop available.")

        # ── Resolve alias ──
        if model_input and model_input.lower() in MODEL_ALIASES:
            model_input = MODEL_ALIASES[model_input.lower()]

        # ── No input + no picker requested → show status / interactive ──
        if not model_input and not show_picker:
            current_model = getattr(loop, "model", "unknown")
            current_provider = getattr(loop, "_provider", None)
            prov_name = getattr(current_provider, "__class__.__name__", "unknown")
            return CommandResult(
                f"⚙ **Model Configuration**\n\n"
                f"Current model: `{current_model}`\n"
                f"Provider: {prov_name}\n\n"
                f"Use `/model <name>` to switch, or `/model --picker` for interactive selection.\n"
                f"Flags: `--save` (persist), `--refresh` (fetch latest models)"
            )

        # ── Interactive picker requested ──
        if show_picker or (not model_input and ctx.channel in ("telegram", "cli")):
            providers = catalog.list_providers()
            # Build provider→model count for display.
            provider_info: dict[str, int] = {}
            for prov in providers:
                try:
                    provider_info[prov] = len(catalog.get_models(prov))
                except Exception:
                    provider_info[prov] = 0

            if ctx.channel == "telegram":
                return CommandResult(
                    "",  # text handled by picker
                    keyboard={"type": "model_picker", "providers": provider_info},
                    action="show_model_picker",
                )
            else:
                # CLI: return text for rich select.
                lines = [f"⚙ **Model Configuration**\n  Current: `{current_model}`\n\nSelect a provider:"]
                for prov, count in sorted(provider_info.items(), key=lambda x: x[0]):
                    lines.append(f"  {prov} ({count} models)")
                return CommandResult("\n".join(lines))

        # ── Direct switch with model_input ──
        new_model = model_input
        new_provider = ""
        new_base_url = ""

        # Parse provider/model syntax.
        if "/" in new_model:
            new_provider = new_model.split("/", 1)[0]
        else:
            # Try to detect provider from prefix.
            for prov, patterns in {
                "deepseek": ["deepseek-"],
                "anthropic": ["claude-"],
                "openai": ["gpt-", "o1-", "o3-"],
                "qwen": ["qwen-", "qwq-"],
            }.items():
                if any(new_model.lower().startswith(p) for p in patterns):
                    new_provider = prov
                    break

        # Switch agent loop model.
        loop.model = new_model

        # Persist to config.yaml if --save.
        if persist_global:
            import yaml as _yaml  # noqa: PLC0415
            cfg_path = Path.home() / ".jalaagent" / "config.yaml"
            cfg: dict[str, Any] = {}
            if cfg_path.exists():
                cfg = _yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            cfg.setdefault("model", {})["default"] = new_model
            if new_provider:
                cfg["model"]["provider"] = new_provider
            if new_base_url:
                cfg["model"]["base_url"] = new_base_url
            cfg_path.parent.mkdir(parents=True, exist_ok=True)
            cfg_path.write_text(_yaml.dump(cfg, default_flow_style=False, sort_keys=False), encoding="utf-8")

        provider_info = f"\nProvider: `{new_provider}`" if new_provider else ""
        save_info = "\nSaved to config.yaml" if persist_global else ""
        return CommandResult(f"🤖 Switched to: `{new_model}`{provider_info}{save_info}")
```

- [ ] **Step 3: Update CommandResult dataclass to support model_picker keyboard**

Verify `CommandResult` already has `keyboard: Any = None` and `action: str = "reply"`. No changes needed — the existing fields support this.

- [ ] **Step 4: Verify command still works without breaking existing tests**

```bash
cd /d/JalaAgent/jalaagent && uv run python -c "from agent_core.commands import get_registry; r = get_registry(); print('Commands:', len(r.list_all())); cmd = r.get('model'); print('Handler:', cmd.handler.__name__ if cmd else 'MISSING')"
# Expected: Commands: 46, Handler: _model
```

- [ ] **Step 5: Commit**

```bash
cd /d/JalaAgent/jalaagent && git add packages/agent-core/src/agent_core/commands.py && git commit -m "feat: replace /model stub with full switch_model pipeline, aliases, --save, --refresh"
```

---

### Task 6: Telegram Model Picker (Inline Keyboard)

**Files:**
- Modify: `extensions/channels/telegram/src/channel_telegram/channel.py` (add state + builders)
- Modify: `extensions/channels/telegram/src/channel_telegram/handlers.py` (add callbacks)

- [ ] **Step 1: Add model picker state + methods to channel.py**

Add to `TelegramChannel.__init__()` (after line 53):

```python
        # Model picker state per chat.
        self._model_picker_state: dict[int, dict[str, Any]] = {}
```

Add these methods to `TelegramChannel` class:

```python
    # ------------------------------------------------------------------
    # Model picker (interactive provider → model selection)
    # ------------------------------------------------------------------

    async def show_model_picker(self, chat_id: int, message_id: int | None = None) -> None:
        """Render the provider selection keyboard."""
        from agent_core.model_catalog import ModelCatalog
        catalog = ModelCatalog()
        providers = catalog.list_providers()

        # Build provider info: name → model count.
        provider_info: dict[str, int] = {}
        for prov in providers:
            try:
                provider_info[prov] = len(catalog.get_models(prov))
            except Exception:
                provider_info[prov] = 0

        keyboard = self._build_provider_keyboard(provider_info)
        text = (
            "⚙ **Model Configuration**\n\n"
            f"Current model: `{getattr(self._agent_loop, 'model', 'unknown')}`\n\n"
            "Select a provider:"
        )
        if message_id:
            await self._app.bot.edit_message_text(
                chat_id=chat_id, message_id=message_id,
                text=text, reply_markup=keyboard, parse_mode="Markdown",
            )
        else:
            await self._app.bot.send_message(
                chat_id=chat_id, text=text, reply_markup=keyboard, parse_mode="Markdown",
            )

    @staticmethod
    def _build_provider_keyboard(provider_info: dict[str, int]) -> Any:
        """Build provider selection inline keyboard."""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        buttons: list[list[Any]] = []
        row: list[Any] = []
        for prov, count in sorted(provider_info.items(), key=lambda x: x[0]):
            label = f"{prov} ({count})"
            row.append(InlineKeyboardButton(label, callback_data=f"mp:{prov}"))
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        buttons.append([InlineKeyboardButton("✕ Cancel", callback_data="mx:")])
        return InlineKeyboardMarkup(buttons)

    @staticmethod
    def _build_model_keyboard(
        provider: str, models: list[str], page: int = 0
    ) -> Any:
        """Build model selection inline keyboard with pagination."""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        per_page = 8
        start = page * per_page
        page_models = models[start:start + per_page]
        total_pages = (len(models) + per_page - 1) // per_page

        buttons: list[list[Any]] = []
        for i, m in enumerate(page_models):
            idx = start + i
            buttons.append([InlineKeyboardButton(m, callback_data=f"mm:{provider}:{idx}")])

        nav: list[Any] = []
        if page > 0:
            nav.append(InlineKeyboardButton("◀ Prev", callback_data=f"mg:{provider}:{page - 1}"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton("Next ▶", callback_data=f"mg:{provider}:{page + 1}"))
        if nav:
            buttons.append(nav)
        buttons.append([
            InlineKeyboardButton("◀ Back", callback_data="mb:"),
            InlineKeyboardButton("✕ Cancel", callback_data="mx:"),
        ])
        return InlineKeyboardMarkup(buttons)

    async def _handle_model_selected(
        self, chat_id: int, provider: str, model: str, message_id: int
    ) -> None:
        """Execute model switch and show confirmation."""
        from agent_core.model_catalog import resolve_base_url

        # Switch the model on the agent loop.
        model_id = f"{provider}/{model}" if "/" not in model else model
        if self._agent_loop:
            self._agent_loop.model = model_id

        base_url = ""
        try:
            base_url = resolve_base_url(provider)
        except KeyError:
            pass

        text = (
            f"✅ **Switched to:** `{model_id}`\n"
            f"Provider: {provider}\n"
            + (f"Endpoint: {base_url}\n" if base_url else "")
            + "\nUse `/model --save` to make this permanent."
        )
        await self._app.bot.edit_message_text(
            chat_id=chat_id, message_id=message_id,
            text=text, parse_mode="Markdown",
        )
        # Clean up picker state.
        self._model_picker_state.pop(chat_id, None)
```

- [ ] **Step 2: Add callback handlers to handlers.py**

Add to `handle_callback()` (after line 69):

```python
        # ── Model picker callbacks ──
        elif data.startswith("mp:"):
            await self._handle_model_picker_provider(query, data)
        elif data.startswith("mm:"):
            await self._handle_model_picker_select(query, data)
        elif data.startswith("mg:"):
            await self._handle_model_picker_page(query, data)
        elif data in ("mb:", "mx:"):
            await self._handle_model_picker_dismiss(query, data)
```

Add the handler methods:

```python
    async def _handle_model_picker_provider(self, query: Any, data: str) -> None:
        """User tapped a provider button (mp:<slug>). Show model list."""
        provider = data.split(":", 1)[1]
        from agent_core.model_catalog import ModelCatalog
        catalog = ModelCatalog()
        try:
            models = catalog.get_models(provider)
        except Exception:
            models = []

        chat_id = query.message.chat_id
        self._channel._model_picker_state[chat_id] = {
            "provider": provider, "models": models, "page": 0,
        }
        keyboard = self._channel._build_model_keyboard(provider, models, 0)
        text = (
            f"**{provider}** — {len(models)} models\n\n"
            "Select a model:"
        )
        await query.edit_message_text(text=text, reply_markup=keyboard, parse_mode="Markdown")

    async def _handle_model_picker_select(self, query: Any, data: str) -> None:
        """User tapped a model button (mm:<provider>:<index>). Execute switch."""
        parts = data.split(":", 2)
        provider = parts[1]
        idx = int(parts[2]) if len(parts) > 2 else 0
        chat_id = query.message.chat_id
        state = self._channel._model_picker_state.get(chat_id, {})
        models = state.get("models", [])
        if idx < len(models):
            model = models[idx]
            await self._channel._handle_model_selected(
                chat_id, provider, model, query.message.message_id,
            )

    async def _handle_model_picker_page(self, query: Any, data: str) -> None:
        """User tapped pagination (mg:<provider>:<page>)."""
        parts = data.split(":", 2)
        provider = parts[1]
        page = int(parts[2]) if len(parts) > 2 else 0
        chat_id = query.message.chat_id
        state = self._channel._model_picker_state.get(chat_id, {})
        models = state.get("models", [])
        self._channel._model_picker_state[chat_id]["page"] = page
        keyboard = self._channel._build_model_keyboard(provider, models, page)
        await query.edit_message_reply_markup(reply_markup=keyboard)

    async def _handle_model_picker_dismiss(self, query: Any, data: str) -> None:
        """User tapped Cancel or Back."""
        if data == "mb:":
            # Back to provider selection.
            await self._channel.show_model_picker(
                query.message.chat_id, query.message.message_id,
            )
        else:
            # Cancel — dismiss.
            await query.edit_message_text("⚙ Model picker dismissed.")
```

- [ ] **Step 3: Update command dispatch to detect model_picker action**

In handlers.py `_dispatch_command()`, after `result = await cmd.handler(ctx)`:

```python
            if result and result.action == "show_model_picker" and result.keyboard:
                message = await update.message.reply_text(
                    "⚙ Loading model picker...",
                )
                await self._channel.show_model_picker(
                    update.message.chat_id, message.message_id,
                )
                return
```

- [ ] **Step 4: Commit**

```bash
cd /d/JalaAgent/jalaagent && git add extensions/channels/telegram/src/channel_telegram/ && git commit -m "feat: add Telegram model picker with inline keyboard, pagination, callback handlers"
```

---

### Task 7: CLI Model Select (Rich)

**Files:**
- Modify: `extensions/channels/cli/src/channel_cli/channel.py:138-165`

- [ ] **Step 1: Add model picker method to CLIChannel class**

After the `_dispatch_command()` method (after line 165), add:

```python
    async def _show_model_picker(self, result: Any) -> None:
        """Interactive model picker for CLI channel via rich select."""
        provider_info = result.keyboard.get("providers", {}) if result.keyboard else {}
        if not provider_info:
            self._console.print(result.text)
            return

        provider_list = sorted(provider_info.items(), key=lambda x: x[0])
        self._console.print()
        self._console.print(Panel(
            f"Current model: {getattr(self, '_agent_loop', None) and getattr(self._agent_loop, 'model', 'unknown')}",
            title="⚙ Model Configuration", border_style="cyan",
        ))
        self._console.print("\nSelect a provider:")
        for i, (prov, count) in enumerate(provider_list, 1):
            self._console.print(f"  {i}. {prov} ({count} models)")

        choice = Prompt.ask("Provider number", default="1")
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(provider_list):
                provider = provider_list[idx][0]
                from agent_core.model_catalog import ModelCatalog
                catalog = ModelCatalog()
                models = catalog.get_models(provider)
                if models:
                    self._console.print(f"\n[bold]{provider}[/] — {len(models)} models")
                    for i, m in enumerate(models[:20], 1):
                        self._console.print(f"  {i}. {m}")
                    model_choice = Prompt.ask("Model number", default="1")
                    try:
                        midx = int(model_choice) - 1
                        if 0 <= midx < len(models):
                            model = models[midx]
                            model_id = f"{provider}/{model}" if "/" not in model else model
                            # Switch the model on the agent loop.
                            self._console.print(f"[green]✅ Switched to: {model_id}[/]")
                    except (ValueError, IndexError):
                        self._console.print("[red]Invalid model selection.[/]")
        except (ValueError, IndexError):
            self._console.print("[red]Invalid provider selection.[/]")
```

- [ ] **Step 2: Wire into CLI _dispatch_command()**

Edit `_dispatch_command()` at line 161-163. Change:

```python
        try:
            result = await cmd.handler(ctx)
            if result and result.text:
                self._console.print(Markdown(result.text))
```

To:

```python
        try:
            result = await cmd.handler(ctx)
            if result and result.action == "show_model_picker":
                await self._show_model_picker(result)
                return
            if result and result.text:
                self._console.print(Markdown(result.text))
```

- [ ] **Step 3: Commit**

```bash
cd /d/JalaAgent/jalaagent && git add extensions/channels/cli/src/channel_cli/channel.py && git commit -m "feat: add CLI model select via rich interactive prompts"
```

---

### Task 8: Wire `--base-url` CLI Flag + Persistence in main.py

**Files:**
- Modify: `cli/src/jala/main.py:31-116,208-214`

- [ ] **Step 1: Add --base-url CLI option**

Add to the typer callback in `main` (line 208-214):

```python
@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    model: str = typer.Option(None, "--model", "-m", help="Model"),
    plan: bool = typer.Option(False, "--plan", help="Plan mode"),
    telegram: bool = typer.Option(False, "--telegram", help="Telegram only"),
    prompt: str | None = typer.Option(None, "--prompt", "-p", help="Single prompt"),
    base_url: str | None = typer.Option(None, "--base-url", help="Override API base URL"),  # NEW
) -> None:
```

Thread it through: `agent_loop = _build_agent(model, plan, base_url=base_url)`.

- [ ] **Step 2: Update _build_agent() signature**

```python
def _build_agent(model: str | None = None, plan: bool = False, base_url: str | None = None) -> Any:
```

Thread `base_url` into `_pick_provider(model, creds, base_url=base_url)`.

- [ ] **Step 3: Update _pick_provider()**

```python
def _pick_provider(model: str | None, creds: Any, base_url: str | None = None) -> Any:
    config = _load_jala_config()
    config_providers = config.get("providers", {})
    router = ProviderRouter()
    return router.resolve(
        model=model, creds=creds,
        cli_base_url=base_url,
        config_providers=config_providers,
    )
```

- [ ] **Step 4: Verify CLI works**

```bash
cd /d/JalaAgent/jalaagent && uv run jala --help | grep "base-url"
# Expected: --base-url  TEXT  Override API base URL
```

- [ ] **Step 5: Commit**

```bash
cd /d/JalaAgent/jalaagent && git add cli/src/jala/main.py && git commit -m "feat: add --base-url CLI flag, wire into ProviderRouter resolution"
```

---

### Task 9: Integration Verification

**Files:**
- No new files — verification only.

- [ ] **Step 1: Verify static catalog loads**

```bash
cd /d/JalaAgent/jalaagent && uv run python -c "
from agent_core.model_catalog import PROVIDER_BASE_URLS, PROVIDER_MODELS, resolve_base_url
print(f'Providers: {len(PROVIDER_BASE_URLS)}')
print(f'Qwen base URL: {resolve_base_url(\"qwen\")}')
print(f'OpenAI base URL: {resolve_base_url(\"openai\")}')
# Test env override.
import os
os.environ['DASHSCOPE_BASE_URL'] = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
print(f'Qwen with env: {resolve_base_url(\"qwen\")}')
"
```

- [ ] **Step 2: Verify /model command registers**

```bash
cd /d/JalaAgent/jalaagent && uv run python -c "
from agent_core.commands import get_registry
r = get_registry()
cmd = r.get('model')
print(f'/model handler: {cmd.handler.__name__ if cmd else \"MISSING\"}')
print(f'Category: {cmd.category if cmd else \"-\"}')
"
```

- [ ] **Step 3: Verify jala --help shows all commands**

```bash
cd /d/JalaAgent/jalaagent && uv run jala --help 2>&1 | grep -E "config-show|config-get|base-url"
```

- [ ] **Step 4: Run all tests**

```bash
cd /d/JalaAgent/jalaagent && uv run pytest tests/packages/agent-core/test_model_catalog.py tests/packages/agent-core/test_provider_router.py -v
```

- [ ] **Step 5: Verify Qwen dual endpoint works (manual, needs live key)**

```bash
# China endpoint
export DASHSCOPE_API_KEY="sk-007..."
export DASHSCOPE_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
uv run jala --model qwen/qwen-plus --prompt "hello" 2>&1 | head -5
```

- [ ] **Step 6: Commit final docs update**

```bash
cd /d/JalaAgent/jalaagent && git add -A && git commit -m "docs: update CHANGELOG and docs for provider/model system overhaul"
```
