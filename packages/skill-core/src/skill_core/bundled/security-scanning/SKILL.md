---
name: security-scanning
description: Scan code for vulnerabilities — credential leaks, injection vectors, unsafe patterns. Pre-commit and pre-deploy gates. Integration with pre-commit-verification skill.
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 🔒
---

# Security Scanning

## Iron Law
```
NEVER COMMIT CREDENTIALS. NEVER TRUST INPUT. NEVER EXECUTE UNVALIDATED CODE.
SCAN BEFORE COMMIT. SCAN BEFORE DEPLOY. SCAN ON SUSPICION.
```

## Scan Categories

### Credential Leaks
```bash
grep -rnE '(API[_-]?KEY|SECRET|TOKEN|PASSWORD)\s*=\s*["'"'"][^"'"'" ]{8,}' .
grep -rnE '(sk-[a-zA-Z0-9]{20,})' .  # OpenAI/Anthropic keys
grep -rnE '(ghp_[a-zA-Z0-9]{36})' .   # GitHub tokens
```

### Injection Vectors
```bash
grep -rnE '(subprocess.*shell\s*=\s*True|os\.system\()' .
grep -rnE 'f["'"'"].*\{.*\}.*sql' .  # f-string SQL queries
grep -rnE '(eval\(|exec\(|__import__\()' .
```

### Unsafe Patterns
```bash
grep -rnE 'pickle\.loads?' .  # Deserialization
grep -rnE '(http://|ftp://)' . --include="*.py"  # Plain HTTP
grep -rnE 'TODO.*(hack|fixme|remove|temp)' .  # Suspicious comments
```

### Dependency Vulnerabilities
```bash
uv run pip-audit  # Python dependency scan
npm audit  # Node.js dependency scan
```

## Severity Classification

| Finding | Severity | Action |
|---------|----------|--------|
| Hardcoded credential | CRITICAL | Block commit |
| `shell=True` with user input | CRITICAL | Block commit |
| `eval`/`exec` with dynamic input | CRITICAL | Block commit |
| SQL string formatting | HIGH | Warn, require fix |
| `pickle.loads` | HIGH | Warn, require fix |
| Plain HTTP for sensitive data | MEDIUM | Note |
| Suspicious TODO comments | LOW | Note |

## Integration

- Run as **Step 2** of **pre-commit-verification** skill
- Run on every `jala skills install` via **skill-core scanner**
- Run in CI on every PR
