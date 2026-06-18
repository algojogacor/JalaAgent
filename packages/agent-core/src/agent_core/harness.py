"""JalaAgent Harness — git worktrees, plan mode, sandbox, background tasks.

The harness is what makes JalaAgent safe for real software development.
Inspired by Claude Code's harness: isolated execution, structured planning,
and safety rails that prevent the agent from breaking things.
"""

from __future__ import annotations

import asyncio
import difflib
import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ======================================================================
# 1. GIT WORKTREE ISOLATION
# ======================================================================


@dataclass
class Worktree:
    """An isolated git worktree for safe agent execution."""

    path: Path
    branch: str
    base_ref: str
    created_at: float = field(default_factory=time.monotonic)

    @property
    def exists(self) -> bool:
        return self.path.is_dir()


class WorktreeIsolation:
    """Create and manage isolated git worktrees.

    The agent works inside a disposable worktree.  Changes are never visible
    to the main repo until explicitly merged.  Worktrees are auto-cleaned
    when the session ends if no changes were made.
    """

    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root
        self._active: dict[str, Worktree] = {}

    async def create(
        self, name: str, base_ref: str = "head"
    ) -> Worktree:
        """Create a new isolated worktree.

        Parameters
        ----------
        name:
            Short name for the worktree (used in branch name).
        base_ref:
            Git ref to branch from: ``"head"`` (current HEAD) or
            ``"fresh"`` (origin/<default-branch>).
        """
        safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "-", name)[:64]
        branch = f"jala/{safe_name}-{int(time.monotonic())}"

        if base_ref == "fresh":
            default_branch = await self._default_branch()
            base = f"origin/{default_branch}"
        else:
            base = "HEAD"

        worktree_dir = self._repo_root / ".claude" / "worktrees" / safe_name

        def _sync() -> None:
            worktree_dir.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "worktree", "add", "-b", branch, str(worktree_dir), base],
                cwd=str(self._repo_root), capture_output=True, check=True,
            )

        await asyncio.to_thread(_sync)
        wt = Worktree(path=worktree_dir, branch=branch, base_ref=base_ref)
        self._active[name] = wt
        return wt

    async def remove(self, name: str, discard_changes: bool = False) -> bool:
        """Remove a worktree.  Refuses if there are uncommitted changes."""
        wt = self._active.pop(name, None)
        if wt is None or not wt.exists:
            return False

        if not discard_changes:
            has_changes = await self._has_changes(wt)
            if has_changes:
                return False  # Caller must confirm.

        def _sync() -> None:
            subprocess.run(
                ["git", "worktree", "remove", str(wt.path), "--force"],
                cwd=str(self._repo_root), capture_output=True,
            )
            subprocess.run(
                ["git", "branch", "-D", wt.branch],
                cwd=str(self._repo_root), capture_output=True,
            )

        await asyncio.to_thread(_sync)
        return True

    async def list_worktrees(self) -> list[dict[str, Any]]:
        """List all git worktrees and their status."""

        def _sync() -> list[dict[str, Any]]:
            result = subprocess.run(
                ["git", "worktree", "list", "--porcelain"],
                cwd=str(self._repo_root), capture_output=True, text=True,
            )
            worktrees: list[dict[str, Any]] = []
            current: dict[str, Any] = {}
            for line in result.stdout.split("\n"):
                if line.startswith("worktree "):
                    if current:
                        worktrees.append(current)
                    current = {"path": line.split(" ", 1)[1]}
                elif line.startswith("branch ") and current:
                    current["branch"] = line.split("refs/heads/", 1)[-1]
                elif line.startswith("HEAD ") and current:
                    current["head"] = line.split(" ", 1)[1]
                elif line.startswith("bare") and current:
                    current["bare"] = True
                elif line.startswith("detached") and current:
                    current["detached"] = True
            if current:
                worktrees.append(current)
            return worktrees

        return await asyncio.to_thread(_sync)

    async def _has_changes(self, wt: Worktree) -> bool:
        def _sync() -> bool:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(wt.path), capture_output=True, text=True,
            )
            return bool(result.stdout.strip())
        return await asyncio.to_thread(_sync)

    async def _default_branch(self) -> str:
        def _sync() -> str:
            result = subprocess.run(
                ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
                cwd=str(self._repo_root), capture_output=True, text=True,
            )
            ref = result.stdout.strip()
            return ref.split("/")[-1] if ref else "main"
        return await asyncio.to_thread(_sync)


