---
name: open-design
description: Open-source design systems — design tokens, component libraries, Figma-to-code pipelines
version: 1.0.0
author: JalaAgent (ported from Hermes)
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 📐
    provenance:
      source: hermes-agent
      original: open-design
---

# Open Design

Build with open-source design systems. No reinventing buttons.

## Recommended Systems
- **shadcn/ui** — Copy-paste React components, Radix primitives
- **Tailwind UI** — Utility-first, production-ready patterns
- **Radix Primitives** — Unstyled, accessible headless components
- **Geist** (Vercel) — Minimal, modern design language

## Design Tokens Pattern
```css
:root {
  --color-primary: oklch(0.6 0.2 250);
  --color-surface: oklch(0.98 0 0);
  --radius-sm: 4px;
  --radius-md: 8px;
  --space-unit: 4px;
}
```

## Rules
- Always use design tokens (never hardcode values)
- Choose one system, don't mix (shadcn + MUI = conflict)
- Customize tokens for brand, keep component behavior
- Accessibility must pass WCAG AA minimum
