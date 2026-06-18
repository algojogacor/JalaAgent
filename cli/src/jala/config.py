"""Configuration loading from env vars and YAML config file."""

import os
from pathlib import Path
from typing import Any

import yaml

_CONFIG_PATH = Path.home() / ".jalaagent" / "config.yaml"


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    """Load JalaAgent configuration.

    Priority: env vars > YAML config > defaults.
    """
    path = config_path or _CONFIG_PATH
    config: dict[str, Any] = _defaults()

    # Load YAML if it exists.
    if path.exists():
        try:
            with path.open(encoding="utf-8") as f:
                yaml_config = yaml.safe_load(f) or {}
            _deep_merge(config, yaml_config)
        except Exception:
            pass

    # Override from env vars.
    _apply_env_overrides(config)

    return config


def _defaults() -> dict[str, Any]:
    return {
        "agent": {"name": "JalaAgent", "model": "claude-sonnet-4-6", "max_iterations": 100},
        "memory": {
            "embedding_model": "qwen3:0.6b",
            "embedding_dim": 1024,
            "embedding_base_url": "http://localhost:11434",
            "dreaming": {"enabled": True, "schedule": "0 3 * * *"},
        },
        "approval": {
            "mode": "normal",
            "rules": {
                "file_read": "auto", "file_write": "auto", "file_delete": "ask",
                "shell_exec": "ask", "network_get": "auto", "network_post": "ask",
                "messaging_send": "ask", "memory_write": "auto",
            },
        },
        "channels": {"telegram": {"token": "", "allowed_users": []}, "cli": {"enabled": True}},
        "mcp": {"idle_timeout": 300, "servers": []},
    }


def _apply_env_overrides(config: dict[str, Any]) -> None:
    """Apply environment variable overrides (JALA_ prefix)."""
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
            # Convert types.
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
