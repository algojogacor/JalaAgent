"""Tests for agent-core tool registry."""

import pytest
from agent_core.errors import ToolLoopError
from agent_core.models import (
    ActionCategory,
    LoopConfig,
    ToolDescriptor,
)
from agent_core.registry import DESTRUCTIVE_CATEGORIES, ToolRegistry

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(
        ToolDescriptor(
            name="read_file",
            description="Read a file from disk",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
            category=ActionCategory.FILE_READ,
        ),
        handler=lambda args: f"Contents of {args.get('path', '?')}",
    )
    reg.register(
        ToolDescriptor(
            name="write_file",
            description="Write content to a file",
            input_schema={"type": "object"},
            category=ActionCategory.FILE_WRITE,
            is_destructive=True,
            max_result_chars=100,
        ),
        handler=lambda args: "OK",
    )
    reg.register(
        ToolDescriptor(
            name="shell_exec",
            description="Run a shell command",
            input_schema={"type": "object"},
            category=ActionCategory.SHELL_EXEC,
            is_destructive=True,
        ),
        handler=lambda args: "output",
        check_fn=lambda: False,  # always unavailable
    )
    return reg


# ---------------------------------------------------------------------------
# Registration & lookup
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_exact_lookup(self, registry: ToolRegistry) -> None:
        assert registry.get("read_file") is not None
        assert registry.get("write_file") is not None

    def test_case_insensitive(self, registry: ToolRegistry) -> None:
        assert registry.get("READ_FILE") is not None
        assert registry.get("Read_File") is not None

    def test_snake_camel_repair(self, registry: ToolRegistry) -> None:
        reg = ToolRegistry()
        reg.register(
            ToolDescriptor(name="readFile", description="", category=ActionCategory.FILE_READ, input_schema={}),
            handler=lambda args: "ok",
        )
        assert reg.get("read_file") is not None

    def test_camel_snake_repair(self, registry: ToolRegistry) -> None:
        # read_file registered → readFile should match.
        assert registry.get("readFile") is not None

    def test_difflib_fallback(self, registry: ToolRegistry) -> None:
        # Close but misspelled.
        assert registry.get("read_flie") is not None  # difflib 0.7 match

    def test_unknown_tool(self, registry: ToolRegistry) -> None:
        assert registry.get("nonexistent_tool_xyz") is None


class TestGetAvailable:
    def test_available_excludes_disabled(self, registry: ToolRegistry) -> None:
        available = registry.get_available()
        names = {d.name for d in available}
        assert "read_file" in names
        assert "write_file" in names
        assert "shell_exec" not in names  # check_fn returns False


class TestFuzzyRepair:
    def test_repair_failure_returns_none(self) -> None:
        reg = ToolRegistry()
        assert reg.get("zzz_nonexistent") is None


@pytest.mark.asyncio
class TestFuzzyRepairAsync:
    async def test_repair_failure_raises_on_execute(self) -> None:
        reg = ToolRegistry()
        with pytest.raises(ValueError, match="Unknown tool"):
            await reg.execute("zzz_nonexistent", {})


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestExecute:
    async def test_execute_read_file(self, registry: ToolRegistry) -> None:
        result = await registry.execute("read_file", {"path": "/tmp/test.txt"})
        assert not result.is_error
        assert "/tmp/test.txt" in result.content

    async def test_execute_unknown_raises(self, registry: ToolRegistry) -> None:
        with pytest.raises(ValueError, match="Unknown tool"):
            await registry.execute("no_such_tool", {})

    async def test_overflow_wraps(self, registry: ToolRegistry) -> None:
        # write_file has max_result_chars=100. Provide a handler that returns >100 chars.
        reg = ToolRegistry()
        reg.register(
            ToolDescriptor(
                name="big_output",
                description="Returns a lot of data",
                category=ActionCategory.FILE_READ,
                max_result_chars=100,
            ),
            handler=lambda args: "x" * 500,
        )
        result = await reg.execute("big_output", {})
        assert result.overflowed
        assert result.overflow_path is not None

    async def test_untrusted_wrapping(self, registry: ToolRegistry) -> None:
        result = await registry.execute(
            "read_file", {"path": "/tmp"}, is_untrusted=True
        )
        assert result.is_untrusted
        assert "<untrusted_tool_result>" in result.content

    async def test_handler_error(self, registry: ToolRegistry) -> None:
        reg = ToolRegistry()
        reg.register(
            ToolDescriptor(
                name="failing", description="", category=ActionCategory.FILE_READ, input_schema={},
            ),
            handler=lambda args: (_ for _ in ()).throw(ValueError("boom")),
        )
        result = await reg.execute("failing", {})
        assert result.is_error
        assert "boom" in result.content


# ---------------------------------------------------------------------------
# Loop detection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestLoopDetection:
    async def test_hard_stop(self) -> None:
        cfg = LoopConfig(
            loop_detection_window=10,
            loop_warning_threshold=3,
            loop_hard_stop_threshold=5,
        )
        reg = ToolRegistry(loop_config=cfg)
        reg.register(
            ToolDescriptor(
                name="repeater", description="", category=ActionCategory.FILE_READ, input_schema={},
            ),
            handler=lambda args: "ok",
        )

        # Call 4 times — should not raise.
        for _ in range(4):
            await reg.execute("repeater", {"key": "value"})

        # 5th call — should raise.
        with pytest.raises(ToolLoopError):
            await reg.execute("repeater", {"key": "value"})

    async def test_different_args_different_calls(self) -> None:
        cfg = LoopConfig(loop_hard_stop_threshold=3)
        reg = ToolRegistry(loop_config=cfg)
        reg.register(
            ToolDescriptor(
                name="reader", description="", category=ActionCategory.FILE_READ, input_schema={},
            ),
            handler=lambda args: "ok",
        )

        # Different arguments — no loop.
        for i in range(5):
            await reg.execute("reader", {"file": f"file_{i}"})


# ---------------------------------------------------------------------------
# Destructive categories
# ---------------------------------------------------------------------------


class TestDestructiveCategories:
    def test_default_set(self) -> None:
        assert ActionCategory.FILE_WRITE in DESTRUCTIVE_CATEGORIES
        assert ActionCategory.FILE_DELETE in DESTRUCTIVE_CATEGORIES
        assert ActionCategory.SHELL_EXEC in DESTRUCTIVE_CATEGORIES
        assert ActionCategory.FILE_READ not in DESTRUCTIVE_CATEGORIES
        assert ActionCategory.NETWORK_GET not in DESTRUCTIVE_CATEGORIES
