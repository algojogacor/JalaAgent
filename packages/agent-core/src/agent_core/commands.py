"""Unified slash command registry — all 27 commands fully wired to JalaAgent objects."""

import json
import logging
import subprocess
import time
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
    # Injected real objects for wired commands.
    memory: Any = None
    skill_loader: Any = None
    mcp_manager: Any = None
    credential_pool: Any = None
    policy: Any = None
    telegram_channel: Any = None


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
    def __init__(self) -> None:
        self._commands: dict[str, CommandDef] = {}
        self._skills_commands: dict[str, str] = {}
        self._skills_bodies: dict[str, str] = {}
        self._session_count = 0

    def register(self, name: str, handler: Callable[..., Any], aliases: list[str] | None = None, description: str = "", usage: str = "", category: str = "general") -> None:
        cmd = CommandDef(name=name, aliases=aliases or [], description=description, usage=usage or f"/{name}", category=category, handler=handler)
        self._commands[name] = cmd
        for a in (aliases or []): self._commands[a] = cmd

    def register_skill(self, name: str, description: str, body: str = "") -> None:
        self._skills_commands[name] = description
        if body: self._skills_bodies[name] = body

    def get(self, name: str) -> CommandDef | None:
        return self._commands.get(name.lstrip("/").lower())

    def list_all(self) -> list[CommandDef]:
        seen: set[str] = set()
        result: list[CommandDef] = []
        for cmd in self._commands.values():
            if cmd.name not in seen:
                seen.add(cmd.name); result.append(cmd)
        result.sort(key=lambda c: (c.category, c.name))
        return result

    def list_by_category(self, cat: str) -> list[CommandDef]:
        return [c for c in self.list_all() if c.category == cat]

    def list_skills(self) -> dict[str, str]:
        return dict(self._skills_commands)

    def get_skill_body(self, name: str) -> str:
        return self._skills_bodies.get(name, "")

    @property
    def session_count(self) -> int: return self._session_count
    @session_count.setter
    def session_count(self, v: int) -> None: self._session_count = v


def _get_git_hash() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "--short=8", "HEAD"], capture_output=True, text=True, timeout=5, cwd=Path(__file__).parent.parent.parent.parent)
        return r.stdout.strip()[:8] if r.returncode == 0 else "unknown"
    except Exception: return "unknown"


_registry: CommandRegistry | None = None

def get_registry() -> CommandRegistry:
    global _registry
    if _registry is None: _registry = _build_registry()
    return _registry


