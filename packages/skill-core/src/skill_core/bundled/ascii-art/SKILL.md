---
name: ascii-art
description: Terminal art via pyfiglet, cowsay, lolcat, image-to-ascii. ANSI color, boxes, banners.
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 🎭
    requires:
      bins: [python]
      env: []
---

# ASCII Art

## Overview
Create terminal-based art using Python libraries. Banners, boxes, ANSI-colored output, image-to-ASCII conversion.

## Tools
- `pyfiglet` — text banners, 200+ fonts
- `cowsay`/`cowthink` — character speech bubbles
- `rich` — colored panels, tables, syntax highlighting
- `PIL`/`pillow` — image to ASCII conversion
- `colorama`/`termcolor` — ANSI color codes

## Process
1. Choose format: banner, box, character, or image conversion
2. Select font/style appropriate to content
3. Apply color meaningfully (not random)
4. Verify output fits terminal width (default 80 cols)
5. Test on both light and dark backgrounds

## Anti-Patterns
- Don't use figlet for body text (only titles)
- Don't use more than 3 colors in one output
- Don't assume terminal supports 256 colors (ANSI 16 is safe)
