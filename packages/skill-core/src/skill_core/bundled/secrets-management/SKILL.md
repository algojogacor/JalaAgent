---
name: secrets-management
description: Credential rotation, vault patterns, .env security, secret scanning in commits. Never commit a secret.
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 🔐
---

# Secrets Management

## Iron Law
```
NEVER COMMIT A SECRET. IF YOU COMMIT ONE, ROTATE IT IMMEDIATELY.
```

## Storage Patterns
- Dev: `.env` file (gitignored, never committed)
- CI/CD: platform secrets (GitHub Secrets, Vercel Env Vars)
- Production: vault (HashiCorp Vault, AWS Secrets Manager, Doppler)
- Runtime: env vars injected by orchestration, not in code

## Detection
```bash
git diff --staged | grep -E '(API.?KEY|SECRET|TOKEN|PASSWORD)\s*=\s*["'"'"'][^"'"'" ]{8,}'
```

## Rotation Process
1. Generate new credential
2. Deploy new credential alongside old (dual-auth window)
3. Verify new credential works
4. Revoke old credential
5. Update all references

## Anti-Patterns
- Never hardcode secrets in source
- Never share .env files via chat/email
- Never use the same secret across environments
