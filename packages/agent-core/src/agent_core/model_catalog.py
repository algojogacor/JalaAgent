"""Provider model catalog — static curated lists, base_url defaults, live API fetch with disk cache.

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

# Provider name -> env var for base_url override.
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
