---
name: graphify
description: Turn any folder of files into a navigable knowledge graph with community detection and honest audit trail.
version: 1.0.0
author: JalaAgent (ported from Hermes)
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 🕸️
    provenance:
      source: hermes-agent
      original: graphify
      category: dev
      ported: 2026-06-18
---

# Graphify

## Overview
Transform any directory into an interactive knowledge graph. Extract entities, detect communities, tag every edge as EXTRACTED (regex), INFERRED (LLM), or AMBIGUOUS (uncertain).

## Process
1. **Scan**: Walk directory, read every file
2. **Extract**: Regex-based entity extraction (no LLM cost)
3. **Infer**: LLM identifies cross-document relationships
4. **Community**: Louvain/Leiden community detection
5. **Output**: Interactive HTML, GraphRAG-ready JSON, audit report

## Honest Audit Trail
Every edge in the graph gets a provenance tag:
- **EXTRACTED** — Regex pattern matched (high confidence)
- **INFERRED** — LLM identified relationship (medium confidence)
- **AMBIGUOUS** — Multiple possible interpretations (low confidence)

## Output Formats
1. `graph.html` — Interactive D3.js force-directed graph
2. `graph.json` — GraphRAG-compatible JSON with nodes and edges
3. `audit.md` — Human-readable report with statistics
4. `graph.cypher` — Neo4j-compatible import script

## Anti-Patterns
- Don't graph without audit trail (you need to know what's reliable)
- Don't use LLM for entity extraction when regex works (cost + latency)
- Don't treat inferred edges as facts (they're suggestions)
