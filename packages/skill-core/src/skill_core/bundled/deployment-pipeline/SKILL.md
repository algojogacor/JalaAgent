---
name: deployment-pipeline
description: CI/CD design with GitHub Actions, deployment strategies (blue-green, canary, rolling), environment promotion.
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 🚀
---

# Deployment Pipeline

## Overview
Design CI/CD pipelines. From push to production with gates, checks, and rollback capability.

## GitHub Actions Structure
```yaml
test → build → security-scan → staging-deploy → smoke-test → prod-deploy
```

## Deployment Strategies
- **Blue-green**: Two identical environments, swap traffic. Instant rollback.
- **Canary**: Gradually shift % of traffic to new version.
- **Rolling**: Replace instances one at a time.

## Pipeline Gates
- Tests must pass (unit + integration)
- Type check must pass
- Lint must pass
- Security scan must pass
- Manual approval for production

## Anti-Patterns
- Never deploy on Friday
- Never skip staging environment
- Never deploy without a tested rollback plan
