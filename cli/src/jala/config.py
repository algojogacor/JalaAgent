"""Configuration loading with 16-section Hermes-parity defaults.

Priority: env vars (JALA_ prefix) > config.yaml > defaults.

All sections declared here match the setup.py output — nothing produced
by the setup wizard is invisible to runtime code.
"""

import os
from pathlib import Path
from typing import Any

import yaml

_CONFIG_PATH = Path.home() / ".jalaagent" / "config.yaml"

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    """Load JalaAgent configuration with full Hermes-parity defaults."""
    path = config_path or _CONFIG_PATH
    config: dict[str, Any] = _defaults()

    if path.exists():
        try:
            with path.open(encoding="utf-8") as f:
                yaml_config = yaml.safe_load(f) or {}
            _deep_merge(config, yaml_config)
        except Exception:
            pass

    _apply_env_overrides(config)
    return config


def get_config_path() -> Path:
    return _CONFIG_PATH


# ---------------------------------------------------------------------------
# Defaults — 16 top-level sections matching setup.py output
# ---------------------------------------------------------------------------


def _defaults() -> dict[str, Any]:
    return {
        # ── Block 1: Provider System ──
        "model": {"default": "auto", "provider": "auto", "context_length": 200000},
        "providers": {
            "deepseek": {"base_url": "https://api.deepseek.com/v1", "models": [{"name": "deepseek-v4-flash-260425", "default": True}, {"name": "deepseek-v4-pro-260425"}]},
            "openai": {"base_url": "https://api.openai.com/v1", "models": [{"name": "gpt-4o", "default": True}, {"name": "gpt-4o-mini"}, {"name": "o4-mini"}]},
            "anthropic": {"base_url": "https://api.anthropic.com", "models": [{"name": "claude-sonnet-4-6", "default": True}]},
            "google": {"base_url": "https://generativelanguage.googleapis.com/v1beta", "models": [{"name": "gemini-2.5-flash", "default": True}]},
            "qwen": {"base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1", "models": [{"name": "qwen3.7-max", "default": True}]},
            "groq": {"base_url": "https://api.groq.com/openai/v1", "models": [{"name": "llama-4-scout-17b-16e-instruct", "default": True}]},
            "mistral": {"base_url": "https://api.mistral.ai/v1", "models": [{"name": "mistral-large-latest", "default": True}]},
            "openrouter": {"base_url": "https://openrouter.ai/api/v1", "models": [{"name": "anthropic/claude-sonnet-4", "default": True}]},
            "together": {"base_url": "https://api.together.xyz/v1", "models": [{"name": "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8", "default": True}]},
            "perplexity": {"base_url": "https://api.perplexity.ai", "models": [{"name": "sonar-pro", "default": True}]},
            "xai": {"base_url": "https://api.x.ai/v1", "models": [{"name": "grok-3", "default": True}]},
            "cohere": {"base_url": "https://api.cohere.ai/v1", "models": [{"name": "command-r-plus", "default": True}]},
            "fireworks": {"base_url": "https://api.fireworks.ai/inference/v1", "models": [{"name": "accounts/fireworks/models/llama-v3p1-70b-instruct", "default": True}]},
            "cerebras": {"base_url": "https://api.cerebras.ai/v1", "models": [{"name": "llama-3.3-70b", "default": True}]},
            "sambanova": {"base_url": "https://api.sambanova.ai/v1", "models": [{"name": "Meta-Llama-3.1-70B", "default": True}]},
            "nvidia": {"base_url": "https://integrate.api.nvidia.com/v1", "models": [{"name": "meta/llama-4-maverick", "default": True}]},
            "alibaba": {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "models": [{"name": "qwen3.7-max", "default": True}]},
            "doubao": {"base_url": "https://ark.cn-beijing.volces.com/api/v3", "models": [{"name": "doubao-pro", "default": True}]},
            "kimi": {"base_url": "https://api.moonshot.cn/v1", "models": [{"name": "kimi-k2.6", "default": True}]},
            "minimax": {"base_url": "https://api.minimax.chat/v1", "models": [{"name": "MiniMax-M3", "default": True}]},
            "zai": {"base_url": "https://api.z.ai/api/paas/v4", "models": [{"name": "glm-4-plus", "default": True}]},
            "jina": {"base_url": "https://api.jina.ai/v1", "models": [{"name": "jina-embeddings-v3", "default": True}]},
            "alibaba-coding": {"base_url": "https://coding-intl.dashscope.aliyuncs.com/v1", "models": [{"name": "qwen3-coder-plus", "default": True}]},
            "ollama": {"base_url": "http://localhost:11434/v1", "models": [{"name": "qwen3:0.6b", "default": True}]},
            "ollama-cloud": {"base_url": "http://localhost:11434/v1", "models": [{"name": "qwen3-coder:480b-cloud", "default": True}]},
        },
        "fallback_providers": ["deepseek", "openrouter", "zai", "alibaba", "mistral", "groq", "nvidia", "google", "perplexity", "cohere", "ollama"],
        "credential_pool": {"strategy": "round_robin", "health_check_interval": 3600, "max_retries": 5, "jitter": True},
        "auxiliary": {
            "compression": {"provider": "", "model": "", "timeout": 120},
            "dreaming": {"provider": "", "model": "", "timeout": 120},
            "title_generation": {"provider": "", "model": "", "timeout": 30},
            "vision": {"provider": "", "model": "", "timeout": 120},
        },

        # ── Block 2: Agent Runtime ──
        "agent": {
            "name": "JalaAgent",
            "max_iterations": 100,
            "model": "claude-sonnet-4-6",
            "provider": "deepseek",
            "api_max_retries": 3,
            "tool_use_enforcement": "auto",
            "task_completion_guidance": True,
            "image_input_mode": "auto",
        },
        "delegation": {"max_sub_agent_depth": 1, "max_concurrent_sub_agents": 5, "sub_agent_iteration_budget": 50, "timeout": 300},
        "compression": {"enabled": True, "threshold": 0.8, "target_ratio": 0.6, "keep_recent_tokens": 20000, "protect_last_n": 50, "protect_first_n": 3},
        "prompt_caching": {"enabled": True, "cache_ttl": "60m", "provider": "anthropic"},
        "checkpoints": {"enabled": True, "max_snapshots": 50, "max_checkpoints": 10, "retention_days": 7, "auto_prune": False, "directory": "~/.jalaagent/checkpoints"},

        # ── Block 3: Tools & Execution ──
        "tool_loop_guardrails": {
            "loop_detection_window": 10,
            "warn_after": {"exact_failure": 2, "same_tool_failure": 3, "idempotent_no_progress": 2},
            "hard_stop_after": {"exact_failure": 5, "same_tool_failure": 8, "idempotent_no_progress": 5},
        },
        "tool_output": {"max_bytes": 50000, "max_lines": 10000, "max_line_length": 5000, "overflow_dir": "~/.jalaagent/tmp"},
        "code_execution": {"block_dangerous": True, "default_timeout": 120, "max_output_chars": 100000},
        "approval": {
            "mode": "normal",
            "rules": {
                "file_read": "auto", "file_write": "auto", "file_delete": "ask",
                "shell_exec": "ask", "network_get": "auto", "network_post": "ask",
                "messaging_send": "ask", "memory_write": "auto",
            },
        },

        # ── Block 4: Channels ──
        "channels": {
            "cli": {"enabled": True, "footer": True, "spinner": True, "streaming_refresh": 10},
            "telegram": {"token": "", "allowed_users": [], "polling_interval": 1, "edit_interval": 0.5},
        },

        # ── Block 5: Memory & Skills ──
        "memory": {
            "embedding_model": "qwen3:0.6b",
            "embedding_dim": 1024,
            "embedding_base_url": "http://localhost:11434",
            "dreaming": {"enabled": True, "schedule": "0 3 * * *"},
            "max_retrieval_results": 10,
            "retrieval_threshold": 0.7,
            "memory_dir": "~/.jalaagent/memories",
            "db_path": "~/.jalaagent/db/memory.db",
        },
        "skills": {"bundled_dir": "auto", "user_dir": "~/.jalaagent/skills", "max_skills_in_prompt": 150, "max_chars_per_skill": 40000},
        "curator": {"enabled": True, "stale_days": 30, "auto_archive": False},
        "goals": {"max_active": 1, "auto_clear_on_new": True},

        # ── Block 6: Hooks & Automation ──
        "hooks": {},
        "cron": {"enabled": False, "tasks": {}},
        "blueprints": {"directory": "~/.jalaagent/blueprints"},
        "kanban": {"enabled": False},

        # ── Block 7: UX & Display ──
        "display": {"footer": True, "spinner": True, "theme": "auto", "timestamps": False},
        "streaming": {"edit_interval": 0.5, "buffer_threshold": 50, "refresh_rate": 10, "max_delay": 0.1},
        "personalities": {
            "directory": "~/.jalaagent/personalities",
            "bundled": ["coder", "debugger", "researcher", "concise", "brainstorming", "auditor"],
            "inline": _bundled_personalities(),
        },

        # ── Block 8: Production ──
        "network": {"proxy": "", "timeout": 120, "max_retries": 3, "verify_ssl": True},
        "logging": {"level": "INFO", "file": "~/.jalaagent/logs/jala.log", "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"},
        "security": {"prompt_injection_detection": True, "scan_skills_on_install": True},
        "privacy": {"telemetry": False, "no_phone_home": True},
        "sessions": {"storage": "jsonl", "directory": "~/.jalaagent/memories/sessions", "cleanup_days": 90, "auto_prune": False, "write_json_snapshots": False},
        "mcp": {"idle_timeout": 300, "servers": []},
    }


