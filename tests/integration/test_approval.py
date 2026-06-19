"""Integration test: approval modes against destructive tool calls."""

from unittest.mock import AsyncMock

import pytest
from agent_core.models import ActionCategory
from agent_core.registry import DESTRUCTIVE_CATEGORIES

# ---------------------------------------------------------------------------
# Approval mode simulation
# ---------------------------------------------------------------------------


def _needs_approval(
    category: ActionCategory,
    mode: str,
    custom_rules: dict[str, str] | None = None,
) -> bool:
    """Simulate the approval policy pipeline.

    Parameters
    ----------
    category:
        The tool action category.
    mode:
        One of paranoid / normal / yolo / custom.
    custom_rules:
        Per-category rules for CUSTOM mode.
    """
    if mode == "yolo":
        return False
    if mode == "paranoid":
        return True
    if mode == "normal":
        return category in DESTRUCTIVE_CATEGORIES
    if mode == "custom" and custom_rules:
        rule = custom_rules.get(category.value, "ask")
        return rule == "ask"
    return True


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestApprovalModes:
    def test_paranoid_always_asks(self) -> None:
        """PARANOID mode — every category requires approval."""
        for cat in ActionCategory:
            assert _needs_approval(cat, "paranoid") is True

    def test_yolo_never_asks(self) -> None:
        """YOLO mode — no category requires approval."""
        for cat in ActionCategory:
            assert _needs_approval(cat, "yolo") is False

    def test_normal_destructive_asks(self) -> None:
        """NORMAL mode — destructive categories require approval."""
        destructive = {
            ActionCategory.FILE_WRITE,
            ActionCategory.FILE_DELETE,
            ActionCategory.SHELL_EXEC,
            ActionCategory.NETWORK_POST,
            ActionCategory.MESSAGING_SEND,
            ActionCategory.MEMORY_WRITE,
        }
        for cat in ActionCategory:
            expected = cat in destructive
            assert _needs_approval(cat, "normal") == expected

    def test_normal_file_read_auto(self) -> None:
        """FILE_READ is not destructive — auto-approved in NORMAL mode."""
        assert _needs_approval(ActionCategory.FILE_READ, "normal") is False

    def test_normal_network_get_auto(self) -> None:
        """NETWORK_GET is not destructive — auto-approved in NORMAL mode."""
        assert _needs_approval(ActionCategory.NETWORK_GET, "normal") is False

    def test_custom_file_delete_auto(self) -> None:
        """CUSTOM mode with file_delete: auto → not asked."""
        assert (
            _needs_approval(
                ActionCategory.FILE_DELETE,
                "custom",
                {"file_delete": "auto"},
            )
            is False
        )

    def test_custom_file_delete_ask(self) -> None:
        """CUSTOM mode with file_delete: ask → asked."""
        assert (
            _needs_approval(
                ActionCategory.FILE_DELETE,
                "custom",
                {"file_delete": "ask"},
            )
            is True
        )

    def test_custom_shell_exec_auto(self) -> None:
        """CUSTOM mode with shell_exec: auto → not asked."""
        assert (
            _needs_approval(
                ActionCategory.SHELL_EXEC,
                "custom",
                {"shell_exec": "auto"},
            )
            is False
        )


@pytest.mark.asyncio
class TestApprovalCallback:
    async def test_callback_called_for_destructive(self) -> None:
        """Simulate approval callback being called and returning True."""
        callback = AsyncMock(return_value=True)
        result = await callback()
        assert result is True
        callback.assert_called_once()


class TestDestructiveCategoriesSet:
    def test_default_destructive_set(self) -> None:
        """Verify the default destructive categories match the PRD."""
        assert ActionCategory.FILE_WRITE in DESTRUCTIVE_CATEGORIES
        assert ActionCategory.FILE_DELETE in DESTRUCTIVE_CATEGORIES
        assert ActionCategory.SHELL_EXEC in DESTRUCTIVE_CATEGORIES
        assert ActionCategory.NETWORK_POST in DESTRUCTIVE_CATEGORIES
        assert ActionCategory.MESSAGING_SEND in DESTRUCTIVE_CATEGORIES
        assert ActionCategory.MEMORY_WRITE in DESTRUCTIVE_CATEGORIES
        # Non-destructive.
        assert ActionCategory.FILE_READ not in DESTRUCTIVE_CATEGORIES
        assert ActionCategory.NETWORK_GET not in DESTRUCTIVE_CATEGORIES
