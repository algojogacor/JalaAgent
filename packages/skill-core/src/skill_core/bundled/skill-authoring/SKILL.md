---
name: skill-authoring
description: How to write effective SKILL.md files. Structure, patterns, triggers, testing. Create skills that actually work.
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 🛠️
---

# Skill Authoring

## Overview
Write effective SKILL.md files for JalaAgent. A good skill is concrete, testable, and triggers at the right time.

## Anatomy
```yaml
---
name: skill-slug           # lowercase, hyphens, unique
description: One line      # Used for trigger matching — be specific
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false          # True = load into every prompt
    emoji: 🔧
    requires:
      bins: []             # Executables needed
      env: []              # Env vars needed
---
# Title
## Overview (1-2 sentences)
## Process (numbered steps, 3-7)
## Anti-Patterns (3-5 things NOT to do)
```

## Writing Rules
- Description is the trigger — make it match what the user would say
- Steps must be actionable, not philosophical
- Anti-patterns pre-empt the most common failure modes
- Every skill must be testable (can you verify it changed behavior?)

## Testing
1. Write 3 prompts that SHOULD trigger the skill
2. Write 2 prompts that should NOT trigger it
3. Verify the skill changes behavior on the should-trigger prompts
4. Verify it does NOT activate on should-not-trigger prompts
