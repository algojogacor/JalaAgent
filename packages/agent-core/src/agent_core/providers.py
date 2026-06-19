"""Provider router — registry-based provider resolution with configurable fallback.

Replaces the 130-line if/elif chain in _pick_provider() with a declarative
registry.  Adding a new provider is now a one-line entry addition, not a
multi-line copy-paste.
"""

from __future__ import annotations

import importlib
import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProviderEntry:
    """Declarative entry for a single LLM provider.

    Attributes
    ----------
    name:
        Short provider name, e.g. ``"deepseek"``.  Matched against the
        ``provider/`` prefix in model strings.
    env_var:
        Environment variable that holds the API key, e.g. ``"DEEPSEEK_API_KEY"``.
    auth_key:
        Key used inside ``auth.json`` ``providers`` block.
    module_path:
        Dotted import path, e.g. ``"provider_deepseek.provider"``.
    class_name:
        Class name to instantiate from the module, e.g. ``"DeepSeekProvider"``.
    model_patterns:
        Model-name prefixes that imply this provider (e.g. ``["deepseek-"]``).
        Used when the model string has no explicit ``provider/`` prefix.
    priority:
        Lower = higher priority in the fallback chain.  Default 100.
    default_model:
        Model name to pass when none is specified by the caller.
    extra_kwargs:
        Additional keyword arguments forwarded to the provider constructor.
    """

    name: str
    env_var: str
    auth_key: str
    module_path: str
    class_name: str
    model_patterns: list[str] = field(default_factory=list)
    priority: int = 100
    default_model: str | None = None
    extra_kwargs: dict[str, Any] = field(default_factory=dict)
    base_url: str | None = None          # Resolved base URL (set by router)
    base_url_env_var: str = ""           # Env var for base_url override


# ---------------------------------------------------------------------------
# Default provider registry
# ---------------------------------------------------------------------------

DEFAULT_PROVIDERS: list[ProviderEntry] = [
    ProviderEntry(
        "anthropic",
        "ANTHROPIC_API_KEY",
        "anthropic",
        "provider_anthropic.provider",
        "AnthropicProvider",
        model_patterns=["claude-"],
        priority=10,
        default_model="claude-sonnet-4-6",
    ),
    ProviderEntry(
        "openai",
        "OPENAI_API_KEY",
        "openai",
        "provider_openai.provider",
        "OpenAIProvider",
        model_patterns=["gpt-", "o1-", "o3-"],
        priority=20,
        default_model="gpt-4o",
    ),
    ProviderEntry(
        "deepseek",
        "DEEPSEEK_API_KEY",
        "deepseek",
        "provider_deepseek.provider",
        "DeepSeekProvider",
        model_patterns=["deepseek-"],
        priority=30,
        default_model="deepseek-chat",
    ),
    ProviderEntry(
        "groq",
        "GROQ_API_KEY",
        "groq",
        "provider_groq.provider",
        "GroqProvider",
        priority=40,
    ),
    ProviderEntry(
        "mistral",
        "MISTRAL_API_KEY",
        "mistral",
        "provider_mistral.provider",
        "MistralProvider",
        priority=50,
    ),
    ProviderEntry(
        "openrouter",
        "OPENROUTER_API_KEY",
        "openrouter",
        "provider_openrouter.provider",
        "OpenRouterProvider",
        priority=60,
    ),
    ProviderEntry(
        "qwen",
        "DASHSCOPE_API_KEY",
        "qwen",
        "provider_universal.provider",
        "OpenAICompatibleProvider",
        model_patterns=["qwen-", "qwen/", "qwq-"],
        priority=35,
        base_url_env_var="DASHSCOPE_BASE_URL",
    ),
    ProviderEntry(
        "universal",
        "",
        "",
        "provider_universal.provider",
        "OpenAICompatibleProvider",
        priority=70,
        extra_kwargs={},
    ),
    ProviderEntry(
        "ollama",
        "",
        "",
        "provider_ollama.provider",
        "OllamaProvider",
        priority=1000,  # last resort
        default_model="qwen3:0.6b",
    ),
]

# Provider names that can appear in "provider/model" syntax.
KNOWN_PROVIDERS = {
    "anthropic", "openai", "deepseek", "groq", "mistral",
    "openrouter", "ollama", "google", "qwen", "together",
    "perplexity", "xai", "cohere", "fireworks", "cerebras",
    "sambanova", "nvidia", "gemini", "universal",
}


