---
name: self-upgrade
description: JalaAgent upgrading its own skills via workshop pipeline. Self-improvement loop using skill-core APIs.
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 🔄
    provenance:
      source: jalaagent-exclusive
---

# Self-Upgrade

## Overview
JalaAgent can improve its own skills using the workshop pipeline. After completing complex tasks, the agent evaluates whether a new skill should be created or an existing one updated.

## Process
1. After session: background task evaluates completed work
2. If a workflow pattern was successful → propose new skill
3. Security scanner runs on proposal
4. User reviews (unless YOLO mode)
5. Skill written to `~/.jalaagent/skills/` atomically with rollback

## Workshop API
```python
from skill_core.workshop import SkillWorkshop
from skill_core.scanner import SkillScanner

workshop = SkillWorkshop(scanner=SkillScanner())
proposal = await workshop.propose(skill_content, source_session_id)
if proposal.scan_result.verdict == "allow":
    skill_path = await workshop.apply(proposal.id)
```

## Upgrade Heuristics
Create/update a skill when:
- Same workflow executed 3+ times successfully
- Task took >10 tool calls (complex enough to capture)
- Workaround was needed (skill would prevent it)
- User explicitly asked how to do something

## Anti-Patterns
- Don't create skills for one-off tasks
- Don't propose without running security scanner
- Don't auto-apply without user review (unless YOLO)
