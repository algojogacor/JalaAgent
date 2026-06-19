# JalaAgent — CLAUDE.md

> This file is the authoritative context for Claude Code working on JalaAgent.
> Read this fully before writing any code, creating any file, or making any architectural decision.
> When in doubt, refer back here.

---

## What is JalaAgent?

JalaAgent is an open-source, self-improving AI agent with a hybrid memory system.
It is designed to be better than both Hermes-Agent and OpenClaw by taking the best
from each and solving their known weaknesses.

**Not** a chatbot wrapper. **Not** a coding copilot. A persistent personal agent
that lives on your machine, remembers everything across sessions, improves its own
skills over time, and reaches you via Telegram or CLI.

**Target users:** Developers and power users who want a fully autonomous personal agent
they can trust, inspect, and extend.

---

## Core Philosophy

1. **Transparent by default** — Everything the agent knows is readable as plain files.
   No opaque databases that the user cannot inspect or edit manually.

2. **Self-improving** — After every session, the agent reviews what happened and
   improves its own memory and skills automatically. User can approve or bypass.

3. **Lightweight first** — Lazy loading everywhere. Nothing runs at startup unless
   needed. MCP servers are loaded on-demand, not at boot.

4. **Production-ready** — Proper error handling, tests, type hints, schema validation.
   Not a weekend hack.

5. **Cross-platform** — Works on Windows (primary dev target), Linux, macOS, Termux.
   No platform-specific assumptions in core logic.

---

## Architecture Overview

```
jalaagent/
├── packages/
│   ├── agent-core/          # Core agent loop, provider abstraction, tool registry
│   ├── memory-core/         # Hybrid memory: file + sqlite-vec + RAG
│   └── skill-core/          # Skill system: SKILL.md, workshop, hub
├── extensions/
│   ├── channels/
│   │   ├── telegram/        # Telegram channel (v1)
│   │   └── cli/             # CLI channel (v1)
│   ├── providers/
│   │   ├── anthropic/       # Claude models
│   │   ├── openai/          # OpenAI-compatible
│   │   ├── ollama/          # Local models
│   │   └── openrouter/      # OpenRouter
│   └── mcp/                 # Optional MCP servers (lazy-loaded)
├── cli/                     # Entry point: `jala` command
├── tests/                   # pytest-asyncio test suite
├── CLAUDE.md                # This file
├── PRD.md                   # Product requirements
└── pyproject.toml           # uv-managed dependencies
```

---

## Memory System (THE core differentiator)

JalaAgent uses a **three-layer hybrid memory** system:

### Layer 1 — Raw File Storage (OpenClaw-inspired)
- Human-readable, git-trackable, manually editable
- `~/.jalaagent/memories/MEMORY.md` — curated facts, always readable
- `~/.jalaagent/memories/USER.md` — user profile and preferences
- `~/.jalaagent/memories/sessions/YYYY-MM-DD.jsonl` — raw session transcripts

### Layer 2 — SQLite + Vector (Hermes + sqlite-vec)
- `~/.jalaagent/db/memory.db` with tables:
  - `episodes` — chunked session content with metadata
  - `embeddings` — vectors via sqlite-vec (Qwen3-Embedding via Ollama)
  - `facts` — atomic facts extracted from MEMORY.md
  - `skills` — indexed skill content for retrieval
- Sync is **lazy** — runs in background during idle, not during active chat

### Layer 3 — Dreaming Pipeline (OpenClaw-inspired)
- Cron job (default: 3 AM daily)
- Phases: Light Sleep → REM → Deep Sleep
- Light Sleep: scan recent sessions for new signals
- REM: find cross-session patterns, deduplicate
- Deep Sleep: promote high-confidence facts to MEMORY.md
- All changes go through user approval gate (unless YOLO mode)

### Retrieval Flow
```
Query
  → sqlite-vec KNN search (primary)
  → FTS5 keyword fallback
  → MEMORY.md linear scan (last resort)
  → inject as <memory-context> into system prompt
```