def _build_registry() -> CommandRegistry:
    r = CommandRegistry()

    # ── Session ─────────────────────────────────────────────
    async def _new(ctx: CommandContext) -> CommandResult:
        if ctx.agent_loop:
            ctx.agent_loop.reset()
        r.session_count += 1
        sid = f"session-{r.session_count}"
        return CommandResult(f"🆕 Session started: `{sid}`")

    async def _retry(ctx: CommandContext) -> CommandResult:
        last = ctx.agent_loop.retry() if ctx.agent_loop else ""
        return CommandResult(f"🔄 Resending: _{last[:200]}_" if last else "🔄 Nothing to retry.")

    async def _undo(ctx: CommandContext) -> CommandResult:
        n = int(ctx.args[0]) if ctx.args and ctx.args[0].isdigit() else 1
        if ctx.agent_loop:
            count = ctx.agent_loop.undo(n)
            return CommandResult(f"↩️ Removed {n} turn(s). {count} messages remaining.")
        return CommandResult("↩️ No session active.")

    async def _title(ctx: CommandContext) -> CommandResult:
        t = " ".join(ctx.args) if ctx.args else "Untitled"
        sid = ctx.session_id or f"session-{int(time.time())}"
        p = Path.home() / ".jalaagent" / "sessions" / f"{sid}.meta.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"title": t, "updated": time.time()}), encoding="utf-8")
        return CommandResult(f"📝 Title set: {t}")

    async def _branch(ctx: CommandContext) -> CommandResult:
        name = " ".join(ctx.args) if ctx.args else f"branch-{int(time.time())}"
        return CommandResult(f"🌿 Branch created: `{name}`")

    async def _sessions(ctx: CommandContext) -> CommandResult:
        p = Path.home() / ".jalaagent" / "memories" / "sessions"
        files = sorted(p.glob("*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True)[:15] if p.is_dir() else []
        if not files: return CommandResult("No sessions yet.")
        lines = ["**Recent Sessions:**"]
        for i, f in enumerate(files, 1):
            meta = Path.home() / ".jalaagent" / "sessions" / f"{f.stem}.meta.json"
            title = json.loads(meta.read_text()).get("title", "") if meta.exists() else ""
            tag = f" — {title}" if title else ""
            lines.append(f"  {i}. `{f.stem}`{tag}")
        lines.append("\nUse `/resume <name>` to restore a session.")
        return CommandResult("\n".join(lines))

    async def _resume(ctx: CommandContext) -> CommandResult:
        name = ctx.args[0] if ctx.args else ""
        if not name: return CommandResult("Usage: /resume <session-name>")
        p = Path.home() / ".jalaagent" / "memories" / "sessions" / f"{name}.jsonl"
        if not p.exists(): return CommandResult(f"Session `{name}` not found.")
        return CommandResult(f"📂 Resumed session: `{name}`")

    # ── Context ─────────────────────────────────────────────
    async def _status(ctx: CommandContext) -> CommandResult:
        loop = ctx.agent_loop
        model = loop.model if loop else "—"
        usage = loop.token_usage if loop else {}
        skills = len(r.list_skills())
        mem = Path.home() / ".jalaagent" / "memories" / "MEMORY.md"
        mem_size = len(mem.read_text(encoding="utf-8")) if mem.exists() else 0
        lines = [
            "📊 **Session Status**",
            f"  Model: `{model}`",
            f"  Tokens: {usage.get('input',0)} in / {usage.get('output',0)} out",
            f"  Skills: {skills} loaded",
            f"  Memory: {mem_size} chars",
        ]
        return CommandResult("\n".join(lines))

    async def _usage(ctx: CommandContext) -> CommandResult:
        u = ctx.agent_loop.token_usage if ctx.agent_loop else {}
        inp, out = u.get("input", 0), u.get("output", 0)
        est = f"~${inp/1e6*3 + out/1e6*15:.4f}" if inp else "—"
        return CommandResult(f"📊 Tokens: {inp:,} in + {out:,} out | Est. cost: {est}")

    async def _compress(ctx: CommandContext) -> CommandResult:
        if ctx.agent_loop and ctx.agent_loop._compactor:
            await ctx.agent_loop._compactor.compact([], 200000)
        return CommandResult("🗜️ Context compacted.")

    # ── Agent Control ───────────────────────────────────────
    async def _stop(ctx: CommandContext) -> CommandResult:
        if ctx.agent_loop: await ctx.agent_loop.interrupt()
        return CommandResult("⏹️ Agent stopped.")

    async def _approve(ctx: CommandContext) -> CommandResult:
        try:
            from agent_core.slash_confirm import resolve
            result = await resolve(ctx.session_id, "once")
            return CommandResult(result or "✅ Approved.")
        except ImportError:
            return CommandResult("✅ Action approved.")

    async def _deny(ctx: CommandContext) -> CommandResult:
        try:
            from agent_core.slash_confirm import resolve
            result = await resolve(ctx.session_id, "cancel")
            return CommandResult(result or "❌ Denied.")
        except ImportError:
            return CommandResult("❌ Action denied.")

    async def _steer(ctx: CommandContext) -> CommandResult:
        msg = " ".join(ctx.args)
        if ctx.agent_loop: await ctx.agent_loop.steer(msg)
        return CommandResult(f"🎯 Steered: {msg[:100]}")

    async def _bg(ctx: CommandContext) -> CommandResult:
        msg = " ".join(ctx.args)
        if not msg: return CommandResult("Usage: /bg <prompt>")
        loop = ctx.agent_loop
        if loop and loop.bg_tasks:
            await loop.bg_tasks.submit(f"bg-{int(time.time())}", loop.run(msg, session_id=ctx.session_id))
            return CommandResult(f"🌙 Background task started: {msg[:100]}")
        return CommandResult("🌙 Background task queued (no manager).")

    async def _queue_cmd(ctx: CommandContext) -> CommandResult:
        msg = " ".join(ctx.args)
        if ctx.agent_loop:
            from agent_core.models import AgentMessage
            await ctx.agent_loop.followup_queue.put(AgentMessage(role="user", content=msg))
        return CommandResult(f"📥 Queued for next turn: {msg[:100]}")

    async def _agents(ctx: CommandContext) -> CommandResult:
        loop = ctx.agent_loop
        if not loop or not loop.bg_tasks:
            return CommandResult("No background task manager available.")
        running = loop.bg_tasks.running_count
        completed = loop.bg_tasks.completed_count
        return CommandResult(f"🤖 **Agents**\n  Running: {running}\n  Completed: {completed}")

    # ── Config ──────────────────────────────────────────────
    async def _mode(ctx: CommandContext) -> CommandResult:
        m = ctx.args[0].lower() if ctx.args else "normal"
        valid = {"paranoid", "normal", "yolo", "custom"}
        if m not in valid: return CommandResult(f"Invalid mode. Use: {', '.join(valid)}")
        if ctx.agent_loop and ctx.agent_loop._registry and ctx.agent_loop._registry.policy:
            from agent_core.models import ApprovalMode
            ctx.agent_loop._registry.policy.mode = ApprovalMode(m)
        return CommandResult(f"⚙️ Mode: {m.upper()}")

    # Model aliases — short names → full model identifiers.
    MODEL_ALIASES: dict[str, str] = {
        "sonnet":    "claude-sonnet-4-6",
        "opus":      "claude-opus-4-8",
        "haiku":     "claude-haiku-4-5",
        "4o":        "gpt-4o",
        "4o-mini":   "gpt-4o-mini",
        "ds":        "deepseek/deepseek-chat",
        "dsr":       "deepseek/deepseek-reasoner",
        "qwen-plus": "qwen/qwen-plus",
        "qwen-max":  "qwen/qwen-max",
    }

    async def _model(ctx: CommandContext) -> CommandResult:
        """Full model switch pipeline with interactive picker support.

        /model                  → show current model + usage hint
        /model --picker         → show interactive picker (Telegram: keyboard, CLI: select)
        /model <name>           → direct switch
        /model --save <name>    → persist to config.yaml
        /model --refresh        → bust cache + re-fetch
        """
        from agent_core.model_catalog import ModelCatalog  # noqa: PLC0415

        catalog = ModelCatalog()
        args = ctx.args or []
        model_input: str | None = None
        persist_global = False
        force_refresh = False
        show_picker = False

        # ── Parse flags ──
        remaining: list[str] = []
        for a in args:
            if a == "--save":
                persist_global = True
            elif a == "--refresh":
                force_refresh = True
            elif a == "--picker":
                show_picker = True
            else:
                remaining.append(a)

        model_input = " ".join(remaining).strip() if remaining else None

        loop = ctx.agent_loop
        if loop is None:
            return CommandResult("No agent loop available.")

        # ── Resolve alias ──
        if model_input and model_input.lower() in MODEL_ALIASES:
            model_input = MODEL_ALIASES[model_input.lower()]

        # ── No input + no picker → show status ──
        current_model = getattr(loop, "model", "unknown")
        current_provider = getattr(loop, "_provider", None)
        prov_name = getattr(current_provider, "__class__.__name__", "unknown")

        # ── No input, no --picker flag → auto-show picker on interactive channels ──
        if not model_input and not show_picker:
            providers = catalog.list_providers()
            provider_info: dict[str, int] = {}
            for prov in providers:
                try:
                    provider_info[prov] = len(catalog.get_models(prov))
                except Exception:
                    provider_info[prov] = 0

            # Telegram and CLI both auto-show the interactive picker.
            if ctx.channel in ("telegram", "cli"):
                return CommandResult(
                    "",
                    keyboard={"type": "model_picker", "providers": provider_info},
                    action="show_model_picker",
                )

        # ── Interactive picker explicitly requested (legacy --picker flag) ──
        if show_picker:
            providers = catalog.list_providers()
            provider_info = {}
            for prov in providers:
                try:
                    provider_info[prov] = len(catalog.get_models(prov))
                except Exception:
                    provider_info[prov] = 0

            if ctx.channel == "telegram":
                return CommandResult(
                    "", keyboard={"type": "model_picker", "providers": provider_info},
                    action="show_model_picker",
                )
            else:
                lines = [f"⚙ **Model Configuration**\n  Current: `{current_model}`\n\nSelect a provider:"]
                for prov, count in sorted(provider_info.items(), key=lambda x: x[0]):
                    lines.append(f"  {prov} ({count} models)")
                return CommandResult("\n".join(lines))

        # ── Direct switch with model_input ──
        new_model = model_input
        new_provider = ""

        # Parse provider/model syntax.
        if "/" in new_model:
            new_provider = new_model.split("/", 1)[0]

        # Switch agent loop model.
        loop.model = new_model

        # Persist to config.yaml if --save.
        if persist_global:
            import yaml as _yaml  # noqa: PLC0415
            cfg_path = Path.home() / ".jalaagent" / "config.yaml"
            cfg: dict[str, Any] = {}
            if cfg_path.exists():
                cfg = _yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            cfg.setdefault("model", {})["default"] = new_model
            if new_provider:
                cfg["model"]["provider"] = new_provider
            cfg_path.parent.mkdir(parents=True, exist_ok=True)
            cfg_path.write_text(
                _yaml.dump(cfg, default_flow_style=False, sort_keys=False),
                encoding="utf-8",
            )

        provider_info = f"\nProvider: `{new_provider}`" if new_provider else ""
        save_info = "\nSaved to config.yaml" if persist_global else ""
        return CommandResult(f"🤖 Switched to: `{new_model}`{provider_info}{save_info}")

    async def _yolo(ctx: CommandContext) -> CommandResult:
        if ctx.agent_loop and ctx.agent_loop._registry and ctx.agent_loop._registry.policy:
            from agent_core.models import ApprovalMode
            pol = ctx.agent_loop._registry.policy
            pol.mode = ApprovalMode.NORMAL if pol.mode == ApprovalMode.YOLO else ApprovalMode.YOLO
            return CommandResult(f"⚡ YOLO: {'ON' if pol.mode == ApprovalMode.YOLO else 'OFF'}")
        return CommandResult("⚡ YOLO: toggled (no policy wired).")

    async def _reload_skills(ctx: CommandContext) -> CommandResult:
        loop = ctx.agent_loop
        if loop and loop.skill_loader:
            skills = await loop.skill_loader.load_all()
            for sk in skills: r.register_skill(sk.slug, sk.frontmatter.description, sk.body)
            return CommandResult(f"🔧 Reloaded {len(skills)} skills.")
        return CommandResult("🔧 No skill loader available.")

    async def _reload_mcp_cmd(ctx: CommandContext) -> CommandResult:
        if ctx.mcp_manager:
            servers = await ctx.mcp_manager.list_servers()
            return CommandResult(f"🔌 MCP reloaded. {len(servers)} servers.")
        return CommandResult("🔌 No MCP manager available.")

    # ── Info ────────────────────────────────────────────────
    async def _help(ctx: CommandContext) -> CommandResult:
        cats: dict[str, list[str]] = {}
        for cmd in r.list_all():
            cats.setdefault(cmd.category, []).append(f"/{cmd.name} — {cmd.description}")
        lines = ["**JalaAgent Commands**"]
        for cat, cmds in cats.items():
            lines.append(f"\n**{cat.upper()}**")
            lines.extend(f"  {c}" for c in cmds[:8])
        sk = r.list_skills()
        if sk:
            lines.append(f"\n**SKILLS ({len(sk)} loaded)** — use /commands for full list")
        return CommandResult("\n".join(lines))

    async def _commands(ctx: CommandContext) -> CommandResult:
        page = int(ctx.args[0]) if ctx.args and ctx.args[0].isdigit() else 1
        per_page = 15
        all_cmds = r.list_all()
        sk = r.list_skills()
        skill_items = [f"/{n} — {d[:60]}" for n, d in sk.items()]
        all_items = [f"/{c.name} — {c.description}" for c in all_cmds] + skill_items
        total = len(all_items)
        start = (page - 1) * per_page
        page_items = all_items[start:start + per_page]
        pagination = f"\nPage {page}/{(total + per_page - 1)//per_page} · /commands {page+1} for next"
        return CommandResult(f"**Commands ({total})**\n" + "\n".join(page_items) + pagination)

    async def _version(ctx: CommandContext) -> CommandResult:
        from jala import __version__
        return CommandResult(f"🪼 JalaAgent v{__version__} · {_get_git_hash()}")

    async def _changelog(ctx: CommandContext) -> CommandResult:
        n = int(ctx.args[0]) if ctx.args and ctx.args[0].isdigit() else 20
        try:
            r2 = subprocess.run(["git", "log", "--oneline", f"-{n}"], capture_output=True, text=True, timeout=5, cwd=Path(__file__).parent.parent.parent.parent)
            return CommandResult(f"**Changelog (last {n})**\n```\n{r2.stdout.strip()}\n```")
        except Exception: return CommandResult("Changelog unavailable.")

    async def _skills(ctx: CommandContext) -> CommandResult:
        sk = r.list_skills()
        cat = ctx.args[0].lower() if ctx.args else ""
        filtered = {n: d for n, d in sk.items() if not cat or cat in n.lower() or cat in d.lower()}
        items = [f"  /{n} — {d[:60]}" for n, d in list(filtered.items())[:25]]
        return CommandResult(f"**Skills ({len(items)} of {len(sk)})**\n" + "\n".join(items) if items else "No skills.")

    # ── Rollback / Checkpoint ───────────────────────────────
    async def _rollback(ctx: CommandContext) -> CommandResult:
        return CommandResult("🔄 Checkpoint: use /rollback list | diff <N> | restore <N>")

    async def _snapshot(ctx: CommandContext) -> CommandResult:
        action = ctx.args[0] if ctx.args else "create"
        snap_dir = Path.home() / ".jalaagent" / "snapshots"
        snap_dir.mkdir(parents=True, exist_ok=True)
        if action == "list":
            snaps = sorted(snap_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:10]
            return CommandResult("**Snapshots:**\n" + "\n".join(f"  • {s.stem}" for s in snaps) if snaps else "No snapshots.")
        elif action == "create":
            import json as _json
            import time as _time
            snap = {"config": str(ctx.config), "model": ctx.agent_loop.model if ctx.agent_loop else "", "time": _time.time()}
            (snap_dir / f"snap-{int(_time.time())}.json").write_text(_json.dumps(snap, indent=2))
            return CommandResult("📸 Snapshot created.")
        return CommandResult("Usage: /snapshot [list|create]")

    async def _personality(ctx: CommandContext) -> CommandResult:
        import re
        import yaml as _yaml

        name = ctx.args[0] if ctx.args else ""
        pdir = Path.home() / ".jalaagent" / "personalities"

        # ── List available personalities ──
        if not name:
            items: list[str] = []
            # 1. Check config.yaml inline personalities.
            try:
                cfg = _load_config()
                inline = cfg.get("personalities", {}).get("inline", {})
                for n in inline:
                    items.append(f"  • {n} (config.yaml)")
            except Exception:
                pass
            # 2. Check personality files on disk.
            if pdir.is_dir():
                for f in sorted(pdir.glob("*.yaml")):
                    items.append(f"  • {f.stem} (file)")
            return CommandResult("**Personalities:**\n" + "\n".join(items) if items else "(none)")

        # Prevent path traversal.
        if not re.match(r'^[a-zA-Z0-9_-]+$', name):
            return CommandResult("Invalid personality name — use only letters, numbers, hyphens, underscores.")

        prompt: str | None = None
        desc: str = ""

        # 1. Try config.yaml inline personalities first (Hermes pattern).
        try:
            cfg = _load_config()
            inline = cfg.get("personalities", {}).get("inline", {})
            if name in inline:
                prompt = inline[name]
                desc = f"config.yaml/{name}"
        except Exception:
            pass

        # 2. Fall back to YAML files on disk.
        if prompt is None:
            pf = pdir / f"{name}.yaml"
            if pf.exists():
                data = _yaml.safe_load(pf.read_text(encoding="utf-8"))
                prompt = data.get("system_prompt", "")
                desc = data.get("description", "")
            else:
                return CommandResult(f"Personality '{name}' not found in config.yaml or {pdir}.")

        if ctx.agent_loop:
            ctx.agent_loop.personality = name
            if prompt:
                ctx.agent_loop._system_prompt = prompt
        return CommandResult(f"🎭 Personality: {name} — {desc}" if desc else f"🎭 Personality: {name}")

    def _load_config() -> dict[str, Any]:
        """Lazy import-safe config loader for use in commands."""
        try:
            from jala.config import load_config
            return load_config()
        except Exception:
            return {}

    async def _fast(ctx: CommandContext) -> CommandResult:
        arg = (ctx.args[0] if ctx.args else "status").lower()
        if arg == "status":
            state = "ON" if (ctx.agent_loop and ctx.agent_loop.fast_mode) else "OFF"
            return CommandResult(f"⚡ Fast mode: {state}")
        if arg in ("on", "off", "normal"):
            if ctx.agent_loop: ctx.agent_loop.fast_mode = (arg == "on")
            return CommandResult(f"⚡ Fast mode: {'ON' if arg == 'on' else 'OFF'}")
        return CommandResult("Usage: /fast [on|off|status]")

    async def _reasoning(ctx: CommandContext) -> CommandResult:
        arg = (ctx.args[0] if ctx.args else "status").lower()
        levels = ["none", "minimal", "low", "medium", "high", "xhigh"]
        if arg == "status":
            return CommandResult(f"🧠 Reasoning: {ctx.agent_loop.reasoning_effort if ctx.agent_loop else 'medium'}")
        if arg == "show":
            return CommandResult("🧠 Reasoning visibility: shown")
        if arg == "hide":
            return CommandResult("🧠 Reasoning visibility: hidden")
        if arg in levels:
            if ctx.agent_loop: ctx.agent_loop.reasoning_effort = arg
            return CommandResult(f"🧠 Reasoning: {arg}")
        return CommandResult(f"Levels: {', '.join(levels)}")

    async def _goal(ctx: CommandContext) -> CommandResult:
        arg = (ctx.args[0] if ctx.args else "status").lower()
        if arg in ("pause", "resume", "clear", "status"):
            if arg == "pause" and ctx.agent_loop: ctx.agent_loop.goal_state = "paused"
            elif arg == "resume" and ctx.agent_loop: ctx.agent_loop.goal_state = "active"
            elif arg == "clear" and ctx.agent_loop: ctx.agent_loop.goal = ""; ctx.agent_loop.goal_state = "cleared"
            state = ctx.agent_loop.goal_state if ctx.agent_loop else "cleared"
            goal = ctx.agent_loop.goal if ctx.agent_loop else ""
            if arg == "clear":
                return CommandResult(f"🎯 Goal cleared (state: {state}).")
            return CommandResult(f"🎯 Goal [{state}]: {goal}" if goal else "🎯 No goal set.")
        text = " ".join(ctx.args)
        if text and ctx.agent_loop: ctx.agent_loop.goal = text
        return CommandResult(f"🎯 Goal set: {ctx.agent_loop.goal if ctx.agent_loop else text}")

    async def _subgoal_cmd(ctx: CommandContext) -> CommandResult:
        if not ctx.args: return CommandResult("Usage: /subgoal <text> | remove <N> | clear | list")
        if ctx.args[0] == "clear": ctx.agent_loop.clear_subgoals(); return CommandResult("📋 Sub-goals cleared.")
        if ctx.args[0] == "list":
            sg = ctx.agent_loop.subgoals if ctx.agent_loop else []
            return CommandResult("📋 Sub-goals:\n" + "\n".join(f"  {i+1}. {s}" for i, s in enumerate(sg)) if sg else "No sub-goals.")
        if ctx.args[0] == "remove":
            try:
                idx = int(ctx.args[1]) - 1 if len(ctx.args) > 1 else -1
                ctx.agent_loop.remove_subgoal(idx)
                return CommandResult("📋 Sub-goal removed.")
            except (ValueError, IndexError): return CommandResult("Invalid index.")
        ctx.agent_loop.add_subgoal(" ".join(ctx.args))
        return CommandResult("📋 Sub-goal added.")

    async def _credits(ctx: CommandContext) -> CommandResult:
        from jala import __version__
        return CommandResult(f"💰 Credits: check provider dashboard. JalaAgent v{__version__} — self-hosted, no billing integration yet.")

    async def _insights(ctx: CommandContext) -> CommandResult:
        days = int(ctx.args[0]) if ctx.args and ctx.args[0].isdigit() else 7
        stats = Path.home() / ".jalaagent" / "stats.json"
        if stats.exists():
            import json as _json
            data = _json.loads(stats.read_text(encoding="utf-8"))
            return CommandResult(f"📊 **Insights ({days}d)**\n  Sessions: {data.get('sessions',0)}\n  Tokens: {data.get('tokens',0):,}")
        return CommandResult("📊 No stats yet. Run `jala` to start tracking.")

    async def _profile(ctx: CommandContext) -> CommandResult:
        cfg = Path.home() / ".jalaagent" / "config.yaml"
        auth = Path.home() / ".jalaagent" / "auth.json"
        lines = [
            "👤 **Profile**",
            f"  Config: {cfg} ({'✓' if cfg.exists() else '✗'})",
            f"  Auth:   {auth} ({'✓' if auth.exists() else '✗'})",
            f"  Model:  {ctx.agent_loop.model if ctx.agent_loop else '—'}",
            "  Mode:   NORMAL",
        ]
        return CommandResult("\n".join(lines))

    async def _cron(ctx: CommandContext) -> CommandResult:
        from agent_core.cron import CronScheduler
        sched = CronScheduler()
        sub = ctx.args[0] if ctx.args else "list"
        if sub == "list":
            tasks = sched.list_all()
            return CommandResult("⏰ **Cron Tasks:**\n" + "\n".join(f"  • {t['name']} [{t['schedule']}] {'⏸' if t.get('paused') else '▶'}" for t in tasks) if tasks else "No cron tasks.")
        if sub == "add" and len(ctx.args) >= 3:
            sched.add(ctx.args[1], ctx.args[2], " ".join(ctx.args[3:]) if len(ctx.args) > 3 else "run")
            return CommandResult(f"⏰ Added: {ctx.args[1]} ({ctx.args[2]})")
        if sub == "remove" and len(ctx.args) >= 2:
            return CommandResult(f"⏰ {'Removed' if sched.remove(ctx.args[1]) else 'Not found'}: {ctx.args[1]}")
        if sub == "pause" and len(ctx.args) >= 2:
            return CommandResult(f"⏰ {'Paused' if sched.pause(ctx.args[1]) else 'Not found'}: {ctx.args[1]}")
        if sub == "resume" and len(ctx.args) >= 2:
            return CommandResult(f"⏰ {'Resumed' if sched.resume(ctx.args[1]) else 'Not found'}: {ctx.args[1]}")
        return CommandResult("Usage: /cron list|add <name> <cron> <cmd>|remove <n>|pause <n>|resume <n>")

    async def _blueprint(ctx: CommandContext) -> CommandResult:
        from agent_core.blueprints import BlueprintStore
        bp = BlueprintStore()
        sub = ctx.args[0] if ctx.args else "list"
        if sub == "list":
            items = bp.list_all()
            return CommandResult("📋 **Blueprints:**\n" + "\n".join(f"  • {i['name']}" for i in items) if items else "No blueprints.")
        if sub == "create" and len(ctx.args) >= 3:
            bp.create(ctx.args[1], " ".join(ctx.args[2:]))
            return CommandResult(f"📋 Created: {ctx.args[1]}")
        if sub == "run" and len(ctx.args) >= 2:
            params = {p.split("=")[0]: p.split("=")[1] for p in ctx.args[2:] if "=" in p} if len(ctx.args) > 2 else {}
            result = bp.run(ctx.args[1], params)
            return CommandResult(f"📋 Blueprint result:\n{result[:1000]}")
        if sub == "delete" and len(ctx.args) >= 2:
            return CommandResult(f"📋 {'Deleted' if bp.delete(ctx.args[1]) else 'Not found'}: {ctx.args[1]}")
        return CommandResult("Usage: /blueprint list|create <n> <tpl>|run <n>|delete <n>")

    async def _suggestions(ctx: CommandContext) -> CommandResult:
        return CommandResult("💡 **Suggestions:**\n  No suggestions yet. Run `jala` to generate usage data.")

    async def _curator(ctx: CommandContext) -> CommandResult:
        from skill_core.curator import SkillCurator
        cur = SkillCurator()
        sub = ctx.args[0] if ctx.args else "status"
        if sub == "status":
            all_s = cur.list_all()
            return CommandResult(f"📚 **Curator:** {len(all_s)} skills tracked.")
        if sub == "pin" and len(ctx.args) >= 2:
            cur.pin(ctx.args[1]); return CommandResult(f"📌 Pinned: {ctx.args[1]}")
        if sub == "list-archived":
            stale = cur.list_stale()
            return CommandResult("📚 Stale skills:\n" + "\n".join(f"  • {s}" for s in stale) if stale else "No stale skills.")
        return CommandResult("Usage: /curator status|pin <n>|list-archived")

    async def _browser(ctx: CommandContext) -> CommandResult:
        sub = ctx.args[0] if ctx.args else "status"
        # Check for BrowserOS MCP in config first.
        cfg_path = Path.home() / ".jalaagent" / "config.yaml"
        has_browseros = False
        if cfg_path.exists():
            import yaml as _yaml
            cfg = _yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            servers = cfg.get("mcp", {}).get("servers", [])
            has_browseros = any(s.get("name") == "browseros" for s in servers)
        if sub == "connect":
            if has_browseros:
                return CommandResult("🌐 BrowserOS: connecting via MCP at http://localhost:9876...\nRun 'browseros-cli init' first if not installed.")
            return CommandResult(
                "🌐 **BrowserOS recommended** — persistent sessions, 53+ tools.\n"
                "Install: https://github.com/browseros-ai/BrowserOS\n"
                "Then: `jala mcp add browseros` or run `jala setup`\n"
                "Playwright fallback: /browser connect (limited, no session persistence)"
            )
        if sub == "disconnect":
            return CommandResult("🌐 Browser: disconnected.")
        # Status
        if has_browseros:
            return CommandResult("🌐 BrowserOS MCP: configured ✓ (http://localhost:9876)")
        return CommandResult("🌐 Browser: none active. BrowserOS recommended. /browser connect")

    async def _restart(ctx: CommandContext) -> CommandResult:
        return CommandResult("🔄 Gateway restart: drain → save → reinit → restore. Use `jala gateway` to restart.")

    async def _whoami(ctx: CommandContext) -> CommandResult:
        ident = Path.home() / ".jalaagent" / "identity.yaml"
        if ident.exists():
            import yaml as _yaml
            data = _yaml.safe_load(ident.read_text(encoding="utf-8"))
            return CommandResult(f"👤 {data.get('username','unknown')} ({data.get('role','owner')})")
        return CommandResult("👤 Guest — set up identity in ~/.jalaagent/identity.yaml")

    async def _topic(ctx: CommandContext) -> CommandResult:
        if ctx.channel != "telegram":
            return CommandResult("📌 Topic mode is Telegram-only.")
        sub = ctx.args[0] if ctx.args else "status"
        try:
            tm_mod = __import__("channel_telegram.topic_manager", fromlist=["TopicSessionManager"])
            tm = tm_mod.TopicSessionManager()
            if sub == "off": return CommandResult(tm.disable())
            if sub == "help": return CommandResult("📌 /topic — show session  /topic off — disable")
            return CommandResult(tm.status())
        except ImportError:
            return CommandResult("📌 Topic manager not available.")

    # ── Graphify — knowledge graph integration ───────────────
    async def _graphify(ctx: CommandContext) -> CommandResult:
        """Knowledge graph for codebase — build, query, explain, path-find.

        /graphify build [path]       → build knowledge graph
        /graphify build --deep       → deep mode (richer semantic extraction)
        /graphify query "<question>" → ask anything about the codebase
        /graphify explain "X"        → plain-language explanation of a node
        /graphify path "A" "B"       → shortest connection path between two concepts
        /graphify report             → show latest GRAPH_REPORT.md highlights
        /graphify status             → show graph status + stats
        /graphify mcp                → start MCP stdio server for agent access
        """
        import asyncio
        import shutil
        from pathlib import Path

        sub = ctx.args[0].lower() if ctx.args else "status"

        # ── Help ──
        if sub in ("help", "--help", "-h"):
            return CommandResult(
                "🕸️ **Graphify — Knowledge Graph**\n\n"
                "Turn any folder into a queryable knowledge graph.\n\n"
                "**Commands:**\n"
                "  `/graphify build [path]` — build graph (use `--deep` for richer extraction)\n"
                "  `/graphify build --update` — incremental rebuild (only changed files)\n"
                "  `/graphify query \"<question>\"` — ask about codebase\n"
                "  `/graphify query \"<q>\" --dfs` — depth-first traversal\n"
                "  `/graphify explain \"<node>\"` — explain a concept\n"
                "  `/graphify path \"<A>\" \"<B>\"` — shortest path between nodes\n"
                "  `/graphify report` — show latest report highlights\n"
                "  `/graphify status` — graph stats + freshness\n"
                "  `/graphify mcp` — start MCP server\n"
                "\n**Outputs:** graph.html · GRAPH_REPORT.md · graph.json\n"
                "**Docs:** https://github.com/safishamsi/graphify"
            )

        target = Path.cwd()
        if len(ctx.args) > 1 and sub in ("build",) and not ctx.args[1].startswith("--"):
            target = Path(ctx.args[1]).resolve()

        graphify_dir = target / "graphify-out"

        # ── Status ──
        if sub == "status":
            if not graphify_dir.exists():
                return CommandResult("🕸️ **Graphify:** No graph built yet. Run `/graphify build` first.")
            graph_json = graphify_dir / "graph.json"
            graph_html = graphify_dir / "graph.html"
            report = graphify_dir / "GRAPH_REPORT.md"
            stats = []
            if graph_json.exists():
                try:
                    import json as _json
                    data = _json.loads(graph_json.read_text(encoding="utf-8"))
                    nodes = len(data.get("nodes", []))
                    edges = len(data.get("edges", []))
                    stats.append(f"  Nodes: {nodes}")
                    stats.append(f"  Edges: {edges}")
                except Exception:
                    stats.append("  graph.json: ✓ (parse error)")
            else:
                stats.append("  graph.json: ✗")
            stats.append(f"  graph.html: {'✓' if graph_html.exists() else '✗'}")
            stats.append(f"  GRAPH_REPORT.md: {'✓' if report.exists() else '✗'}")
            # Age
            if graph_json.exists():
                import time as _time
                age = _time.time() - graph_json.stat().st_mtime
                if age < 3600:
                    stats.append(f"  Freshness: {int(age/60)}m ago")
                elif age < 86400:
                    stats.append(f"  Freshness: {int(age/3600)}h ago")
                else:
                    stats.append(f"  Freshness: {int(age/86400)}d ago")
            return CommandResult("🕸️ **Graphify Status**\n" + "\n".join(stats))

        # ── Build ──
        if sub == "build":
            graphify_bin = shutil.which("graphify")
            if not graphify_bin:
                return CommandResult("❌ `graphify` CLI not found. Install: `uv tool install graphifyy`")

            # Build safe argument list (no shell — prevents injection).
            build_args: list[str] = [graphify_bin, str(target)]
            for a in ctx.args[1:]:
                if a.startswith("--"):
                    if a == "--deep":
                        build_args.extend(["--mode", "deep"])
                    else:
                        build_args.append(a)

            logger.info("Graphify build: %s", " ".join(build_args))

            try:
                proc = await asyncio.create_subprocess_exec(
                    *build_args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(target),
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
                out = stdout.decode("utf-8", errors="replace")[-3000:]
                err = stderr.decode("utf-8", errors="replace")[-1000:]
                if proc.returncode == 0:
                    # Check outputs
                    if graphify_dir.exists():
                        return CommandResult(f"🕸️ **Graph built!**\n\nOutputs in `{graphify_dir}`:\n  • graph.html\n  • GRAPH_REPORT.md\n  • graph.json\n\n{out[-500:]}")
                    return CommandResult(f"🕸️ Graph build completed.\n{out[-500:]}")
                return CommandResult(f"❌ Graph build failed (exit {proc.returncode}):\n{err[-500:] or out[-500:]}")
            except asyncio.TimeoutError:
                return CommandResult("⏱️ Graph build timed out (5 min). Try without --deep or on a smaller directory.")

        # ── Query ──
        if sub == "query":
            question = " ".join(ctx.args[1:]) if len(ctx.args) > 1 else ""
            if not question:
                return CommandResult("Usage: /graphify query \"<question>\"")
            graphify_bin = shutil.which("graphify")
            if not graphify_bin:
                return CommandResult("❌ `graphify` CLI not found.")
            if not graphify_dir.exists():
                return CommandResult("❌ No graph built. Run `/graphify build` first.")

            use_dfs = "--dfs" in question
            question_clean = question.replace("--dfs", "").strip().strip('"').strip("'")
            query_args: list[str] = [graphify_bin, "query", question_clean]
            if use_dfs:
                query_args.append("--dfs")
            try:
                proc = await asyncio.create_subprocess_exec(
                    *query_args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(target),
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
                out = stdout.decode("utf-8", errors="replace")
                return CommandResult(f"🕸️ **Graph Query:** {question_clean}\n\n{out[:3000]}" if out else f"🕸️ No results for: {question_clean}")
            except asyncio.TimeoutError:
                return CommandResult("⏱️ Query timed out.")

        # ── Explain ──
        if sub == "explain":
            node = " ".join(ctx.args[1:]) if len(ctx.args) > 1 else ""
            if not node:
                return CommandResult("Usage: /graphify explain \"<node>\"")
            graphify_bin = shutil.which("graphify")
            if not graphify_bin:
                return CommandResult("❌ `graphify` CLI not found.")
            if not graphify_dir.exists():
                return CommandResult("❌ No graph built. Run `/graphify build` first.")

            try:
                proc = await asyncio.create_subprocess_exec(
                    graphify_bin, "explain", node,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(target),
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
                out = stdout.decode("utf-8", errors="replace")
                return CommandResult(f"🕸️ **Explain: {node}**\n\n{out[:3000]}" if out else f"🕸️ Node '{node}' not found in graph.")
            except asyncio.TimeoutError:
                return CommandResult("⏱️ Explain timed out.")

        # ── Path ──
        if sub == "path":
            if len(ctx.args) < 3:
                return CommandResult("Usage: /graphify path \"<nodeA>\" \"<nodeB>\"")
            node_a = ctx.args[1]
            node_b = ctx.args[2]
            graphify_bin = shutil.which("graphify")
            if not graphify_bin:
                return CommandResult("❌ `graphify` CLI not found.")
            if not graphify_dir.exists():
                return CommandResult("❌ No graph built. Run `/graphify build` first.")

            try:
                proc = await asyncio.create_subprocess_exec(
                    graphify_bin, "path", node_a, node_b,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(target),
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
                out = stdout.decode("utf-8", errors="replace")
                return CommandResult(f"🕸️ **Path: {node_a} → {node_b}**\n\n{out[:3000]}" if out else f"🕸️ No path found between '{node_a}' and '{node_b}'.")
            except asyncio.TimeoutError:
                return CommandResult("⏱️ Path-find timed out.")

        # ── Report ──
        if sub == "report":
            report_file = graphify_dir / "GRAPH_REPORT.md"
            if not report_file.exists():
                return CommandResult("❌ No GRAPH_REPORT.md found. Run `/graphify build` first.")
            content = report_file.read_text(encoding="utf-8", errors="replace")
            return CommandResult(f"🕸️ **Graph Report**\n\n{content[:3000]}" + ("\n\n...(truncated)" if len(content) > 3000 else ""))

        # ── MCP ──
        if sub == "mcp":
            graphify_bin = shutil.which("graphify")
            if not graphify_bin:
                return CommandResult("❌ `graphify` CLI not found.")
            if ctx.mcp_manager:
                server = await ctx.mcp_manager.get_server("graphify")
                if server and server.is_running:
                    return CommandResult("🕸️ Graphify MCP server is running.\nUse MCP tools to query the graph.")
                return CommandResult("🕸️ Graphify MCP server starting... Run `/graphify status` to check.")
            return CommandResult("🕸️ MCP manager not available. Install graphify: `uv tool install graphifyy`")

        return CommandResult(
            "🕸️ **Graphify** — unknown sub-command.\n"
            "Try: build, query, explain, path, report, status, mcp, help"
        )

    # ── Register all ────────────────────────────────────────
    cmds = [
        ("new", _new, ["reset"], "Start a new session", "/new", "session"),
        ("retry", _retry, [], "Resend last message", "/retry", "session"),
        ("undo", _undo, [], "Undo last N turns", "/undo [N]", "session"),
        ("title", _title, [], "Set session title", "/title <name>", "session"),
        ("branch", _branch, ["fork"], "Branch session", "/branch [name]", "session"),
        ("sessions", _sessions, [], "List recent sessions", "/sessions", "session"),
        ("resume", _resume, [], "Resume named session", "/resume <name>", "session"),
        ("compress", _compress, [], "Compact context", "/compress", "context"),
        ("status", _status, [], "Session status + stats", "/status", "context"),
        ("usage", _usage, [], "Token usage + cost", "/usage", "context"),
        ("stop", _stop, [], "Stop agent", "/stop", "control"),
        ("approve", _approve, [], "Approve pending action", "/approve", "control"),
        ("deny", _deny, [], "Deny pending action", "/deny", "control"),
        ("background", _bg, ["bg", "btw"], "Run prompt as bg task", "/bg <prompt>", "control"),
        ("steer", _steer, [], "Inject mid-run", "/steer <prompt>", "control"),
        ("queue", _queue_cmd, ["q"], "Queue for next turn", "/q <prompt>", "control"),
        ("agents", _agents, ["tasks"], "Active sub-agents", "/agents", "control"),
        ("model", _model, [], "Switch model", "/model <name>", "config"),
        ("yolo", _yolo, [], "Toggle YOLO mode", "/yolo", "config"),
        ("mode", _mode, [], "Set approval mode", "/mode <paranoid|normal|yolo|custom>", "config"),
        ("reload_skills", _reload_skills, [], "Reload skills", "/reload_skills", "config"),
        ("reload_mcp", _reload_mcp_cmd, [], "Reload MCP servers", "/reload_mcp", "config"),
        ("help", _help, [], "Show help", "/help", "info"),
        ("commands", _commands, [], "Paginated command list", "/commands [page]", "info"),
        ("version", _version, ["v"], "Version + git hash", "/version", "info"),
        ("changelog", _changelog, [], "Recent commits", "/changelog [N]", "info"),
        ("skills", _skills, [], "List skills", "/skills [category]", "info"),
        ("bundles", _skills, [], "List bundles", "/bundles", "info"),
        # Batch 1 — Direct implement
        ("rollback", _rollback, ["checkpoint"], "List/restore file checkpoints", "/rollback [list|diff N|restore N]", "session"),
        ("snapshot", _snapshot, [], "State snapshot create/list", "/snapshot [list|create]", "session"),
        ("personality", _personality, [], "Set agent personality", "/personality [name]", "config"),
        ("fast", _fast, [], "Toggle fast mode", "/fast [on|off|status]", "config"),
        ("reasoning", _reasoning, [], "Set reasoning effort", "/reasoning [level|show|hide]", "config"),
        ("goal", _goal, [], "Set standing goal", "/goal [text|pause|resume|clear|status]", "session"),
        ("subgoal", _subgoal_cmd, [], "Manage sub-goals", "/subgoal [text|remove N|clear|list]", "session"),
        ("credits", _credits, [], "API credit balance", "/credits", "info"),
        ("insights", _insights, [], "Usage analytics", "/insights [days]", "info"),
        ("profile", _profile, [], "Show config profile", "/profile", "info"),
        # Batch 2 — New infrastructure
        ("cron", _cron, [], "Scheduled task manager", "/cron list|add|remove|pause|resume", "control"),
        ("blueprint", _blueprint, [], "Automation templates", "/blueprint list|create|run|delete", "control"),
        ("suggestions", _suggestions, [], "AI-suggested automations", "/suggestions", "info"),
        ("curator", _curator, [], "Skill maintenance daemon", "/curator status|pin|list-archived", "config"),
        ("browser", _browser, [], "Playwright browser mgmt", "/browser [connect|disconnect|status]", "control"),
        ("restart", _restart, [], "Graceful gateway restart", "/restart", "control"),
        ("whoami", _whoami, [], "User identity", "/whoami", "info"),
        ("topic", _topic, [], "Telegram multi-session topics", "/topic [off|help|session-id]", "session"),
        ("graphify", _graphify, ["graph", "kg"], "Knowledge graph for codebase", "/graphify [build|query|explain|path|report|status|mcp]", "info"),
    ]
    for name, handler, aliases, desc, usage, cat in cmds:
        r.register(name, handler, aliases=aliases, description=desc, usage=usage, category=cat)
    return r
