"""Tests for JalaAgent harness — worktrees, plan mode, sandbox, tasks, diff editing."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from agent_core.harness import (
    BackgroundTaskManager,
    DiffEditor,
    PlanMode,
    SandboxedShell,
)


# ---------------------------------------------------------------------------
# Plan Mode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestPlanMode:
    async def test_create_and_approve(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            pm = PlanMode(Path(td))
            plan = await pm.create_plan(
                "Add login page",
                "Add a login page with OAuth.",
                [{"title": "Scaffold", "detail": "Create Login component"}],
                files_create=["src/login.tsx"],
                verification=["npm run dev", "visit /login"],
            )
            assert plan.title == "Add login page"
            assert not plan.approved
            assert not pm.is_approved

            await pm.approve()
            assert pm.is_approved

    async def test_reject_discards(self) -> None:
        pm = PlanMode(Path(tempfile.mkdtemp()))
        await pm.create_plan("Test", "Desc", [{"title": "Phase 1"}])
        await pm.reject()
        assert pm.current is None

    async def test_plan_format(self) -> None:
        pm = PlanMode(Path(tempfile.mkdtemp()))
        plan = await pm.create_plan(
            "Fix auth bug", "Fix JWT expiry issue.",
            [{"title": "Analyze", "detail": "Find root cause"}],
            files_modify=["auth.py"],
            files_create=["tests/test_auth.py"],
            verification=["pytest tests/test_auth.py"],
        )
        formatted = plan.format_for_review()
        assert "Fix auth bug" in formatted
        assert "auth.py" in formatted
        assert "pytest" in formatted


# ---------------------------------------------------------------------------
# Sandboxed Shell
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSandboxedShell:
    async def test_safe_command(self) -> None:
        shell = SandboxedShell()
        result = await shell.execute("echo hello")
        assert "hello" in result["stdout"]
        assert result["exit_code"] == 0

    async def test_dangerous_blocked(self) -> None:
        shell = SandboxedShell(block_dangerous=True)
        result = await shell.execute("rm -rf /tmp/test")
        assert result["was_dangerous"]
        assert "BLOCKED" in result["stderr"]

    async def test_dangerous_warned_when_not_blocking(self) -> None:
        shell = SandboxedShell(block_dangerous=False)
        result = await shell.execute("rm -rf /tmp/test")
        assert result["was_dangerous"]  # flagged but not blocked.

    async def test_path_scoping(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            shell = SandboxedShell(allowed_root=Path(td))
            result = await shell.execute("echo test", cwd=td)
            assert result["exit_code"] == 0

            # Trying to escape the allowed root.
            result = await shell.execute("echo test", cwd="/")
            assert "BLOCKED" in result["stderr"]

    async def test_timeout(self) -> None:
        shell = SandboxedShell(default_timeout=0.5)
        result = await shell.execute("sleep 5")
        assert result["timed_out"]

    async def test_history(self) -> None:
        shell = SandboxedShell()
        await shell.execute("echo first")
        await shell.execute("echo second")
        assert len(shell.history) == 2


# ---------------------------------------------------------------------------
# Background Task Manager
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestBackgroundTaskManager:
    async def test_submit_and_get_result(self) -> None:
        btm = BackgroundTaskManager()

        async def slow_op() -> str:
            await asyncio.sleep(0.05)
            return "done"

        name = await btm.submit("test_op", slow_op())
        result = await btm.get_result(name, timeout=1.0)
        assert result["status"] == "completed"
        assert result["result"] == "done"

    async def test_task_failure(self) -> None:
        btm = BackgroundTaskManager()

        async def failing() -> str:
            raise ValueError("boom")

        name = await btm.submit("failing", failing())
        result = await btm.get_result(name, timeout=1.0)
        assert result["status"] == "failed"
        assert "boom" in result["error"]

    async def test_wait_all(self) -> None:
        btm = BackgroundTaskManager()
        await btm.submit("op1", asyncio.sleep(0.01))
        await btm.submit("op2", asyncio.sleep(0.01))
        results = await btm.wait_all(timeout=1.0)
        assert len(results) == 2

    async def test_cancel(self) -> None:
        btm = BackgroundTaskManager()
        async def cancellable() -> None:
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                pass
        name = await btm.submit("long", cancellable())
        assert btm.cancel(name)
        await asyncio.sleep(0.05)  # Let cancellation propagate.
        assert btm.running_count == 0


# ---------------------------------------------------------------------------
# Diff Editor
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestDiffEditor:
    async def test_preview_diff(self) -> None:
        diff = await DiffEditor.preview_diff(
            "hello world\n", "hello universe\n", label="test.txt"
        )
        assert "hello world" in diff or "hello universe" in diff

    async def test_apply_diff(self) -> None:
        import difflib
        original = "line 1\nline 2\nline 3\n"
        modified = "line 1\nmodified line\nline 3\n"
        diff_text = "".join(difflib.unified_diff(
            original.splitlines(True), modified.splitlines(True),
            fromfile="a/test.txt", tofile="b/test.txt",
        ))

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(original)
            path = Path(f.name)

        try:
            success = await DiffEditor.apply_diff(path, diff_text, expected_original=original)
            assert success
            content = path.read_text()
            assert "modified line" in content
        finally:
            path.unlink()

    async def test_drift_detection(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("original\n")
            path = Path(f.name)

        try:
            diff_text = "--- a/test\n+++ b/test\n@@ -1,1 +1,1 @@\n-original\n+changed\n"
            # Pass a wrong expected_original to simulate drift.
            success = await DiffEditor.apply_diff(path, diff_text, expected_original="wrong content")
            assert not success  # Drift detected, edit refused.
        finally:
            path.unlink()
