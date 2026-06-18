---
name: mcp-management
description: Configure and manage MCP servers — stdio and HTTP transports, tool naming, security filtering, auto-reconnection, WSL bridging. Extend agent capabilities through tools.
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata: jalaagent: always: false; emoji: 🔌
---

# MCP Management

## Iron Law
```
MCP SERVERS RUN AS SUBPROCESSES. THEY HAVE ACCESS TO THE HOST.
FILTER ENVIRONMENT VARIABLES. STRIP CREDENTIALS BEFORE SENDING.
NEVER EXPOSE SENSITIVE ENV VARS TO MCP SERVERS.
```

## Configuration

### Transport: stdio
```yaml
mcp:
  servers:
    - name: filesystem
      command: npx
      args: ["-y", "@modelcontextprotocol/server-filesystem", "/allowed/path"]
      env:
        NODE_ENV: production
```

### Transport: HTTP
```yaml
mcp:
  servers:
    - name: custom-api
      url: http://localhost:8080/mcp
      headers:
        Authorization: "Bearer ${MCP_TOKEN}"
```

## Tool Naming Convention

MCP tools are namespaced: `mcp_{server_name}_{tool_name}`

Example:
- `mcp_filesystem_read_file`
- `mcp_filesystem_write_file`
- `mcp_fetch_get`

## Security Rules

1. **Filter environment variables**: only pass explicitly listed env vars
2. **Strip credentials**: remove `API_KEY`, `SECRET`, `TOKEN` from transmitted env
3. **Path scoping**: filesystem servers get `--allowed-paths` not root access
4. **Timeout**: every MCP call has a 30s timeout

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Server won't start | Check command is in PATH, npx is installed |
| Tools not appearing | Server started but didn't announce tools — check logs |
| WSL → Windows bridging | `ip route show default`, use that IP for HTTP MCP servers |
| Connection drops | Auto-reconnect with exponential backoff (1s, 2s, 4s, max 30s) |

## Commands
```bash
jala mcp add <name> <command> [args...]  # Add a server
jala mcp list                            # List configured servers
jala mcp status                          # Show running/idle status
jala mcp remove <name>                   # Remove a server
```
