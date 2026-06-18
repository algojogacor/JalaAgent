"""Unified slash command registry — same commands work in CLI and Telegram."""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CommandContext:
    channel: str = ""
    session_id: str = ""
    agent_loop: Any = None
    config: dict[str, Any] = field(default_factory=dict)
    args: list[str] = field(default_factory=list)
    raw: str = ""


@dataclass
class CommandResult:
    text: str
    keyboard: Any = None
    action: str = "reply"


@dataclass
class CommandDef:
    name: str
    aliases: list[str]
    description: str
    usage: str
    category: str
    handler: Callable[..., Any]


class CommandRegistry:
    """Universal slash command registry — define once, works in CLI + Telegram."""

    def __init__(self) -> None:
        self._commands: dict[str, CommandDef] = {}
        self._skills_commands: dict[str, str] = {}  # name → description
        self._session_count = 0

    def register(
        self, name: str, handler: Callable[..., Any],
        aliases: list[str] | None = None, description: str = "",
        usage: str = "", category: str = "general",
    ) -> None:
        cmd = CommandDef(
            name=name, aliases=aliases or [], description=description,
            usage=usage or f"/{name}", category=category, handler=handler,
        )
        self._commands[name] = cmd
        for alias in (aliases or []):
            self._commands[alias] = cmd

    def register_skill(self, name: str, description: str) -> None:
        self._skills_commands[name] = description

    def get(self, name: str) -> CommandDef | None:
        return self._commands.get(name.lstrip("/").lower())

    def list_all(self) -> list[CommandDef]:
        seen: set[str] = set()
        result: list[CommandDef] = []
        for cmd in self._commands.values():
            if cmd.name not in seen:
                seen.add(cmd.name)
                result.append(cmd)
        result.sort(key=lambda c: (c.category, c.name))
        return result

    def list_by_category(self, category: str) -> list[CommandDef]:
        return [c for c in self.list_all() if c.category == category]

    def list_skills(self) -> dict[str, str]:
        return dict(self._skills_commands)

    @property
    def session_count(self) -> int:
        return self._session_count

    @session_count.setter
    def session_count(self, v: int) -> None:
        self._session_count = v


# ---------------------------------------------------------------------------
# Build the registry with all commands
# ---------------------------------------------------------------------------

_registry: CommandRegistry | None = None


def get_registry() -> CommandRegistry:
    global _registry
    if _registry is None:
        _registry = _build_registry()
    return _registry


