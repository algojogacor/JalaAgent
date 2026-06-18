---
name: self-diagnosis
description: Agent introspection — check logs, verify config, test connections, troubleshoot issues. The agent fixing itself.
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 🔧
---

# Self-Diagnosis

## Overview
Diagnose and fix JalaAgent issues. Check logs, verify configuration, test provider connections.

## Diagnostic Checklist
1. **Config**: `~/.jalaagent/config.yaml` exists and is valid YAML
2. **Dirs**: `~/.jalaagent/memories/`, `~/.jalaagent/db/`, `~/.jalaagent/skills/`
3. **Provider**: `ANTHROPIC_API_KEY` or other provider key is set
4. **Database**: `~/.jalaagent/db/memory.db` is accessible
5. **Skills**: bundled skills directory exists and loads without errors
6. **Memory**: MEMORY.md is readable, not corrupted
7. **Logs**: Check `~/.jalaagent/logs/` for recent errors

## Common Issues
- "No provider available" → check env vars, try different provider
- "Database locked" → another process has memory.db open
- "Skill parse error" → YAML frontmatter syntax error in SKILL.md
- "Memory drift detected" → MEMORY.md modified externally during session

## Fix Actions
- Corrupted config → run `jala setup` to regenerate
- Locked database → kill stale process, or delete WAL files
- Provider error → rotate credentials, try fallback provider
