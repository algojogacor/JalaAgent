---
name: architecture-diagram
description: System architecture diagrams via Mermaid, Excalidraw, or ASCII art
version: 1.0.0
author: JalaAgent (ported from Hermes)
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 🏗️
    provenance:
      source: hermes-agent
      original: architecture-diagram
---

# Architecture Diagram

Generate system architecture diagrams. Choose format by context.

## Formats
- **Mermaid**: Markdown docs, GitHub README, version-controlled
- **Excalidraw**: Collaborative whiteboarding, rough sketches
- **ASCII art**: Terminal, CLI output, code comments

## Mermaid Pattern
```mermaid
graph TB
    Client --> LB[Load Balancer]
    LB --> API1[API Server 1]
    LB --> API2[API Server 2]
    API1 --> Cache[(Redis)]
    API2 --> Cache
    API1 --> DB[(PostgreSQL)]
    API2 --> DB
```

## Rules
- Label every edge (what data flows?)
- Group by network boundary (public/private/internal)
- Max 12 nodes per diagram (split if larger)
- Always include legend for non-standard symbols