# ======================================================================
# 2. PLAN MODE
# ======================================================================


@dataclass
class Plan:
    """A structured implementation plan."""

    title: str
    description: str
    phases: list[dict[str, str]] = field(default_factory=list)
    files_to_modify: list[str] = field(default_factory=list)
    files_to_create: list[str] = field(default_factory=list)
    verification_steps: list[str] = field(default_factory=list)
    approved: bool = False

    def format_for_review(self) -> str:
        """Format the plan for user review (rich/CLI friendly)."""
        lines = [
            f"# Plan: {self.title}",
            "",
            self.description,
            "",
            "## Phases",
        ]
        for i, phase in enumerate(self.phases, 1):
            lines.append(f"{i}. **{phase['title']}** — {phase.get('detail', '')}")
        if self.files_to_modify:
            lines.append("\n## Files to Modify")
            for f in self.files_to_modify:
                lines.append(f"- {f}")
        if self.files_to_create:
            lines.append("\n## Files to Create")
            for f in self.files_to_create:
                lines.append(f"- {f}")
        if self.verification_steps:
            lines.append("\n## Verification")
            for v in self.verification_steps:
                lines.append(f"- {v}")
        return "\n".join(lines)


class PlanMode:
    """Structured design-before-implementation workflow.

    Follows Claude Code's plan mode pattern:
    1. Explore codebase → understand context.
    2. Design approach → write plan.
    3. Get user approval → proceed only when confirmed.
    4. Execute plan → implement phase by phase.
    """

    def __init__(self, plans_dir: Path | None = None) -> None:
        self._plans_dir = plans_dir or Path.home() / ".jalaagent" / "plans"
        self._current: Plan | None = None

    async def create_plan(
        self, title: str, description: str, phases: list[dict[str, str]],
        files_modify: list[str] | None = None,
        files_create: list[str] | None = None,
        verification: list[str] | None = None,
    ) -> Plan:
        """Create a new plan and save it for review."""
        plan = Plan(
            title=title,
            description=description,
            phases=phases,
            files_to_modify=files_modify or [],
            files_to_create=files_create or [],
            verification_steps=verification or [],
        )
        self._current = plan
        await self._save_plan(plan)
        return plan

    async def approve(self) -> Plan:
        """Mark the current plan as approved."""
        if self._current is None:
            raise ValueError("No plan to approve")
        self._current.approved = True
        await self._save_plan(self._current)
        return self._current

    async def reject(self) -> None:
        """Discard the current plan."""
        self._current = None

    @property
    def current(self) -> Plan | None:
        return self._current

    @property
    def is_approved(self) -> bool:
        return self._current is not None and self._current.approved

    async def _save_plan(self, plan: Plan) -> None:
        safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "-", plan.title.lower())[:64]
        plan_path = self._plans_dir / f"{safe_name}.md"

        def _sync() -> None:
            plan_path.parent.mkdir(parents=True, exist_ok=True)
            plan_path.write_text(plan.format_for_review(), encoding="utf-8")

        await asyncio.to_thread(_sync)


# ======================================================================
# 3. SANDBOXED EXECUTION
# ======================================================================


# Dangerous patterns that should always trigger a warning or block.
_DANGEROUS_PATTERNS = [
    (re.compile(r"\brm\s+-rf\b"), "Recursive delete detected: rm -rf"),
    (re.compile(r"\bgit\s+push\s+--force"), "Force push detected"),
    (re.compile(r"\bchmod\s+777\b"), "World-writable permissions: chmod 777"),
    (re.compile(r"\bcurl\b.*\|\s*(ba)?sh\b"), "Curl-pipe-shell detected"),
    (re.compile(r">\s*/dev/sda"), "Writing to raw device"),
    (re.compile(r"\bformat\s+C:"), "Disk format detected",),  # Windows
]


