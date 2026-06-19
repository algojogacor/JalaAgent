# Harness — Safe Coding Infrastructure

JalaAgent's 5-piece harness provides safety rails for autonomous operation.

## WorktreeIsolation
- Creates disposable git worktrees for safe agent execution
- Agent works in `.claude/worktrees/<name>/`
- Changes never touch main branch until explicitly committed
- Auto-cleanup on session end if no changes

## PlanMode
- Design-first workflow: explore → propose → approve → implement
- `<HARD-GATE>` blocks implementation before approval
- Plans saved as markdown in `~/.jalaagent/plans/`

## SandboxedShell
- Dangerous command detection: `rm -rf`, `curl | sh`, `chmod 777`
- Path scoping: restricts shell to allowed root directory
- Configurable timeout per command
- History tracking

## BackgroundTaskManager
- Submit long-running tasks without blocking the agent loop
- `npm install`, `cargo build`, `pytest` run as daemon tasks
- Max concurrent tasks configurable

## DiffEditor
- Safe file editing via unified diffs
- Drift detection: refuses edit if file changed since preview
- Atomic writes with temp file + rename