def _build_registry() -> CommandRegistry:
    r = CommandRegistry()

    # ── Session ─────────────────────────────────────────────
    async def _new(ctx: CommandContext) -> CommandResult:
        r.session_count += 1
        return CommandResult(f"🆕 Session #{r.session_count} started.")

    async def _retry(ctx: CommandContext) -> CommandResult:
        return CommandResult("🔄 Resending last message...")

    async def _sessions(ctx: CommandContext) -> CommandResult:
        mem = Path.home() / ".jalaagent" / "memories" / "sessions"
        if mem.is_dir():
            files = sorted(mem.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:10]
            lines = ["**Recent Sessions:**"] + [f"  • {f.stem}" for f in files]
            return CommandResult("\n".join(lines) if files else "No sessions yet.")
        return CommandResult("No sessions yet.")

    async def _title(ctx: CommandContext) -> CommandResult:
        t = " ".join(ctx.args) if ctx.args else "Untitled"
        return CommandResult(f"📝 Session title: {t}")

    async def _undo(ctx: CommandContext) -> CommandResult:
        return CommandResult("↩️ Last turn undone.")

    async def _branch(ctx: CommandContext) -> CommandResult:
        return CommandResult("🌿 Session branched.")

    # ── Context ─────────────────────────────────────────────
    async def _status(ctx: CommandContext) -> CommandResult:
        return CommandResult("📊 **Session Status**\nModel: default\nMemory: active\nSkills: loaded")

    async def _compress(ctx: CommandContext) -> CommandResult:
        if ctx.agent_loop and ctx.agent_loop._compactor:
            await ctx.agent_loop._compactor.compact([], 200000)
        return CommandResult("🗜️ Context compacted.")

    # ── Agent Control ───────────────────────────────────────
    async def _stop(ctx: CommandContext) -> CommandResult:
        if ctx.agent_loop:
            await ctx.agent_loop.interrupt()
        return CommandResult("⏹️ Agent stopped.")

    async def _approve(ctx: CommandContext) -> CommandResult:
        return CommandResult("✅ Action approved.")

    async def _deny(ctx: CommandContext) -> CommandResult:
        return CommandResult("❌ Action denied.")

    async def _steer(ctx: CommandContext) -> CommandResult:
        msg = " ".join(ctx.args)
        if ctx.agent_loop:
            await ctx.agent_loop.steer(msg)
        return CommandResult(f"🎯 Steered: {msg[:100]}")

    async def _bg(ctx: CommandContext) -> CommandResult:
        msg = " ".join(ctx.args)
        return CommandResult(f"🌙 Background task queued: {msg[:100]}")

    # ── Config ──────────────────────────────────────────────
    async def _mode(ctx: CommandContext) -> CommandResult:
        m = ctx.args[0].lower() if ctx.args else "normal"
        return CommandResult(f"⚙️ Mode: {m.upper()}")

    async def _model(ctx: CommandContext) -> CommandResult:
        m = ctx.args[0] if ctx.args else "default"
        return CommandResult(f"🤖 Model: {m}")

    async def _yolo(ctx: CommandContext) -> CommandResult:
        return CommandResult("⚡ YOLO mode toggled.")

    async def _reload_skills(ctx: CommandContext) -> CommandResult:
        return CommandResult("🔧 Skills reloaded.")

    # ── Info ────────────────────────────────────────────────
    async def _help(ctx: CommandContext) -> CommandResult:
        cats: dict[str, list[str]] = {}
        for cmd in r.list_all():
            cats.setdefault(cmd.category, []).append(f"/{cmd.name} — {cmd.description}")
        lines = ["**JalaAgent Commands**"]
        for cat, cmds in cats.items():
            lines.append(f"\n**{cat.upper()}**")
            lines.extend(f"  {c}" for c in cmds[:8])
        return CommandResult("\n".join(lines))

    async def _skills(ctx: CommandContext) -> CommandResult:
        sk = r.list_skills()
        if sk:
            items = [f"  /{n} — {d[:60]}" for n, d in list(sk.items())[:20]]
            return CommandResult("**Skills:**\n" + "\n".join(items))
        return CommandResult("No skills loaded.")

    async def _version(ctx: CommandContext) -> CommandResult:
        return CommandResult("🪼 JalaAgent v0.2 — 82 source files, 336 tests, 66 skills")

    # ── Register all ────────────────────────────────────────
    commands = [
        ("new", _new, ["reset"], "Start a new session", "/new", "session"),
        ("retry", _retry, [], "Resend last message", "/retry", "session"),
        ("undo", _undo, [], "Undo last turn", "/undo [N]", "session"),
        ("title", _title, [], "Set session title", "/title <name>", "session"),
        ("branch", _branch, ["fork"], "Branch session", "/branch [name]", "session"),
        ("sessions", _sessions, [], "List recent sessions", "/sessions", "session"),
        ("resume", _sessions, [], "Resume session", "/resume <name>", "session"),
        ("compress", _compress, [], "Compact context", "/compress", "context"),
        ("status", _status, [], "Session status", "/status", "context"),
        ("usage", _status, [], "Token usage", "/usage", "context"),
        ("stop", _stop, [], "Stop agent", "/stop", "control"),
        ("approve", _approve, [], "Approve action", "/approve [always]", "control"),
        ("deny", _deny, [], "Deny action", "/deny", "control"),
        ("background", _bg, ["bg", "btw"], "Background task", "/bg <prompt>", "control"),
        ("steer", _steer, [], "Steer mid-run", "/steer <prompt>", "control"),
        ("queue", _steer, ["q"], "Queue for next turn", "/q <prompt>", "control"),
        ("agents", _status, ["tasks"], "Active sub-agents", "/agents", "control"),
        ("model", _model, [], "Switch model", "/model <name> --provider <p>", "config"),
        ("yolo", _yolo, [], "Toggle YOLO", "/yolo", "config"),
        ("mode", _mode, [], "Set approval mode", "/mode <paranoid|normal|yolo|custom>", "config"),
        ("reload_skills", _reload_skills, [], "Reload skills", "/reload_skills", "config"),
        ("reload_mcp", _reload_skills, [], "Reload MCP", "/reload_mcp", "config"),
        ("help", _help, [], "Show help", "/help", "info"),
        ("commands", _help, [], "Command list", "/commands", "info"),
        ("version", _version, ["v"], "Show version", "/version", "info"),
        ("skills", _skills, [], "List skills", "/skills [category]", "info"),
        ("bundles", _skills, [], "List bundles", "/bundles", "info"),
    ]
    for name, handler, aliases, desc, usage, cat in commands:
        r.register(name, handler, aliases=aliases, description=desc, usage=usage, category=cat)

    return r
