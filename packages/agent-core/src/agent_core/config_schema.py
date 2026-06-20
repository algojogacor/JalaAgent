"""Pydantic v2 schema for JalaAgent config.yaml validation.

Mirrors the 16-section defaults in ``cli/src/jala/config.py:_defaults()``.
All fields have defaults — validation never blocks startup; it logs warnings
and falls back to the raw dict.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ModelConfig(BaseModel):
    """Top-level model selection."""
    default: str = "deepseek-v4-flash-260425"
    provider: str = "deepseek"
    context_length: int = 200000


class ProviderModel(BaseModel):
    """A single model entry under a provider."""
    name: str
    default: bool = False


class ProviderEntry(BaseModel):
    """Configuration for one provider endpoint."""
    base_url: str = ""
    models: list[ProviderModel] = Field(default_factory=list)
    extra_headers: dict[str, str] = Field(default_factory=dict)


class AuxiliaryRole(BaseModel):
    """Background-task model role."""
    provider: str = ""
    model: str = ""
    timeout: int = 120


class AuxiliaryConfig(BaseModel):
    compression: AuxiliaryRole = Field(default_factory=AuxiliaryRole)
    dreaming: AuxiliaryRole = Field(default_factory=AuxiliaryRole)
    title_generation: AuxiliaryRole = Field(default_factory=AuxiliaryRole)
    vision: AuxiliaryRole = Field(default_factory=AuxiliaryRole)


class CredentialPoolConfig(BaseModel):
    strategy: str = "round_robin"
    health_check_interval: int = 3600
    max_retries: int = 5
    jitter: bool = True


class AgentConfig(BaseModel):
    name: str = "JalaAgent"
    max_iterations: int = Field(default=100, gt=0)
    model: str = "claude-sonnet-4-6"
    provider: str = "deepseek"
    api_max_retries: int = 3
    tool_use_enforcement: str = "auto"
    task_completion_guidance: bool = True
    image_input_mode: str = "auto"


class DelegationConfig(BaseModel):
    max_sub_agent_depth: int = 1
    max_concurrent_sub_agents: int = 5
    sub_agent_iteration_budget: int = 50
    timeout: int = 300


class CompressionConfig(BaseModel):
    enabled: bool = True
    threshold: float = 0.8
    target_ratio: float = 0.6
    keep_recent_tokens: int = 20000
    protect_last_n: int = 50
    protect_first_n: int = 3


class ApprovalRules(BaseModel):
    file_read: str = "auto"
    file_write: str = "auto"
    file_delete: str = "ask"
    shell_exec: str = "ask"
    network_get: str = "auto"
    network_post: str = "ask"
    messaging_send: str = "ask"
    memory_write: str = "auto"


class ApprovalConfig(BaseModel):
    mode: str = "normal"
    rules: ApprovalRules = Field(default_factory=ApprovalRules)


class MemoryDreamingConfig(BaseModel):
    enabled: bool = True
    schedule: str = "0 3 * * *"


class MemoryConfig(BaseModel):
    embedding_model: str = "qwen3:0.6b"
    embedding_dim: int = 1024
    embedding_base_url: str = "http://localhost:11434"
    dreaming: MemoryDreamingConfig = Field(default_factory=MemoryDreamingConfig)
    max_retrieval_results: int = 10
    retrieval_threshold: float = 0.7
    memory_dir: str = "~/.jalaagent/memories"
    db_path: str = "~/.jalaagent/db/memory.db"


class SkillsConfig(BaseModel):
    bundled_dir: str = "auto"
    user_dir: str = "~/.jalaagent/skills"
    max_skills_in_prompt: int = 150
    max_chars_per_skill: int = 40000


class ChannelCLIConfig(BaseModel):
    enabled: bool = True
    footer: bool = True
    spinner: bool = True
    streaming_refresh: int = 10


class ChannelTelegramConfig(BaseModel):
    token: str = ""
    allowed_users: list[int] = Field(default_factory=list)
    polling_interval: int = 1
    edit_interval: float = 0.5


class ChannelsConfig(BaseModel):
    cli: ChannelCLIConfig = Field(default_factory=ChannelCLIConfig)
    telegram: ChannelTelegramConfig = Field(default_factory=ChannelTelegramConfig)


class SessionsConfig(BaseModel):
    storage: str = "jsonl"
    directory: str = "~/.jalaagent/memories/sessions"
    cleanup_days: int = 90
    auto_prune: bool = False
    write_json_snapshots: bool = False


class MCPConfig(BaseModel):
    idle_timeout: int = 300
    servers: list[dict[str, Any]] = Field(default_factory=list)


class LoggingConfig(BaseModel):
    level: str = "INFO"
    file: str = "~/.jalaagent/logs/jala.log"
    format: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


class SecurityConfig(BaseModel):
    prompt_injection_detection: bool = True
    scan_skills_on_install: bool = True


class JalaConfig(BaseModel):
    """Top-level JalaAgent configuration schema.

    Every field has a default that matches ``config.py:_defaults()``.
    Unknown keys in user YAML are silently ignored (``extra="ignore"``)
    so that future version upgrades don't break existing configs.
    """
    model_config = {"extra": "ignore"}

    model: ModelConfig = Field(default_factory=ModelConfig)
    providers: dict[str, ProviderEntry] = Field(default_factory=dict)
    fallback_providers: list[str] = Field(default_factory=lambda: ["deepseek", "openrouter", "groq", "mistral", "ollama"])
    credential_pool: CredentialPoolConfig = Field(default_factory=CredentialPoolConfig)
    auxiliary: AuxiliaryConfig = Field(default_factory=AuxiliaryConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    delegation: DelegationConfig = Field(default_factory=DelegationConfig)
    compression: CompressionConfig = Field(default_factory=CompressionConfig)
    approval: ApprovalConfig = Field(default_factory=ApprovalConfig)
    channels: ChannelsConfig = Field(default_factory=ChannelsConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    skills: SkillsConfig = Field(default_factory=SkillsConfig)
    sessions: SessionsConfig = Field(default_factory=SessionsConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
