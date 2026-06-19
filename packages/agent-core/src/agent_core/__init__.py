"""JalaAgent Agent Core — agent loop, provider abstraction, tool registry, credentials."""

from agent_core.compaction import ContextCompactor
from agent_core.errors import (
    APIErrorClassifier,
    AuthError,
    ContentPolicyError,
    ContextTooLongError,
    JalaAgentError,
    RateLimitError,
    RetryPolicy,
    TimeoutError,
    ToolLoopError,
    TransientError,
)
from agent_core.harness import (
    BackgroundTaskManager,
    DiffEditor,
    PlanMode,
    SandboxedShell,
    WorktreeIsolation,
)
from agent_core.loop import AgentLoop

# Credential pool and core tools available via direct import:
#   from agent_core.credentials import CredentialPool
#   from agent_core.core_tools import register_all
from agent_core.models import (
    ActionCategory,
    AgentChunk,
    AgentMessage,
    ApprovalMode,
    ApprovalRequest,
    ApprovalResult,
    ChunkType,
    ContentBlock,
    FailoverReason,
    LoopConfig,
    ProviderChunk,
    ProviderChunkType,
    ToolCall,
    ToolDescriptor,
    ToolResult,
)
from agent_core.registry import DESTRUCTIVE_CATEGORIES, ToolRegistry

__all__ = [
    # models
    "ActionCategory",
    "AgentChunk",
    "AgentMessage",
    "ApprovalMode",
    "ApprovalRequest",
    "ApprovalResult",
    "ChunkType",
    "ContentBlock",
    "FailoverReason",
    "LoopConfig",
    "ProviderChunk",
    "ProviderChunkType",
    "ToolCall",
    "ToolDescriptor",
    "ToolResult",
    # registry
    "ToolRegistry",
    "DESTRUCTIVE_CATEGORIES",
    # loop
    "AgentLoop",
    # compaction
    "ContextCompactor",
    # errors
    "JalaAgentError",
    "RateLimitError",
    "AuthError",
    "ContentPolicyError",
    "ContextTooLongError",
    "TimeoutError",
    "TransientError",
    "ToolLoopError",
    "APIErrorClassifier",
    "RetryPolicy",
    # harness
    "WorktreeIsolation",
    "PlanMode",
    "SandboxedShell",
    "BackgroundTaskManager",
    "DiffEditor",
]
