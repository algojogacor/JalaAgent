---
name: animated-gradient-mesh
description: CSS animated gradient mesh backgrounds with smooth color transitions
version: 1.0.0
author: JalaAgent (ported from Hermes)
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 🌈
    provenance:
      source: hermes-agent
      original: animated-gradient-mesh
---

# Animated Gradient Mesh

CSS-only animated gradient meshes. No JavaScript, pure CSS.

## Basic Template
```css
@keyframes gradient-shift {
  0% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
  100% { background-position: 0% 50%; }
}
.mesh {
  background: linear-gradient(-45deg, #ee7752, #e73c7e, #23a6d5, #23d5ab);
  background-size: 400% 400%;
  animation: gradient-shift 15s ease infinite;
}
```

## Design Rules
- 3-5 colors maximum, use OKLCH for smooth transitions
- Duration 8-20s (slower = more elegant)
- Always include `@media (prefers-reduced-motion)` fallback
- Use as hero background, not body (too distracting)
