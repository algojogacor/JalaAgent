---
name: docker-management
description: Dockerfile authoring, docker-compose, multi-stage builds, layer caching, container optimization.
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 🐳
    requires: {bins: [docker], env: []}
---

# Docker Management

## Overview
Build efficient, secure Docker images. Optimize for build speed, image size, and runtime security.

## Dockerfile Rules
1. Start from specific version tags, never `:latest`
2. Multi-stage builds: separate build deps from runtime
3. Layer order: least-changing first (deps before code)
4. `.dockerignore` must exclude `.git`, `node_modules`, `__pycache__`
5. Use non-root USER in final stage

## docker-compose Patterns
- Service naming: descriptive, not generic
- Health checks on every service
- Volume mounting for dev, COPY for prod
- Network isolation between service groups

## Anti-Patterns
- Never `COPY . .` without `.dockerignore`
- Never run as root in production
- Never store secrets in image layers
- Never use `latest` tag in production
