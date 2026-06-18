"""Tests for agent-core models."""

import pytest

from agent_core.models import (
    ActionCategory,
    AgentChunk,
    AgentMessage,
    ApprovalMode,
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


class TestApprovalMode:
    def test_values(self) -> None:
        assert ApprovalMode.PARANOID == "paranoid"
        assert ApprovalMode.NORMAL == "normal"
        assert ApprovalMode.YOLO == "yolo"
        assert ApprovalMode.CUSTOM == "custom"


class TestActionCategory:
    def test_values(self) -> None:
        assert ActionCategory.FILE_READ == "file_read"
        assert ActionCategory.FILE_WRITE == "file_write"
        assert ActionCategory.SHELL_EXEC == "shell_exec"


class TestFailoverReason:
    def test_values(self) -> None:
        assert FailoverReason.RATE_LIMIT == "rate_limit"
        assert FailoverReason.TRANSIENT == "transient"


class TestAgentMessage:
    def test_defaults(self) -> None:
        msg = AgentMessage(role="user", content="hello")
        assert msg.role == "user"
        assert msg.content == "hello"
        assert msg.tool_calls is None
        assert msg.tool_call_id is None

    def test_with_tool_calls(self) -> None:
        tc = ToolCall(id="tc1", name="read_file", arguments={"path": "/tmp"})
        msg = AgentMessage(role="assistant", content="", tool_calls=[tc])
        assert len(msg.tool_calls) == 1
        assert msg.tool_calls[0].name == "read_file"

    def test_tool_message(self) -> None:
        msg = AgentMessage(role="tool", content="result", tool_call_id="tc1")
        assert msg.tool_call_id == "tc1"

    def test_multimodal_content(self) -> None:
        blocks = [ContentBlock(text="Hello"), ContentBlock(text="World")]
        msg = AgentMessage(role="user", content=blocks)
        assert isinstance(msg.content, list)
        assert len(msg.content) == 2


class TestToolDescriptor:
    def test_minimal(self) -> None:
        desc = ToolDescriptor(
            name="read_file",
            description="Read a file",
            input_schema={"type": "object"},
            category=ActionCategory.FILE_READ,
        )
        assert desc.name == "read_file"
        assert not desc.is_destructive
        assert desc.max_result_chars == 50000


class TestToolResult:
    def test_defaults(self) -> None:
        result = ToolResult(content="done")
        assert result.content == "done"
        assert not result.is_error
        assert not result.overflowed

    def test_error_result(self) -> None:
        result = ToolResult(content="Failed", is_error=True)
        assert result.is_error

    def test_untrusted(self) -> None:
        result = ToolResult(content="web content", is_untrusted=True)
        assert result.is_untrusted


class TestLoopConfig:
    def test_defaults(self) -> None:
        cfg = LoopConfig()
        assert cfg.max_iterations == 100
        assert cfg.compaction_threshold == 0.8
        assert cfg.loop_warning_threshold == 3
        assert cfg.loop_hard_stop_threshold == 5

    def test_validation(self) -> None:
        with pytest.raises(Exception):
            LoopConfig(max_iterations=0)
        with pytest.raises(Exception):
            LoopConfig(compaction_threshold=1.5)
