---
name: excalidraw
description: Create and edit Excalidraw diagrams — wireframes, flowcharts, whiteboard sketches
version: 1.0.0
author: JalaAgent (ported from Hermes)
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: ✏️
    provenance:
      source: hermes-agent
      original: excalidraw
---

# Excalidraw

Create hand-drawn style diagrams and wireframes using Excalidraw's JSON format.

## JSON Structure
```json
{
  "type": "excalidraw",
  "version": 2,
  "elements": [
    {"type": "rectangle", "x": 100, "y": 100, "width": 200, "height": 80, "strokeColor": "#1e1e1e", "backgroundColor": "#a5d8ff"},
    {"type": "text", "x": 140, "y": 120, "text": "User Service", "fontSize": 20},
    {"type": "arrow", "x": 300, "y": 140, "width": 100, "height": 0}
  ]
}
```

## When to Use
- System architecture sketches (rough, not precise)
- Wireframes (low-fidelity, fast iteration)
- Whiteboard-style explanations
- Collaborative diagramming

## Rules
- Use the hand-drawn aesthetic (don't fight it)
- Keep diagrams under 20 elements (split complex ones)
- Export as .excalidraw for editing, .png for sharing
- Always include labels on arrows