class SandboxedShell:
    """Safe shell execution with path scoping and dangerous command detection.

    Features:
    - Working directory scoped to a specific path.
    - Dangerous command patterns detected and blocked/warned.
    - Configurable timeout per command.
    - Output size limits to prevent memory exhaustion.
    """

    def __init__(
        self,
        allowed_root: Path | None = None,
        default_timeout: float = 120.0,
        max_output_chars: int = 100_000,
        block_dangerous: bool = True,
    ) -> None:
        self._allowed_root = allowed_root
        self._default_timeout = default_timeout
        self._max_output_chars = max_output_chars
        self._block_dangerous = block_dangerous
        self._history: list[dict[str, Any]] = []

    async def execute(
        self, command: str, cwd: str | None = None, timeout: float | None = None
    ) -> dict[str, Any]:
        """Execute a shell command safely.

        Returns a dict with keys: stdout, stderr, exit_code, timed_out,
        was_dangerous, truncated.
        """
        # Check for dangerous patterns.
        danger = self._check_dangerous(command)
        if danger and self._block_dangerous:
            return {
                "stdout": "", "stderr": f"BLOCKED: {danger}",
                "exit_code": 1, "timed_out": False,
                "was_dangerous": True, "truncated": False,
            }

        timeout = timeout or self._default_timeout
        work_dir = cwd or (str(self._allowed_root) if self._allowed_root else ".")

        # Scope check.
        if self._allowed_root:
            resolved = Path(work_dir).resolve()
            if not str(resolved).startswith(str(self._allowed_root.resolve())):
                return {
                    "stdout": "", "stderr": "BLOCKED: path outside allowed root",
                    "exit_code": 1, "timed_out": False,
                    "was_dangerous": False, "truncated": False,
                }

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=work_dir,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            return {
                "stdout": "", "stderr": f"Command timed out after {timeout}s",
                "exit_code": -1, "timed_out": True,
                "was_dangerous": bool(danger), "truncated": False,
            }

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        truncated = len(stdout) > self._max_output_chars

        if truncated:
            stdout = stdout[:self._max_output_chars] + (
                f"\n... (truncated from {len(stdout)} chars)"
            )

        result = {
            "stdout": stdout, "stderr": stderr,
            "exit_code": proc.returncode or 0,
            "timed_out": False, "was_dangerous": bool(danger),
            "truncated": truncated,
        }
        self._history.append({"command": command, **result})
        return result

    def _check_dangerous(self, command: str) -> str | None:
        for pattern, message in _DANGEROUS_PATTERNS:
            if pattern.search(command):
                return message
        return None

    @property
    def history(self) -> list[dict[str, Any]]:
        return list(self._history)


# ======================================================================
# Unified diff parsing helpers
# ======================================================================


_HUNK_HEADER_RE = re.compile(r"^@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@")


def _parse_unified_diff(diff_text: str) -> list[dict[str, Any]]:
    """Parse unified diff text into a list of hunks.

    Each hunk is a dict with ``start`` (0-based), ``old_count``,
    ``new_count``, and ``lines``
    (list of (action, content) where action is ``" "``, ``"-"``, or ``"+"``).
    """
    hunks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for line in diff_text.splitlines(True):
        m = _HUNK_HEADER_RE.match(line)
        if m:
            old_start = int(m.group(1)) - 1  # 0-based.
            old_count = int(m.group(2)) if m.group(2) else 1
            new_count = int(m.group(4)) if m.group(4) else 1
            current = {
                "start": old_start,
                "old_count": old_count,
                "new_count": new_count,
                "lines": [],
            }
            hunks.append(current)
        elif current is not None:
            if line.startswith(" ") or line.startswith("-") or line.startswith("+"):
                current["lines"].append((line[0], line[1:]))

    return hunks


def _apply_hunk(
    result_lines: list[str],
    hunk: dict[str, Any],
    offset: int,
) -> tuple[list[str], int]:
    """Apply a single hunk to result_lines, adjusting for line count changes."""
    pos = hunk["start"] + offset
    old_idx = 0
    new_lines: list[str] = []

    for action, content in hunk["lines"]:
        if action == " ":  # Context line.
            if old_idx < len(result_lines) - pos:
                pass  # Already in result_lines.
            old_idx += 1
            pos += 1
        elif action == "-":  # Remove line.
            if pos < len(result_lines):
                result_lines.pop(pos)
            old_idx += 1
        elif action == "+":  # Add line.
            result_lines.insert(pos, content)
            pos += 1
            offset += 1

    return result_lines, offset


# ======================================================================
# 4. BACKGROUND TASK MANAGER
# ======================================================================