### Key Design Decisions (do not change without discussion)
- **Frozen snapshot pattern** (from Hermes): memory is captured at session start
  and NEVER updated mid-session in the prompt. Preserves Anthropic prompt cache.
- **Drift detection**: if MEMORY.md is modified externally during a session,
  agent detects and refuses to write (prevents corruption).
- **Untrusted result wrapping**: web/MCP tool results are wrapped in
  `<untrusted_tool_result>` tags to prevent prompt injection.

---

## Tool System

### Approval Modes
```python
class ApprovalMode(Enum):
    PARANOID = "paranoid"  # Ask for everything
    NORMAL   = "normal"    # Ask only for destructive actions
    YOLO     = "yolo"      # Bypass all approvals
    CUSTOM   = "custom"    # Per-category rules via config
```

YOLO mode must show a clear warning during setup. It is a valid mode.

### Policy Pipeline (4 layers, simplified from OpenClaw's 8)
```
global → agent → category → sender
```
- `deny` always wins over `allow`
- Categories: `file_read`, `file_write`, `file_delete`, `shell_exec`,
  `network_get`, `network_post`, `messaging_send`, `memory_write`

### Default CUSTOM config
```yaml
approval:
  mode: normal
  rules:
    file_read: auto
    file_write: auto
    file_delete: ask
    shell_exec: ask
    network_get: auto
    network_post: ask
    messaging_send: ask
    memory_write: auto
```

### MCP Loading
- **Lazy** — MCP servers are NOT started at agent boot
- Started on first tool call that requires them
- Killed after idle timeout (default: 5 minutes)
- Base MCP servers shipped by default: `filesystem`, `shell`, `fetch`

### Tool Features (implement all)
- **Fuzzy name repair**: case-insensitive, snake_case/camelCase, difflib 0.7 cutoff
- **Loop detection**: repeated identical calls, no-progress patterns → warning then hard stop
- **Overflow handling**: results > 50K chars → persist to temp file, return path instead
- **Untrusted wrapping**: web/MCP/browser results → `<untrusted_tool_result>` XML

---

## Skill System

### Format
Standard `SKILL.md` with YAML frontmatter compatible with agentskills.io:

```yaml
---
name: skill-name
description: What this skill does
version: 1.0.0
author: username
license: MIT
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 🔧
    requires:
      bins: []
      env: []
---
```

### Workshop Pipeline (AI-assisted skill generation)
```
propose → security_scan → review (user) → apply / reject
```
- Agent proposes new skill after completing a complex task
- Security scanner runs on proposed SKILL.md
- User reviews diff before apply (unless YOLO mode)
- Failed writes automatically roll back

### Sources (priority order)
1. Bundled (shipped with JalaAgent)
2. User-installed (`~/.jalaagent/skills/`)
3. Plugin-provided (via extensions)
4. Extra dirs (user-configured)

### Self-improvement
- After every session, background task evaluates if existing skills should be updated
- Only writes to skills index, not skill files themselves, unless user approves
- Skills are content-addressed: `sha256:<prefix>` per SKILL.md for cache-aware re-reading

---

## Agent Runtime

### Core Loop
- Python 3.12+ with **native asyncio** — no thread bridges, no `run_coroutine_threadsafe`
- Streaming-first: all LLM calls use streaming by default
- Max iterations: configurable (default: 100)
- Two-tier queue: steering (mid-run injection) + followup (post-stop injection)

### Provider Abstraction
All providers implement `BaseProvider`:
- `stream_completion()` → async generator of chunks
- `count_tokens()` → int
- `convert_tools()` → provider-native format

Supported in v1: `anthropic`, `openai`, `ollama`, `openrouter`

### Context Management
- Compaction triggered at configurable token threshold
- 5-phase compression: prune old tool results → deduplicate → protect recent → budget tail → summarize middle
- Summary format: Goal, Completed Actions, Active State, Key Decisions, Remaining Work
- Session stored as JSONL (append-only)
- Tree-based session navigation: sessions are trees, not linear (enables branching)

