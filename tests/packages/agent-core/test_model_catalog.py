# tests/packages/agent-core/test_model_catalog.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import os
from agent_core.model_catalog import (
    PROVIDER_BASE_URLS, PROVIDER_MODELS, BASE_URL_ENV_VARS,
    resolve_base_url, ModelCatalog,
)

def test_provider_base_urls_has_required_providers():
    """Every major provider must have a full-URL default."""
    required = ["qwen", "openai", "deepseek", "anthropic", "ollama", "openrouter"]
    for prov in required:
        assert prov in PROVIDER_BASE_URLS, f"Missing base_url for {prov}"
        assert PROVIDER_BASE_URLS[prov].startswith("https://") or \
               PROVIDER_BASE_URLS[prov].startswith("http://"), \
               f"base_url for {prov} must be full URL, got: {PROVIDER_BASE_URLS[prov]}"

def test_provider_base_urls_are_full_paths():
    """All base_urls must include scheme + host — most also include a path like /v1."""
    bare_domain_ok = {"anthropic", "perplexity"}
    for prov, url in PROVIDER_BASE_URLS.items():
        assert "://" in url, f"{prov}: URL must have scheme"
        parts = url.split("/")
        assert len(parts) >= 3, f"{prov}: URL must have at least scheme + host: {url}"
        if prov not in bare_domain_ok:
            assert len(parts) >= 4, f"{prov}: URL must have a path component: {url}"

def test_provider_models_has_curated_lists():
    for prov in PROVIDER_BASE_URLS:
        assert prov in PROVIDER_MODELS, f"Missing model list for {prov}"
        assert len(PROVIDER_MODELS[prov]) >= 1, f"Empty model list for {prov}"

def test_base_url_env_vars_covers_all_providers():
    """Every provider in PROVIDER_BASE_URLS should have an env var mapping."""
    for prov in PROVIDER_BASE_URLS:
        assert prov in BASE_URL_ENV_VARS, f"Missing env var for {prov}"
        assert BASE_URL_ENV_VARS[prov].endswith("_BASE_URL"), \
            f"Env var for {prov} should end with _BASE_URL, got {BASE_URL_ENV_VARS[prov]}"

def test_qwen_has_both_endpoints_documented():
    """Qwen static default is intl, but env var allows China override."""
    assert "qwen" in PROVIDER_BASE_URLS
    assert "dashscope" in PROVIDER_BASE_URLS["qwen"]
    assert BASE_URL_ENV_VARS["qwen"] == "DASHSCOPE_BASE_URL"


# ── Task 2 tests: resolve_base_url + ModelCatalog ──


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


def test_model_catalog_get_models_static_fallback():
    """Catalog returns static list when no cache exists."""
    catalog = ModelCatalog()
    models = catalog.get_models("deepseek")
    assert "deepseek-chat" in models
    assert "deepseek-reasoner" in models


def test_model_catalog_cache_key_varies_by_base_url():
    """Different base_urls produce different cache keys."""
    catalog = ModelCatalog()
    key_a = catalog._cache_key("qwen", "https://dashscope.aliyuncs.com/compatible-mode/v1", "sk-abc12345")
    key_b = catalog._cache_key("qwen", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1", "sk-abc12345")
    assert key_a != key_b


def test_model_catalog_cache_key_varies_by_api_key():
    """Different API keys produce different cache keys."""
    catalog = ModelCatalog()
    key_a = catalog._cache_key("qwen", "https://dashscope.aliyuncs.com/compatible-mode/v1", "sk-aaa11111")
    key_b = catalog._cache_key("qwen", "https://dashscope.aliyuncs.com/compatible-mode/v1", "sk-bbb22222")
    assert key_a != key_b


def test_model_catalog_list_providers():
    """list_providers returns all known provider slugs."""
    catalog = ModelCatalog()
    providers = catalog.list_providers()
    assert "qwen" in providers
    assert "openai" in providers
    assert "ollama" in providers
    assert len(providers) == len(PROVIDER_BASE_URLS)
