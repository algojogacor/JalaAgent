# tests/packages/agent-core/test_model_catalog.py
import pytest
from agent_core.model_catalog import PROVIDER_BASE_URLS, PROVIDER_MODELS, BASE_URL_ENV_VARS

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
