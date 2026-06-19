# Authoring Skills

> Create your own skills for JalaAgent using the standard SKILL.md format.

## Quick Start

```bash
# Create a skill directory
mkdir my-skill

# Create SKILL.md
cat > my-skill/SKILL.md << 'EOF'
---
name: my-skill
description: What this skill does — be specific about triggers and outcome
version: 1.0.0
author: your-name
license: MIT
platforms: [windows, linux, macos]
metadata:
  jalaagent:
    always: false
    emoji: 🔧
    requires:
      bins: []
      env: []
---

# My Skill

Instructions for the agent go here. Be specific and concrete.
EOF

# Validate
jala skills validate my-skill/SKILL.md
```

## SKILL.md Format

Every skill is a directory containing a `SKILL.md` file with **YAML frontmatter** followed by a **markdown body**.

### Frontmatter Fields

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `name` | **Yes** | string | Slug — lowercase, hyphenated, unique |
| `description` | **Yes** | string | What the skill does + when it triggers |
| `version` | No | string | Semver (e.g. `1.0.0`) |
| `author` | No | string | Your GitHub handle or name |
| `license` | No | string | SPDX identifier (MIT, Apache-2.0, etc.) |
| `platforms` | No | string[] | `windows`, `linux`, `macos`, `termux` |
| `metadata.jalaagent.always` | No | bool | Load skill into every session (default: false) |
| `metadata.jalaagent.emoji` | No | string | Emoji shown in skill listing |
| `metadata.jalaagent.requires.bins` | No | string[] | CLI tools this skill needs |
| `metadata.jalaagent.requires.env` | No | string[] | Environment variables this skill needs |

### Body (Markdown)

The markdown body is the agent's instruction. It should be:
- **Specific** — name exact tools, flags, patterns
- **Concrete** — provide examples, not abstractions
- **Self-contained** — don't assume other skills are loaded

### Optional Files

| File | Purpose |
|------|---------|
| `references/` | Reference docs the agent can read |
| `templates/` | Output templates for code/docs |
| `scripts/` | Helper scripts the skill invokes |
| `SKILL.md` | Main skill definition (required) |

## Security Scanning

JalaAgent automatically scans skills for dangerous patterns during validation
and installation:

| Severity | Examples |
|----------|----------|
| **CRITICAL** → BLOCKED | `eval()`, `exec()`, shell injection, crypto mining |
| **HIGH** → WARN | Prompt injection patterns, env exfiltration, piped shell commands |
| **MEDIUM** → ALLOW | Obfuscation, suspicious but not clearly malicious |

Skills with CRITICAL findings are **blocked**. HIGH findings produce a warning
but don't prevent installation.

## Testing Your Skill

```bash
# Validate format + security scan
jala skills validate my-skill/SKILL.md

# List all loaded skills (yours should appear)
jala skills list

# Test in a session (invoke by name)
jala --prompt "/my-skill help me with X"
```

## Publishing

### As a bundled skill (contributing to JalaAgent)

1. Fork the repo
2. Add your skill to `packages/skill-core/src/skill_core/bundled/<skill-name>/`
3. Run `jala skills validate` on it
4. Open a PR using the skill PR template

### As a user-installed skill

Place your skill in `~/.jalaagent/skills/<skill-name>/`. User skills
take priority over bundled skills of the same name.

### On the Skill Hub (coming soon)

The JalaAgent Skill Hub will allow installing skills with:
```bash
jala skills install <skill-slug>
```

## Reference

See existing bundled skills in `packages/skill-core/src/skill_core/bundled/`
for examples. The `brainstorming` and `systematic-debugging` skills are good
starting points.
