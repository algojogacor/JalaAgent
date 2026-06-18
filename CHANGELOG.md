# Changelog

All notable changes to JalaAgent.

## v2026.6.18 (2026-06-18)

### Added
- Initial release: 82 source files, ~14,000 lines Python
- 4-layer hybrid memory: file + sqlite-vec + dreaming + knowledge graph
- 77 bundled skills across 13 categories
- 46 unified slash commands (CLI + Telegram)
- Universal provider covering 16+ OpenAI-compatible APIs
- Gateway mode: `jala gateway` runs CLI + Telegram simultaneously
- API server: `jala serve` exposes Anthropic-compatible endpoint
- 5-piece harness: worktree isolation, sandboxed shell, diff editor, plan mode, bg tasks
- 4-layer policy pipeline: PARANOID, NORMAL, YOLO, CUSTOM
- Credential pool with rotation and strategies (random/priority/round_robin)
- Claude Code integration as JalaAgent tool
- 10 design skills pack (removable via `rm -rf design-pack/`)
- Full Hermes-parity config.yaml with 8 blocks, 50+ sections
- 336 tests, pyright clean