class BackgroundTaskManager:
    """Manages long-running background tasks without blocking the agent loop.

    Tasks like `npm install`, `cargo build`, or `pytest` can run in the
    background while the agent continues processing.  Results are collected
    and surfaced when ready.
    """

    def __init__(self, max_concurrent: int = 5) -> None:
        self._max_concurrent = max_concurrent
        self._tasks: dict[str, asyncio.Task[Any]] = {}
        self._results: dict[str, Any] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def submit(self, name: str, coro: Any) -> str:
        """Submit a coroutine to run in the background.

        Returns the task ID immediately.  Use :meth:`get_result` to
        retrieve the output later.
        """
        async with self._semaphore:

            async def _runner() -> Any:
                try:
                    result = await coro
                    self._results[name] = {"status": "completed", "result": result}
                except Exception as exc:
                    self._results[name] = {"status": "failed", "error": str(exc)}
                return self._results[name]

            self._tasks[name] = asyncio.create_task(_runner())
        return name

    async def get_result(self, name: str, timeout: float | None = None) -> Any | None:
        """Get the result of a background task, waiting if still running."""
        task = self._tasks.get(name)
        if task is None:
            return self._results.get(name)
        if not task.done() and timeout:
            try:
                await asyncio.wait_for(task, timeout=timeout)
            except asyncio.TimeoutError:
                return {"status": "running"}
        if task.done():
            return self._results.get(name, {"status": "running"})
        return {"status": "running"}

    async def wait_all(self, timeout: float | None = None) -> dict[str, Any]:
        """Wait for all background tasks to complete."""
        if not self._tasks:
            return {}
        tasks = list(self._tasks.values())
        done, pending = await asyncio.wait(tasks, timeout=timeout)
        for task in pending:
            task.cancel()
        return dict(self._results)

    def cancel(self, name: str) -> bool:
        """Cancel a running background task."""
        task = self._tasks.get(name)
        if task and not task.done():
            task.cancel()
            return True
        return False

    @property
    def running_count(self) -> int:
        return sum(1 for t in self._tasks.values() if not t.done())

    @property
    def completed_count(self) -> int:
        return len(self._results)


# ======================================================================
# 5. DIFF-BASED FILE EDITING
# ======================================================================


class DiffEditor:
    """Safe file editing using unified diffs.

    The agent generates a diff, the user reviews it, and the edit is
    applied atomically.  If the file has changed since the diff was
    generated, the edit is refused (drift detection).
    """

    @staticmethod
    async def preview_diff(original: str, modified: str, label: str = "changes") -> str:
        """Generate a unified diff for user review."""
        diff = difflib.unified_diff(
            original.splitlines(True),
            modified.splitlines(True),
            fromfile=f"a/{label}", tofile=f"b/{label}",
        )
        return "".join(diff)

    @staticmethod
    async def apply_diff(
        path: Path, diff_text: str, expected_original: str | None = None
    ) -> bool:
        """Apply a unified diff to a file, with optional drift check.

        Parses unified diff hunks and applies them line by line.
        Returns ``True`` on success, ``False`` if the file drifted.
        """
        def _sync() -> bool:
            if not path.exists():
                original_lines = []
            else:
                original_lines = path.read_text(encoding="utf-8").splitlines(True)

            if expected_original is not None:
                current = path.read_text(encoding="utf-8") if path.exists() else ""
                if current != expected_original:
                    return False

            # Parse unified diff hunks.
            result_lines = list(original_lines)
            hunks = _parse_unified_diff(diff_text)
            offset = 0
            for hunk in hunks:
                result_lines, offset = _apply_hunk(result_lines, hunk, offset)

            tmp = path.parent / f".{path.name}.tmp"
            tmp.write_text("".join(result_lines), encoding="utf-8")
            os.replace(tmp, path)
            return True

        return await asyncio.to_thread(_sync)

    @staticmethod
    async def read_with_mtime(path: Path) -> tuple[str, float]:
        """Read file content and record mtime for later drift detection."""

        def _sync() -> tuple[str, float]:
            if not path.exists():
                return "", 0.0
            content = path.read_text(encoding="utf-8")
            mtime = os.path.getmtime(path)
            return content, mtime

        return await asyncio.to_thread(_sync)
