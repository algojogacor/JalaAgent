---
name: sketch
description: SVG sketch and illustration generation — vector art, icons, spot illustrations
version: 1.0.0
author: JalaAgent (ported from Hermes)
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 🎨
    provenance:
      source: hermes-agent
      original: sketch
---

# Sketch — SVG Illustrations

Generate vector illustrations and icons as inline SVG. No external assets needed.

## SVG Patterns
- Use `<path>` for organic shapes, `<rect>`/`<circle>` for geometric
- Stroke-based illustrations (hand-drawn feel) vs fill-based (flat design)
- ViewBox 0 0 400 300 as default canvas
- Inline SVG works everywhere — HTML, React, Markdown

## Color Palette
```html
<svg viewBox="0 0 400 300" xmlns="http://www.w3.org/2000/svg">
  <circle cx="200" cy="150" r="80" fill="#a5d8ff" stroke="#1e1e1e" stroke-width="3"/>
  <text x="200" y="160" text-anchor="middle" font-family="sans-serif">Hello</text>
</svg>
```

## Rules
- Max 50 elements per illustration (keep it simple)
- Always include `xmlns` and `viewBox`
- Use semantic colors (not random)
- Export as .svg file, embed inline, or use as data URI
