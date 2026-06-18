---
name: skill-creator
description: Create, test, evaluate, and iteratively improve skills. A/B test with-skill vs baseline. Quantitative benchmarking. Progressive disclosure loading.
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata: jalaagent: always: false; emoji: 🛠️
---

# Skill Creator (Meta-Skill)

The skill for building skills. Full lifecycle: capture intent → write → test → evaluate → iterate → optimize.

## Skill Anatomy

```markdown
---
name: skill-name          # Unique slug, lowercase, hyphens
description: One-line     # Used for SKILL.md triggering
version: 1.0.0
author: username
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false         # Auto-load into every prompt?
    emoji: 🔧
    requires:
      bins: []            # Required executables
      env: []             # Required env vars
---

# Title

## Iron Law (optional)
`ALL CAPS CRITICAL RULE IN CODE BLOCK`

## When To Use / When NOT To Use
## Process (numbered steps)
## Red Flags / Common Mistakes
## Integration (links to other skills)
```

## Evaluation Pipeline

### Step 1: Create Test Cases
Write 3-5 evaluation prompts. Each should have a measurable expected outcome.

### Step 2: Baseline Run
Spawn a subagent WITHOUT the skill. Record results.

### Step 3: Skill Run
Spawn a subagent WITH the skill loaded. Same prompts. Record results.

### Step 4: Compare
| Metric | Baseline | With Skill |
|--------|----------|------------|
| Task completion | X% | Y% |
| Errors | N | M |
| Time | Xs | Ys |

### Step 5: Iterate
Organize iterations as `iteration-1/`, `iteration-2/`, etc. Snapshot the skill before each edit for fair comparison.

### Step 6: Optimize Description
Test trigger accuracy: run queries that SHOULD trigger the skill and queries that SHOULD NOT.

## Writing Patterns

- **Progressive Disclosure**: metadata → body → bundled resources
- **Explain the WHY**, not just heavy-handed MUSTs
- **Pre-empt excuses**: name the rationalizations people use to skip the process
- **Good/Bad examples**: show both correct and incorrect usage
- **Integration section**: skills don't exist in isolation — link to related skills