### Error Handling
Classify every API error into one of these categories:
- `rate_limit` → jittered exponential backoff
- `auth_error` → rotate credential pool
- `content_policy` → try fallback provider once, never retry same prompt
- `context_too_long` → trigger compaction then retry
- `timeout` → TTFB watchdog, kill and retry
- `transient` → exponential backoff up to 3 attempts

### Sub-agents
- `delegate_task` tool spawns isolated child agent
- Max depth: 1 by default (no nested sub-agents unless configured)
- Max concurrent sub-agents: 15
- Each sub-agent gets restricted toolset and separate iteration budget

---

## Channels

### v1: Telegram + CLI

**Telegram:**
- Library: `python-telegram-bot` (async)
- One bot per user (self-hosted)
- Commands: `/new`, `/reset`, `/mode`, `/skills`, `/memory`, `/approve`, `/reject`
- Inline approval buttons for NORMAL/PARANOID mode

**CLI:**
- Library: `typer` + `rich`
- Multiline input support
- Streaming output with animated spinner
- Slash command autocomplete

### Channel Interface
All channels implement `BaseChannel`:
```python
class BaseChannel:
    async def send_message(self, text: str) -> None: ...
    async def send_approval_request(self, action: Action) -> ApprovalResult: ...
    async def on_message(self, handler: MessageHandler) -> None: ...
```

---

## Tech Stack (locked, do not change without strong reason)

| Component | Choice | Version |
|-----------|--------|---------|
| Language | Python | 3.12+ |
| Package manager | uv | latest |
| Async | asyncio native | — |
| Vector DB | sqlite-vec | latest |
| Embedding | Qwen3-Embedding via Ollama | — |
| File watch | watchfiles | latest |
| Validation | pydantic v2 | 2.x |
| CLI | typer + rich | latest |
| Telegram | python-telegram-bot | 21.x |
| Testing | pytest + pytest-asyncio | latest |
| MCP SDK | mcp (official Anthropic SDK) | latest |
| Linting | ruff | latest |
| Type checking | pyright | latest |

---

## File Conventions

- All async functions must have `async def` — no sync wrappers around async
- All public functions must have type hints
- All pydantic models go in `models.py` within their package
- Config files use YAML (not TOML, not JSON) for user-facing config
- Internal config uses pydantic Settings with env var support
- Test files mirror source structure: `tests/packages/memory-core/test_retrieval.py`
- Every module has `__init__.py` exporting its public API

---

## What NOT to Do

- Do NOT use `threading` in new code — use `asyncio` tasks
- Do NOT start MCP servers at agent boot — lazy load only
- Do NOT write to MEMORY.md mid-session — frozen snapshot pattern
- Do NOT skip the security scan in the skill workshop pipeline
- Do NOT hardcode any API keys — always use env vars or credential store
- Do NOT use `print()` — use `rich.console` or `logging`
- Do NOT skip tests for core packages (agent-core, memory-core, skill-core)
- Do NOT make `agent-core` depend on any channel or provider — keep it pure
- Do NOT commit code without updating relevant docs — docs/ must always match code

---

## Docs Sync Rule (MANDATORY)

The `docs/` directory must ALWAYS stay in sync with the codebase.
This is non-negotiable — outdated docs are worse than no docs.

### When docs MUST be updated:

Any time you make changes that affect these areas, update the 
corresponding doc file IN THE SAME COMMIT:

| Changed | Update |
|---------|--------|
| New slash command added | `docs/commands.md` |
| New CLI subcommand | `docs/quickstart.md` + `docs/user-guide.md` |
| Memory system change | `docs/memory.md` |
| New skill added/removed | `docs/skills.md` |
| New provider added | `docs/providers.md` |
| Config section added | `docs/configuration.md` |
| API endpoint added/changed | `docs/api-reference.md` |
| Harness feature changed | `docs/harness.md` |
| Architecture change | `docs/architecture.md` |
| New feature (any) | `docs/INDEX.md` + `docs/roadmap.md` |
| CHANGELOG.md | Every commit that adds/changes user-facing features |

