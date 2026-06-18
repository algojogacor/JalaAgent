"""Core built-in tools — always available (PRD F-02.1).

Tools: read_file, write_file, patch_file, list_dir, shell, fetch,
       memory, delegate_task, skill_manage.
"""

import asyncio
import difflib
import os
import tempfile
from pathlib import Path
from typing import Any

import httpx

logger = __import__("logging").getLogger(__name__)

_MAX_RESULT = 50000  # Overflow threshold.


# ---------------------------------------------------------------------------
# File tools
# ---------------------------------------------------------------------------


async def tool_read_file(args: dict[str, Any]) -> str:
    """Read a file from disk."""
    path = Path(args["path"]).expanduser().resolve()
    if not path.exists():
        return f"Error: file not found: {path}"
    content = await asyncio.to_thread(path.read_text, encoding="utf-8", errors="replace")
    if len(content) > _MAX_RESULT:
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8")
        tmp.write(content)
        tmp.close()
        return f"File too large ({len(content)} chars). Saved to: {tmp.name}"
    return content


async def tool_write_file(args: dict[str, Any]) -> str:
    """Write content to a file (atomic)."""
    path = Path(args["path"]).expanduser().resolve()
    content = args["content"]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.tmp"
    await asyncio.to_thread(tmp.write_text, content, encoding="utf-8")
    os.replace(tmp, path)
    return f"Written {len(content)} chars to {path}"


async def tool_patch_file(args: dict[str, Any]) -> str:
    """Apply a unified diff patch to a file."""
    path = Path(args["path"]).expanduser().resolve()
    diff_text = args["diff"]
    original = await asyncio.to_thread(path.read_text, encoding="utf-8") if path.exists() else ""
    patched = difflib.restore(diff_text.splitlines(True), 1)
    result = "".join(patched)
    tmp = path.parent / f".{path.name}.tmp"
    await asyncio.to_thread(tmp.write_text, result, encoding="utf-8")
    os.replace(tmp, path)
    return f"Patched {path}"


async def tool_list_dir(args: dict[str, Any]) -> str:
    """List directory contents."""
    path = Path(args.get("path", ".")).expanduser().resolve()
    if not path.is_dir():
        return f"Error: not a directory: {path}"
    items = []
    for p in sorted(path.iterdir()):
        suffix = "/" if p.is_dir() else ""
        size = p.stat().st_size if p.is_file() else 0
        items.append(f"  {p.name}{suffix}  ({_fmt_size(size)})")
    return "\n".join(items) if items else "(empty)"


# ---------------------------------------------------------------------------
# Shell tool
# ---------------------------------------------------------------------------


async def tool_shell(args: dict[str, Any]) -> str:
    """Execute a shell command (with timeout)."""
    cmd = args["command"]
    timeout = args.get("timeout", 60)
    cwd = args.get("cwd", ".")
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=cwd
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        result = stdout.decode("utf-8", errors="replace")
        if stderr:
            result += "\n[stderr]\n" + stderr.decode("utf-8", errors="replace")
        return result or "(no output)"
    except asyncio.TimeoutError:
        return f"Command timed out after {timeout}s"


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------


async def tool_fetch(args: dict[str, Any]) -> str:
    """HTTP request (GET or POST)."""
    url = args["url"]
    method = args.get("method", "GET").upper()
    headers = args.get("headers", {})
    body = args.get("body")
    async with httpx.AsyncClient(timeout=30.0) as client:
        if method == "POST":
            resp = await client.post(url, headers=headers, json=body)
        else:
            resp = await client.get(url, headers=headers)
        return resp.text[:_MAX_RESULT]


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------


async def tool_memory(args: dict[str, Any]) -> str:
    """Read/write/search agent memory."""
    action = args.get("action", "read")
    mem_path = Path.home() / ".jalaagent" / "memories" / "MEMORY.md"
    if action == "read":
        if mem_path.exists():
            return await asyncio.to_thread(mem_path.read_text, encoding="utf-8")
        return "(no memory yet)"
    elif action == "write":
        content = args.get("content", "")
        mem_path.parent.mkdir(parents=True, exist_ok=True)
        existing = await asyncio.to_thread(mem_path.read_text, encoding="utf-8") if mem_path.exists() else ""
        await asyncio.to_thread(mem_path.write_text, existing + "\n" + content, encoding="utf-8")
        return f"Memory updated: {content[:100]}..."
    elif action == "search":
        query = args.get("query", "").lower()
        if mem_path.exists():
            text = await asyncio.to_thread(mem_path.read_text, encoding="utf-8")
            lines = [l for l in text.split("\n") if query in l.lower()]
            return "\n".join(lines[:10]) or "(no matches)"
        return "(no memory yet)"
    return "Usage: memory read|write|search"


# ---------------------------------------------------------------------------
# Delegate task
# ---------------------------------------------------------------------------


async def tool_delegate_task(args: dict[str, Any]) -> str:
    """Spawn a sub-agent (v1: placeholder, full in v2)."""
    task = args.get("task", "")
    return f"Sub-agent spawned for: {task[:200]}. (v1: simulation mode)"


# ---------------------------------------------------------------------------
# Skill manage
# ---------------------------------------------------------------------------


async def tool_skill_manage(args: dict[str, Any]) -> str:
    """Create/edit/delete skills."""
    action = args.get("action", "list")
    skills_dir = Path.home() / ".jalaagent" / "skills"
    if action == "list":
        if skills_dir.is_dir():
            items = [p.name for p in skills_dir.iterdir() if p.is_dir()]
            return "Skills:\n" + "\n".join(f"  - {s}" for s in items) if items else "(no skills installed)"
        return "(no skills installed)"
    elif action == "create":
        name = args.get("name", "unnamed")
        desc = args.get("description", "")
        body = args.get("body", "")
        skill_dir = skills_dir / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        content = f"---\nname: {name}\ndescription: {desc}\nversion: 1.0.0\n---\n\n{body}"
        await asyncio.to_thread((skill_dir / "SKILL.md").write_text, content, encoding="utf-8")
        return f"Skill created: {name}"
    return "Usage: skill_manage list|create"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n}{unit}"
        n = n // 1024
    return f"{n}TB"


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------


def register_all(registry: Any) -> None:
    """Register all core tools into a ToolRegistry instance."""
    from agent_core.models import ActionCategory, ToolDescriptor

    tools = [
        ("read_file", "Read a file from disk", ActionCategory.FILE_READ, tool_read_file),
        ("write_file", "Write content to a file (atomic)", ActionCategory.FILE_WRITE, tool_write_file),
        ("patch_file", "Apply a unified diff patch to a file", ActionCategory.FILE_WRITE, tool_patch_file),
        ("list_dir", "List directory contents", ActionCategory.FILE_READ, tool_list_dir),
        ("shell", "Execute a terminal command", ActionCategory.SHELL_EXEC, tool_shell),
        ("fetch", "Make an HTTP request", ActionCategory.NETWORK_GET, tool_fetch),
        ("memory", "Read/write/search agent memory", ActionCategory.MEMORY_WRITE, tool_memory),
        ("delegate_task", "Spawn a sub-agent", ActionCategory.SHELL_EXEC, tool_delegate_task),
        ("skill_manage", "Create/edit/delete skills", ActionCategory.FILE_WRITE, tool_skill_manage),
    ]
    for name, desc, cat, handler in tools:
        registry.register(
            ToolDescriptor(name=name, description=desc, category=cat, is_destructive=(cat != ActionCategory.FILE_READ)),
            handler=handler,
        )
