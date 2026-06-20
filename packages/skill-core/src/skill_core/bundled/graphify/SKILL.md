---
name: graphify
description: Turn any folder of files into a queryable knowledge graph with community detection and honest audit trail. Backed by the graphify CLI (safishamsi/graphify).
version: 2.0.0
author: JalaAgent (ported from Hermes, now backed by real graphify CLI)
license: MIT
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 🕸️
    requires:
      bins: [graphify]
      env: []
    provenance:
      source: safishamsi/graphify
      original: graphify
      category: dev
      ported: 2026-06-18
      updated: 2026-06-20
      backend: graphifyy v0.8.44 (PyPI)
      cli: graphify
      mcp: graphify --mcp
---

# Graphify — Knowledge Graph for JalaAgent

Backed by [safishamsi/graphify](https://github.com/safishamsi/graphify) — the open-source
codebase-to-knowledge-graph tool (69k+ stars, YC S26).

## Overview
Transform any directory into an interactive knowledge graph. Extract entities via tree-sitter
AST parsing (36 languages), detect communities via Leiden clustering, tag every edge as
EXTRACTED (regex/parser), INFERRED (LLM), or AMBIGUOUS (uncertain).

## Quick Start

```bash
# Install the CLI (one-time)
uv tool install graphifyy

# Then use in JalaAgent:
/graphify build .                    # build graph for current directory
/graphify build . --deep             # deep mode — richer semantic extraction
/graphify query "how does auth work?" # ask about the codebase
/graphify explain "BaseProvider"      # explain a concept
/graphify path "Auth" "Database"     # shortest path between two concepts
/graphify status                      # graph stats + freshness
/graphify report                      # show latest GRAPH_REPORT.md
/graphify mcp                         # start graphify as MCP server
```

## Process
1. **Scan**: Walk directory, respect `.gitignore` and `.graphifyignore`
2. **AST Extract**: Code files parsed locally via tree-sitter (36 languages, zero API calls)
3. **Semantic Extract**: Docs/PDFs/images sent to configured LLM backend
4. **Graph Build**: Entities as nodes, relationships as edges, confidence-tagged
5. **Community Detect**: Leiden clustering for node grouping
6. **Output**: `graph.html` (interactive), `GRAPH_REPORT.md` (highlights), `graph.json` (queryable)

## Honest Audit Trail
Every edge in the graph gets a provenance tag:
- **EXTRACTED** — Pattern/parser matched (high confidence)
- **INFERRED** — LLM identified relationship (medium confidence)
- **AMBIGUOUS** — Multiple possible interpretations (low confidence)

## Output Formats
1. `graph.html` — Interactive browser-based graph visualization
2. `GRAPH_REPORT.md` — God nodes, surprising connections, design rationale, suggested questions
3. `graph.json` — Full structured graph for querying without re-reading files
4. SVG, GraphML, Obsidian vault, Neo4j, FalkorDB (via flags)

## Privacy
- Code is always processed locally (tree-sitter) — never leaves your machine
- Only docs/PDFs/images require LLM API calls
- No telemetry, no analytics, no usage tracking

## Anti-Patterns
- Don't graph without audit trail (you need to know what's reliable)
- Don't use LLM for entity extraction when tree-sitter works (cost + latency)
- Don't treat inferred edges as facts (they're suggestions)
- Don't commit `graphify-out/cache/` to git (add to .gitignore)

## JalaAgent Integration
- `/graphify` slash command — full CLI wrapper in JalaAgent
- MCP server — registered in JalaAgent's MCP manager (`graphify` server)
- PreToolUse hooks — Claude Code auto-consults graph before answering codebase questions
- Auto-rebuild hooks — rebuilds graph after code changes