### Before every commit, verify:

- [ ] Did I add a feature? → docs updated
- [ ] Did I change a command? → docs updated  
- [ ] Did I change config? → docs updated
- [ ] Is CHANGELOG.md updated with this change?
- [ ] Does docs/INDEX.md reflect current feature count?

### Doc format rules:

- Every doc must have a "Last updated: v2026.X.X" line at the top
- CHANGELOG.md uses date-based versioning: `v2026.M.D`
- Commands in docs must match EXACTLY what's in commands.py
- Config examples in docs must match EXACTLY what config.py generates
- Never document a feature that doesn't exist in code yet
  (mark as `[planned]` or `[v2026.X.X]` instead)

### CHANGELOG.md format:

```
## v2026.6.19 (2026-06-19)

### Added
- Brief description of new feature

### Fixed
- Brief description of fix

### Changed
- Brief description of change
```

### Self-check before finishing any task:

Before marking a task complete, Claude Code must ask itself:
"Did any of my changes affect user-facing behavior, commands, 
config, or architecture?"

If YES → docs must be updated before the task is done.
If NO → explicitly state why docs don't need updating.

This rule applies to ALL tasks, no exceptions.

---

## Current Status

> v2026.6.19 — 4 phases complete. 82 source files, 13,264 lines, 374 tests.

### Completed ✅

| Package | Modules | Notes |
|---------|---------|-------|
| `packages/memory-core` | 9 modules | 4-layer memory: file + sqlite-vec + dreaming + knowledge graph |
| `packages/skill-core` | 5 modules + 65 skills | Loader, scanner, workshop, hub (stub), bundled skills |
| `packages/agent-core` | 12 modules | Loop, registry, harness, policy, credentials, commands, repair, sanitize, compaction, errors, models, core_tools |
| `extensions/providers` | Universal + 4 | Universal (16 APIs), Anthropic, Ollama, OpenAI, Gemini |
| `extensions/channels` | CLI + Telegram | Both with BaseChannel protocol + unified slash commands |
| `extensions/mcp` | manager.py | Lazy-loading MCP server lifecycle |
| `extensions/browser` | tool.py | Playwright automation |
| `cli/` | main.py, setup.py, config.py | `jala` entry point + setup wizard |
| `tests/` | 25 test files | 374 tests passing |

### Features

- **Gateway mode**: `jala gateway` runs CLI + Telegram simultaneously ✅
- **Slash commands**: 46 unified commands (session, context, control, config, info) ✅
- **Versioning**: date-based `v2026.6.19` with git hash display ✅
- **Fail-closed approval**: auto-deny on timeout, CLI defaults to No ✅
- **65 bundled skills**: 12 categories, 8 JalaAgent-exclusive ✅
- **4-layer memory**: file + sqlite-vec + dreaming pipeline + knowledge graph ✅
- **Universal provider**: 1 adapter covers 16+ OpenAI-compatible APIs ✅
- **Policy pipeline**: 4-layer (global→agent→category→sender), 4 modes ✅
- **Harness**: worktree isolation, plan mode, sandboxed shell, bg tasks, diff editor ✅
- **Credential pool**: rotation, cooldown, health checking ✅

### Next

| Priority | What | Where |
|----------|------|-------|
| 1 | Gateway hardening (banner, session tracking, graceful shutdown improvements) | `cli/src/jala/main.py` |
| 2 | MCP server wiring (tools actually callable through registry) | `extensions/mcp/manager.py` |
| 3 | Documentation (README, API docs, user guide) | repo root |
| 4 | Real-world testing + telemetry | `tests/` |
| 5 | `jala version` + `jala auth` CLI subcommands | `cli/src/jala/main.py` |

---

## Decisions (Answered)

- Embedding dimension: **1024** (qwen3:0.6b)
- Dreaming pipeline: **asyncio task** (not subprocess)
- Default approval mode: **NORMAL**
- Versioning: **date-based** `v2026.M.D`
- Credential storage: **auth.json** + **config.yaml** (no .env)