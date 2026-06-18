---
name: p5js
description: Creative coding with p5.js — generative art, interactive sketches, visual experiments
version: 1.0.0
author: JalaAgent (ported from Hermes)
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 🎮
    provenance:
      source: hermes-agent
      original: p5js
---

# P5.js — Creative Coding

Generate interactive art and visual experiments using p5.js.

## Quick Start
```html
<script src="https://cdnjs.cloudflare.com/ajax/libs/p5.js/1.9.0/p5.min.js"></script>
<script>
function setup() { createCanvas(400, 400); }
function draw() {
  background(220);
  ellipse(mouseX, mouseY, 50, 50);
}
</script>
```

## Generative Patterns
- **Perlin noise**: `noise(x * 0.01, y * 0.01)` for organic textures
- **Recursion**: fractal trees, Sierpinski triangles
- **Particle systems**: emitters, gravity, trails
- **Flow fields**: vector fields guiding particle motion

## Rules
- Canvas size max 800x800 (performance)
- Always include `setup()` and `draw()`
- Use `frameRate(30)` for smooth animation
- Export as single HTML file (self-contained)
