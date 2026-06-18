---
name: design-md
description: Markdown-based design documentation — design specs, style guides, and component catalogs
version: 1.0.0
author: JalaAgent (ported from Hermes)
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 📝
    provenance:
      source: hermes-agent
      original: design-md
---

# Design.md — Markdown Design Documentation

Write design specs as markdown files. Git-trackable, diff-friendly, always up-to-date.

## Template Structure
```markdown
# Design: [Feature]

## Visual Reference
![mockup](mockup.png)

## Typography
- Headings: Space Grotesk Bold (24/30/36px)
- Body: Source Sans 3 (16px, 1.5 line-height)

## Colors
- Primary: oklch(0.6 0.2 250) (#2563eb)
- Surface: oklch(0.98 0 0) (#fafafa)

## Spacing
- Section padding: 64px
- Card padding: 24px
- Element gap: 16px

## Components
- Button: 44px height, 16px radius, primary fill
- Input: 44px height, 1px border, 8px radius
- Card: 16px radius, 1px border, subtle shadow
```

## Rules
- One DESIGN.md per feature/section
- Always include visual reference (screenshot or mockup)
- Keep values concrete (px, not "medium padding")
- Update DESIGN.md when code changes (they drift)