class ProviderRouter:
    """Resolve the best available provider from a registry.

    Resolution order
    ----------------
    1. If *model* contains ``provider/model`` syntax and *provider* is known,
       try that specific provider first.
    2. If *model* starts with a known model-name prefix, route accordingly.
    3. Fall back through the registry sorted by *priority* (lowest first).
    4. Last resort: the lowest-priority entry (typically Ollama local).

    Parameters
    ----------
    entries:
        Provider entries that define the registry.
    """

    def __init__(self, entries: list[ProviderEntry] | None = None) -> None:
        self._entries: list[ProviderEntry] = list(entries or DEFAULT_PROVIDERS)
        # Sort once: lower priority = tried first.
        self._entries.sort(key=lambda e: e.priority)
        # Lookup by name for fast routing.
        self._by_name: dict[str, ProviderEntry] = {e.name: e for e in self._entries}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve(
        self,
        model: str | None = None,
        creds: Any = None,
        cli_base_url: str | None = None,
        config_providers: dict[str, Any] | None = None,
    ) -> Any:
        """Return an instantiated provider, picking the best available.

        *creds* is accepted for API compatibility with the old signature
        but is **not used** — the router reads keys directly from
        environment variables and ``auth.json`` internally.
        """
        model_lower = (model or "").lower()

        # Read auth.json keys once.
        auth_keys = self._read_auth_keys()

        # ── 1. Explicit provider/model syntax ──
        requested = self._parse_requested_provider(model_lower)
        if requested and requested in self._by_name:
            entry = self._by_name[requested]
            provider = self._try_entry(entry, model_lower, auth_keys, cli_base_url, config_providers)
            if provider is not None:
                return provider

        # ── 2. Known model-name prefix routing ──
        if requested is None:
            prefix_match = self._match_prefix(model_lower)
            if prefix_match:
                provider = self._try_entry(prefix_match, model, auth_keys, cli_base_url, config_providers)
                if provider is not None:
                    return provider

        # ── 3. Priority-ordered fallback ──
        for entry in self._entries:
            # Skip Ollama until the very end — it's the safety net.
            if entry.name == "ollama":
                continue
            provider = self._try_entry(entry, model, auth_keys, cli_base_url, config_providers)
            if provider is not None:
                return provider

        # ── 4. Last resort: local Ollama ──
        return self._last_resort_ollama(model)

    def register(self, entry: ProviderEntry) -> None:
        """Add or replace a provider entry at runtime."""
        self._by_name[entry.name] = entry
        # Remove old entry with same name, insert new, re-sort.
        self._entries = [e for e in self._entries if e.name != entry.name]
        self._entries.append(entry)
        self._entries.sort(key=lambda e: e.priority)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _read_auth_keys() -> dict[str, str]:
        """Read API keys from ``~/.jalaagent/auth.json``."""
        import json
        from pathlib import Path

        keys: dict[str, str] = {}
        auth_path = Path.home() / ".jalaagent" / "auth.json"
        if not auth_path.exists():
            return keys
        try:
            auth = json.loads(auth_path.read_text(encoding="utf-8"))
            for prov, entries in auth.get("providers", {}).items():
                for e in entries:
                    k = e.get("key", "") or e.get("access_token", "")
                    if k:
                        keys[prov] = k
                        break
        except Exception:
            pass
        return keys

    @staticmethod
    def _parse_requested_provider(model_lower: str) -> str | None:
        """Extract provider name from ``provider/model`` syntax."""
        if "/" not in model_lower:
            return None
        candidate = model_lower.split("/", 1)[0].strip()
        if candidate in KNOWN_PROVIDERS:
            return candidate
        return None

    def _match_prefix(self, model_lower: str) -> ProviderEntry | None:
        """Match model name prefix to a provider entry."""
        for entry in self._entries:
            for pat in entry.model_patterns:
                if model_lower.startswith(pat):
                    return entry
        return None

    @staticmethod
    def _try_entry(
        entry: ProviderEntry,
        model: str | None,
        auth_keys: dict[str, str],
        cli_base_url: str | None = None,
        config_providers: dict[str, Any] | None = None,
    ) -> Any | None:
        """Try to instantiate *entry*.  Returns ``None`` on failure."""
        import os as _os

        # Resolve API key.
        key = _os.environ.get(entry.env_var, "")
        if not key and entry.auth_key:
            key = auth_keys.get(entry.auth_key, "")

        # Some providers (universal, ollama) don't need a key.
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

            # Resolve base_url through 4-tier chain.
            from agent_core.model_catalog import resolve_base_url  # noqa: PLC0415
            try:
                resolved_base = resolve_base_url(
                    entry.name,
                    cli_base_url=cli_base_url,
                    config_providers=config_providers or {},
                )
                kwargs["base_url"] = resolved_base
            except KeyError:
                pass  # Unknown provider — let constructor use its own default.

            kwargs.update(entry.extra_kwargs)
            return cls(**kwargs)
        except Exception:
            return None

    def _last_resort_ollama(self, model: str | None) -> Any:
        """Return the Ollama provider — always succeeds."""
        from rich.console import Console as _Console  # noqa: PLC0415 — only imported here

        ollama = self._by_name.get("ollama")
        if ollama is None:
            raise RuntimeError("No Ollama entry in provider registry")

        _Console().print(
            "[yellow]No cloud API keys found.[/] "
            "Falling back to local Ollama ([bold]qwen3:0.6b[/]).\n"
            "[dim]Make sure Ollama is running. Run 'jala setup' to configure a cloud provider.[/]"
        )
        mod = importlib.import_module(ollama.module_path)
        cls = getattr(mod, ollama.class_name)
        return cls(model=ollama.default_model or "qwen3:0.6b")
