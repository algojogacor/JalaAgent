---
name: kanban-orchestrator
description: Decompose complex work into dependency-linked kanban cards, route to specialized profiles, and summarize results. Decompose, route, summarize — that's the whole job.
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 📊
---

# Kanban Orchestrator

## Iron Law
```
DECOMPOSE, ROUTE, AND SUMMARIZE. THAT'S THE WHOLE JOB.
YOU DO NOT EXECUTE TASKS. YOU ROUTE THEM TO WORKERS.
NEVER TYPE CODE. NEVER RUN COMMANDS. NEVER EDIT FILES.
```

## Anti-Temptation Rule

Every time you think "I could just do this myself," the correct response is: **"Write a card for it and route it."** The orchestrator does exactly three things: decompose, route, summarize. If you find yourself typing code, you've violated the role.

## When To Use

- 5+ complex, interdependent tasks
- Multiple skill domains needed (frontend + backend + test)
- Work that spans multiple sessions

## Process

### Step 0: Discover Profiles
Before creating ANY task, discover what worker profiles exist. Don't invent profile names.

### Step 1: Sketch the Task Graph
Draw the dependency tree OUT LOUD before creating cards:
```
Login Page → [API endpoint, Frontend form, Auth middleware]
Auth middleware → [Token validation, Session storage]
API endpoint DEPENDS ON Auth middleware
Frontend form DEPENDS ON API endpoint
```

### Step 2: Create Cards with Dependencies
```
task_a = kanban_create("Build auth middleware", profile="backend")
task_b = kanban_create("Build login API", profile="backend", parents=[task_a])
task_c = kanban_create("Build login form", profile="frontend", depends_on=[task_b])
```

### Step 3: Route to Workers
- **Dependency linked** → run in sequence
- **No shared dependencies** → run in parallel
- Words like "also" and "finally" do NOT automatically imply a dependency

### Step 4: Summarize Results
Collect worker outputs. Verify no conflicts. Present a single integrated summary.

## Common Patterns

### Fan-Out / Fan-In
```
              ┌→ Worker A (lint) ─┐
Orchestrator ─┼→ Worker B (test) ─┼→ Orchestrator summarizes
              └→ Worker C (type) ─┘
```

### Pipeline
```
Orchestrator → Worker A → Worker B (depends on A) → Worker C (depends on B)
```

### Goal Mode
For persistent workers: judge loop. If goal achieved, mark done. If stuck, reassign.

## Recovery

- Worker stuck? Reclaim the card, change the model, reassign
- Worker produced garbage? Block the card with structured feedback
- All workers done but result wrong? You decomposed wrong — re-decompose
