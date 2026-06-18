# Architecture

JalaAgent is structured as a monorepo with 3 core packages, 5 extension categories, and a CLI layer.

## Package Map

```
jalaagent/
├── packages/           — Core logic, no external deps on channels/providers
│   ├── memory-core/    — 4-layer hybrid memory (9 modules)
│   ├── skill-core/     — Skill system + 77 bundled skills (5 modules)
│   └── agent-core/     — Loop, registry, harness, policy (14 modules)
├── extensions/         — Swappable, provider/channel-specific
│   ├── providers/      — Universal (16 APIs) + Anthropic + Ollama + Gemini
│   ├── channels/       — CLI (rich) + Telegram (PTB v21)
│   ├── mcp/            — Lazy-loading MCP server manager
│   └── browser/        — Playwright automation
├── cli/                — jala entry point
└── tests/              — 336 tests (unit + integration)
```

## Data Flow

```
User Input → CLI/Telegram Channel → AgentLoop
  ├── MemoryRetriever: KNN → FTS → KG → MEMORY.md scan
  ├── SkillLoader: inject <available_skills> XML
  ├── Provider: stream LLM response
  ├── ToolRegistry: execute tool calls (10 tools)
  └── BackgroundTaskManager: self-improvement daemon
```

## Key Design Decisions

- **Pure asyncio**: No threading anywhere
- **Frozen snapshot pattern**: Memory captured at session start, never mid-session
- **Provider agnostic**: Single universal provider for 16+ APIs
- **Separation of concerns**: agent-core depends on nothing channel/provider-specific
- **Transparent files**: All memory is readable plain text + SQLite
