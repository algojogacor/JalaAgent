# Changelog

All notable changes to JalaAgent.

## v2026.6.20 (2026-06-20)

### Added
- **Provider/model system overhaul** — Hermes-level `/model` command with interactive picker (Telegram + CLI)
- **Static model catalog** — 17 providers with curated model lists in `agent_core.model_catalog`
- **Live API model discovery** — `GET /v1/models` with 1-hour disk cache, auto-discovers new models
- **4-tier base_url resolution** — CLI flag → env var → config.yaml → static default per provider
- **`--base-url` CLI flag** — override API endpoint on the command line
- **Provider env var overrides** — `DASHSCOPE_BASE_URL`, `OPENAI_BASE_URL`, etc. for all 17 providers
- **Qwen dual-endpoint support** — China (`dashscope.aliyuncs.com`) + International (`dashscope-intl.aliyuncs.com`)
- **`/model --save`** — persist model switch to config.yaml
- **`/model --refresh`** — force cache bust + live API re-fetch
- **Model aliases** — `/model sonnet` → `claude-sonnet-4-6`, `/model ds` → `deepseek/deepseek-chat`
- **Telegram inline keyboard picker** — multi-step provider → model selection with pagination
- **CLI rich model select** — numbered prompts for provider → model selection

### Changed
- Universal provider cleaned of hardcoded PROVIDERS dict — now pure transport layer
- ProviderRouter expanded to 18 known providers with base_url chain support
- CLAUDE.md updated to enterprise-grade philosophy

## v2026.6.19 (2026-06-19)

### Added
- `jala config-show` — display current configuration
- `jala config-get <key>` — get config value by dot-notation key (e.g., `model.provider`)

### Fixed
- Provider imports now work from main.py (extracted path setup to `agent_core.paths`)
- `uv sync --all-packages` in README and quickstart documentation
- Skills count badge corrected to 65

## v2026.6.18 (2026-06-18)

### Added
- Initial release: 82 source files, ~14,000 lines Python
- 4-layer hybrid memory: file + sqlite-vec + dreaming + knowledge graph
- 67 bundled skills across 13 categories
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
