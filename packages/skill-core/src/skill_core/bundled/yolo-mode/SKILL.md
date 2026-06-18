---
name: yolo-mode
description: Full autonomy patterns — when YOLO is safe, when it's dangerous, checklist before enabling, auto-disable triggers.
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: ⚡
    provenance:
      source: jalaagent-exclusive
---

# YOLO Mode

## Overview
JalaAgent's YOLO mode bypasses all approval checks. This skill defines when it's safe, when it's dangerous, and how to use it responsibly.

## Safety Checklist (Before Enabling)
1. [ ] Running in isolated worktree (not main branch)
2. [ ] No production credentials in environment
3. [ ] No destructive operations pending
4. [ ] User explicitly typed `/mode yolo`
5. [ ] User acknowledged the YOLO warning
6. [ ] Logging is enabled (`~/.jalaagent/logs/yolo.log`)

## Safe Use Cases
- Bulk file operations in an isolated worktree
- Running test suites (read-only)
- Code generation with review step after
- Research tasks (web fetch, data analysis)

## Dangerous Use Cases (Never YOLO)
- Production deployments
- Database migrations
- Credential rotation
- `rm -rf` or equivalent
- Force push to shared branches

## Auto-Disable Triggers
The following should auto-disable YOLO:
1. Shell command matches dangerous pattern (rm -rf, chmod 777)
2. Write to file outside worktree root
3. Network request to unknown domain
4. 50+ consecutive tool calls without user interaction
5. Session duration exceeds 30 minutes

## Integration
- Policy pipeline: `PolicyPipeline(mode=ApprovalMode.YOLO)`
- Credential pool: YOLO bypasses approval but NOT credential rotation
- Worktree: YOLO session should always run in isolated worktree
