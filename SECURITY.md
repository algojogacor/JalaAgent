# Security Policy

## Reporting Vulnerabilities

If you discover a security vulnerability in JalaAgent, please report it privately.

**Do NOT open a public issue.** Instead, open a private security advisory on GitHub or contact the maintainers directly.

## Supported Versions

| Version | Supported |
|---------|-----------|
| v2026.6.x | ✅ Yes |

## Security Architecture

JalaAgent has multiple security layers:

- **Policy pipeline**: 4-layer approval system (PARANOID/NORMAL/YOLO/CUSTOM)
- **Sandboxed shell**: Dangerous command detection + path scoping
- **Skill scanner**: 6-rule security scan on skill install
- **Fail-closed approval**: Auto-deny on timeout
- **Credential isolation**: auth.json with 0o600 permissions
- **No telemetry**: JalaAgent never phones home

## Known Safe Practices

- `jala serve` uses auth tokens for API access
- Config files have restrictive permissions (0o600)
- Path traversal prevented in `/personality` and `BlueprintStore`
- Exception details never leak to API clients
