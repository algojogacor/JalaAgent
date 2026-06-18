---
name: micro-interactions
description: CSS/JS micro-interactions for UI polish — hover states, transitions, loading animations
version: 1.0.0
author: JalaAgent (ported from Hermes)
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: ✨
    provenance:
      source: hermes-agent
      original: micro-interactions
---

# Micro-Interactions

Small animations that make UI feel responsive and polished.

## Button Hover
```css
.btn {
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.btn:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.15); }
.btn:active { transform: translateY(0); }
```

## Skeleton Loading
```css
.skeleton {
  background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
}
```

## Rules
- Duration: 150-300ms (fast = responsive)
- Easing: ease-out for entering, ease-in for exiting
- Always respect `@media (prefers-reduced-motion: reduce)`
- One animation per element (multiple = chaotic)
