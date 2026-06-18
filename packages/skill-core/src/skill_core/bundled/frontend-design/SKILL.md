---
name: frontend-design
description: Create distinctive, production-grade frontend interfaces. Bold aesthetic choices, no AI-slop defaults. Intentionality over intensity.
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata: jalaagent: always: false; emoji: 🎨
---

# Frontend Design

## Philosophy

**Intentionality, not intensity.** Every design choice should be deliberate. Pick an extreme direction, not a safe middle ground. Claude is capable of extraordinary creative work — don't hold back.

## What to NEVER Use

- **Fonts:** Inter, Roboto, Arial, system-ui (overused, zero personality)
- **Colors:** Purple gradients on white backgrounds (the universal AI aesthetic)
- **Layouts:** Centered card with subtle shadow (every AI-generated landing page)
- **Icons:** Generic emoji as primary visual elements

## What to Use Instead

- **Typography:** Pick a distinctive pairing. Display font for headings, readable font for body. Try: DM Serif Display + Source Sans, or Space Grotesk + Inter (if Inter is the only good option)
- **Color:** Pick ONE bold color as your accent. Everything else is neutral. Never more than 3 colors in a palette.
- **Spatial:** Generous whitespace. Asymmetric layouts. Break the centered-card pattern.
- **Motion:** One meaningful animation per page. Page load transitions. Hover states. No bouncing logos.

## Design Process

1. **State the vibe**: 3 adjectives. Example: "Brutalist, technical, warm"
2. **Pick typography**: 1 display font + 1 body font
3. **Pick palette**: 1 accent color + neutral scale (3-5 shades)
4. **Sketch layout**: Asymmetric, generous whitespace
5. **Build component**: Fully functional, not just visual
6. **Test dark mode**: Every design must work in dark mode

## Anti-Patterns (AI Slop)

- Cards with `border-radius: 12px` and `box-shadow: 0 4px 6px`
- Hero section with centered text + gradient background
- Every section having the same padding
- No hover/focus/active states on interactive elements
- Lorem ipsum in production designs
