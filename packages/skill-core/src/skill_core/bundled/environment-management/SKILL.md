---
name: environment-management
description: Reproducible dev environments — venv, conda, nix, dev containers, Docker-based dev. Lockfiles and pinning.
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 📦
---

# Environment Management

## Overview
Create and maintain reproducible development environments. "Works on my machine" is a solved problem.

## Tools
- **uv** (Python) — Fast resolver, lockfile, pip-compatible
- **conda/mamba** — Cross-language environment management
- **dev containers** — Docker-based, IDE-integrated
- **nix** — Declarative, fully reproducible

## Process
1. Pin all dependencies with exact versions
2. Lockfile must be committed (uv.lock, environment.yml)
3. Document setup in README: one command to full dev environment
4. CI uses same lockfile as development
5. Separate dev deps from production deps

## Anti-Patterns
- Never: `pip install` without version pinning
- Never: system-wide installations for project deps
- Never: undocumented setup steps
