"""Core pydantic models for JalaAgent agent-core."""

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ApprovalMode(str, Enum):
    """Tool approval modes for actions."""

    PARANOID = "paranoid"  # Ask for everything
    NORMAL = "normal"      # Ask only for destructive actions
    YOLO = "yolo"          # Bypass all approvals
    CUSTOM = "custom"      # Per-category rules via config


class ActionCategory(str, Enum):
    """Categories for tool action classification."""

    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"
    SHELL_EXEC = "shell_exec"
    NETWORK_GET = "network_get"
    NETWORK_POST = "network_post"
    MESSAGING_SEND = "messaging_send"
    MEMORY_WRITE = "memory_write"


class FailoverReason(str, Enum):
    """Why a provider request failed and how to recover."""

    RATE_LIMIT = "rate_limit"
    AUTH_ERROR = "auth_error"
    CONTENT_POLICY = "content_policy"
    CONTEXT_TOO_LONG = "context_too_long"
    TIMEOUT = "timeout"
    TRANSIENT = "transient"
    UNKNOWN = "unknown"


class ChunkType(str, Enum):
    """Types of streaming chunks emitted by the agent loop."""

    TEXT = "text"
    TOOL_CALL = "tool_call"
    TOOL_START = "tool_start"
    TOOL_RESULT = "tool_result"
    APPROVAL_REQUEST = "approval_request"
    MEMORY_UPDATE = "memory_update"
    SKILL_PROPOSAL = "skill_proposal"
    THINKING = "thinking"
    DONE = "done"
    ERROR = "error"


class ProviderChunkType(str, Enum):
    """Types of chunks from a provider's streaming response."""

    TEXT = "text"
    TOOL_CALL = "tool_call"
    THINKING = "thinking"
    DONE = "done"


# ---------------------------------------------------------------------------
# Messaging
# ---------------------------------------------------------------------------


class ContentBlock(BaseModel):
    """A single content block in a multi-modal message."""

    type: str = "text"
    text: str = ""


class ToolCall(BaseModel):
    """A tool-use request from the model."""

    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    name: str = ""
    arguments: dict[str, Any] = Field(default_factory=dict)


class AgentMessage(BaseModel):
    """An LLM conversation message."""

    role: Literal["user", "assistant", "tool", "system"] = "user"
    content: str | list[ContentBlock] = ""
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None


class ProviderChunk(BaseModel):
    """A single chunk from a provider's streaming response."""

    type: ProviderChunkType
    content: str | None = None
    tool_call: ToolCall | None = None


# ---------------------------------------------------------------------------
# Tool system
# ---------------------------------------------------------------------------


class ToolDescriptor(BaseModel):
    """Describes a tool to the provider and the registry."""

    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    category: ActionCategory
    is_destructive: bool = False
    max_result_chars: int = 50000


class ToolResult(BaseModel):
    """The result of a tool execution."""

    content: str = ""
    is_error: bool = False
    is_untrusted: bool = False
    overflowed: bool = False
    overflow_path: Path | None = None


# ---------------------------------------------------------------------------
# Approval
# ---------------------------------------------------------------------------


class ApprovalRequest(BaseModel):
    """A request for user approval of a tool execution."""

    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    tool_name: str
    tool_category: ActionCategory
    arguments: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class ApprovalResult(BaseModel):
    """The user's response to an approval request."""

    approved: bool = False
    reason: str = ""


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------


class AgentChunk(BaseModel):
    """A single chunk emitted by the agent loop."""

    type: ChunkType
    content: str | None = None
    metadata: dict[str, Any] | None = None


class LoopConfig(BaseModel):
    """Configuration for the agent conversation loop."""

    max_iterations: int = Field(default=100, gt=0)
    max_sub_agent_depth: int = Field(default=1, ge=0)
    max_concurrent_sub_agents: int = Field(default=5, ge=1)
    sub_agent_iteration_budget: int = Field(default=50, gt=0)
    compaction_threshold: float = Field(
        default=0.8, gt=0.0, le=1.0,
        description="Fraction of context window at which compaction triggers",
    )
    loop_detection_window: int = Field(
        default=10, ge=1,
        description="Number of recent calls to track for loop detection",
    )
    loop_warning_threshold: int = Field(default=3, ge=1)
    loop_hard_stop_threshold: int = Field(default=5, ge=1)
    overflow_result_chars: int = Field(
        default=50000, ge=1000,
        description="Result size at which overflow to temp file",
    )


__all__ = [
    # Enums
    "ApprovalMode",
    "ActionCategory",
    "FailoverReason",
    "ChunkType",
    "ProviderChunkType",
    # Messaging
    "ContentBlock",
    "ToolCall",
    "AgentMessage",
    "ProviderChunk",
    # Tool system
    "ToolDescriptor",
    "ToolResult",
    # Approval
    "ApprovalRequest",
    "ApprovalResult",
    # Agent loop
    "AgentChunk",
    "LoopConfig",
]
