---
name: pixel-art
description: Convert images to retro pixel art with 14 hardware palettes. Floyd-Steinberg dithering, procedural animation overlay.
version: 1.0.0
author: JalaAgent (adapted from Hermes pixel-art)
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 👾
    provenance:
      source: hermes-agent
      original: pixel-art
      category: creative
      ported: 2026-06-18
      adaptations: [replaced pygame/pyboy deps with Pillow-only pipeline, added GIF export]
---

# Pixel Art

## Overview
Convert any image to retro pixel art with hardware-accurate color palettes. 14 era-specific palettes, Floyd-Steinberg dithering, optional animation.

## 14 Hardware Palettes
- NES (54 colors), Game Boy (4 shades), Game Boy Color (32 colors)
- PICO-8 (16 colors), C64 (16 colors), ZX Spectrum (15 colors)
- SNES (256 colors), Sega Genesis (512 colors), Atari 2600 (128 colors)
- MSX (16 colors), Amiga (4096 colors), Apple II (16 colors)
- VGA (256 colors), EGA (64 colors)

## Process
```python
from PIL import Image
# 1. Load image
img = Image.open("input.png")
# 2. Downscale to target resolution (e.g., 64x64)
img = img.resize((64, 64), Image.LANCZOS)
# 3. Quantize to palette
img = img.quantize(colors=16, palette=Image.Palette.ADAPTIVE)
# 4. Apply Floyd-Steinberg dithering
# 5. Upscale with nearest-neighbor (crisp pixels)
img = img.resize((512, 512), Image.NEAREST)
```

## Animation Overlay (12 scene types)
Rain, fireflies, snow, embers, starfield, lightning, waves, bubbles, leaves, smoke particles, aurora, confetti

## Anti-Patterns
- Don't upscale before dithering (pixels get blurry)
- Don't use more colors than the target palette supports
- Don't apply animation overlay to images that shouldn't animate
