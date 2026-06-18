---
name: visual-design
description: Create distinctive SVG and HTML artifacts. Anti-generic, bold typography, intentional color. No AI-slop defaults.
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 🎨
---

# Visual Design

## Overview
Create production-quality visual artifacts (SVG, HTML/CSS, diagrams). Every design must be distinctive and intentional. No generic "AI aesthetic" output.

## Process
1. State the vibe in 3 adjectives (e.g. "brutalist, technical, warm")
2. Pick 1 display font + 1 body font pairing
3. Choose 1 accent color + neutral palette (3-5 shades)
4. Layout: asymmetric, generous whitespace, break centered-card pattern
5. Build fully functional component (not just visual)
6. Verify dark mode compatibility

## Anti-Patterns
- Never: Inter, Roboto, Arial as display fonts
- Never: purple gradients on white backgrounds
- Never: centered cards with subtle shadows
- Never: lorem ipsum in final output
- Never: skip hover/focus/active states on interactive elements

## Typography Pairings
- DM Serif Display + Source Sans 3
- Space Grotesk + IBM Plex Sans
- Fraunces + Inter (only if Inter as body)
- Newsreader + Geist

## Color Rules
- Max 3 colors in palette (1 accent + 2 neutrals)
- Accent must pass WCAG AA on white background
- Dark mode: swap neutrals, keep accent
