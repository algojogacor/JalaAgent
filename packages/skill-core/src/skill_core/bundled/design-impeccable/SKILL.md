---
name: design-impeccable
description: Production-grade frontend design authority with preflight gates, anti-slop manifesto, and OKLCH color system.
version: 1.0.0
author: JalaAgent (adapted from Hermes design-impeccable)
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: ✨
    provenance:
      source: hermes-agent
      original: design-impeccable
      category: creative
      ported: 2026-06-18
      adaptations: [removed Hermes-specific MCP references, added JalaAgent frontend-design integration]
---

# Design Impeccable

## Preflight Gates (MUST pass before any design work)
1. **Context**: Understand the product, audience, and goal
2. **Product**: Identify real assets (logos, screenshots, brand colors)
3. **Command**: Select design command (craft, shape, teach, document, etc.)
4. **Craft**: Generate the design
5. **Image**: Verify all images are real (not placeholder)
6. **Mutation**: Iterate based on feedback

## Anti-Slop Manifesto
ABSOLUTE BANS:
- No grey side-stripe borders (the #1 AI design tell)
- No gradient text on white backgrounds
- No glassmorphism without purpose
- No hero-metric template (big number + label)
- No identical card grids (every card same height with subtle shadow)
- No purple-to-blue gradients
- No Inter/Roboto/Arial as display fonts

## 22 Design Commands
craft, shape, teach, document, extract, critique, audit, polish, bolder, quieter, distill, harden, onboard, animate, colorize, typeset, layout, delight, overdrive, clarify, adapt, optimize, live

## OKLCH Color System
Use OKLCH for perceptually uniform color manipulation:
```css
--primary: oklch(0.6 0.2 250);    /* Blue accent */
--surface: oklch(0.98 0 0);       /* Near-white */
--text: oklch(0.2 0 0);           /* Near-black */
```