# ---------------------------------------------------------------------------
# Bundled personalities (inline, Hermes-parity)
# ---------------------------------------------------------------------------


def _bundled_personalities() -> dict[str, str]:
    """Return bundled personality prompts.  These are JalaAgent versions
    inspired by — but distinct from — Hermes personality prompts."""
    return {
        "coder": (
            "You are JalaAgent in coder mode — a senior software engineer who writes "
            "clean, secure, maintainable code. Never produce generic boilerplate. "
            "Every output must be specific to the context. No hardcoded secrets. "
            "No copy-pasted components. You think in systems, not features. "
            "Security is a first-class requirement. You have opinions and explain "
            "your reasoning. When modifying existing code: specify exact line numbers "
            "with context. Never rewrite entire files to change one line."
        ),
        "debugger": (
            "You are JalaAgent in debugger mode. Find and fix bugs — don't explain "
            "them, fix them. Start with root cause, not symptoms. Never patch a "
            "symptom if the root cause is fixable. For each bug: state what it is, "
            "why it happens, and the exact fix. Prioritize by blast radius: crashes "
            "first, data corruption second, logic errors third, cosmetic last. "
            "After fixing, always verify. No fix is done until it's verified."
        ),
        "researcher": (
            "You are JalaAgent in research mode. Produce rigorous, defensible "
            "analysis — not summaries, not opinion pieces. Every claim needs "
            "evidence. Every methodology needs justification. Every conclusion "
            "must follow from the data. When exploring a topic: stress-test the "
            "research question first — is it specific enough? Is it answerable? "
            "A vague question produces vague answers. Cross-reference sources. "
            "Acknowledge limitations honestly. Prefer primary sources."
        ),
        "concise": (
            "You are JalaAgent in concise mode. Keep responses brief and to the "
            "point. No preamble, no fluff, no AI-sounding filler phrases. Answer "
            "the question directly. If the user needs more detail, they will ask."
        ),
        "brainstorming": (
            "You are JalaAgent in brainstorming mode. Generate ideas — not safe "
            "ones, not obvious ones. Start from unexpected angles. Challenge the "
            "premise before answering. Generate at least one unconventional idea "
            "and defend why it might work. Think in analogies. Cross-pollinate "
            "domains. Be specific: no vague suggestions. Quantity first, judgment "
            "later. Contradiction is allowed — propose opposite ideas if both have "
            "merit. The goal is surface area, not a conclusion."
        ),
        "auditor": (
            "You are JalaAgent in auditor mode. Your job is systematic code audit "
            "— find every flaw before it reaches production. Work in passes: first "
            "for crashes and data corruption, second for logic errors and edge "
            "cases, third for security and config mismatches, fourth for structural "
            "issues. Never stop at surface symptoms — trace every bug to root "
            "cause. For each issue: severity (CRITICAL/HIGH/MEDIUM/LOW), file path, "
            "line number, what the bug is, why it happens, and the exact fix. "
            "A bug you miss is a bug that ships. If you find something suspicious "
            "but cannot confirm, flag it as SUSPECT — don't silently skip it."
        ),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _apply_env_overrides(config: dict[str, Any]) -> None:
    env_map = {
        "JALA_MODEL": ("agent", "model"),
        "JALA_APPROVAL_MODE": ("approval", "mode"),
        "JALA_EMBEDDING_MODEL": ("memory", "embedding_model"),
        "JALA_EMBEDDING_DIM": ("memory", "embedding_dim"),
        "JALA_EMBEDDING_URL": ("memory", "embedding_base_url"),
        "JALA_DREAMING_ENABLED": ("memory", "dreaming", "enabled"),
        "JALA_DREAMING_SCHEDULE": ("memory", "dreaming", "schedule"),
    }
    for env_var, keys in env_map.items():
        value = os.environ.get(env_var)
        if value is not None:
            d = config
            for key in keys[:-1]:
                d = d.setdefault(key, {})
            if env_var == "JALA_EMBEDDING_DIM":
                value = int(value)  # type: ignore[assignment]
            elif env_var == "JALA_DREAMING_ENABLED":
                value = value.lower() in ("true", "1", "yes")  # type: ignore[assignment]
            d[keys[-1]] = value


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> None:
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
