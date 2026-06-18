---
name: browseros
description: Control BrowserOS agentic browser — navigate, click, extract data, fill forms, manage sessions with persistent login state
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos]
metadata:
  jalaagent:
    always: false
    emoji: 🌐
    requires:
      bins: []
      env: []
---

# BrowserOS

## Overview
BrowserOS is an agentic browser with 53+ browser automation tools and persistent session state. Unlike Playwright (which starts fresh every session), BrowserOS keeps you logged into Gmail, GitHub, Twitter, and any site across sessions. It runs as a separate process and connects to JalaAgent via MCP.

## Why BrowserOS > Playwright
- **Persistent sessions**: login once, stay logged in across sessions
- **53+ tools**: navigate, click, type, extract, screenshot, scroll, fill forms, manage cookies, download files, intercept network, emulate devices
- **No setup per session**: browser state survives restarts
- **Runs separately**: no dependency conflicts, no Chromium download
- **MCP-native**: connects via `http://localhost:9876`, auto-discovered by JalaAgent

## Setup
1. Download from https://github.com/browseros-ai/BrowserOS
2. Install and run `browseros-cli init`
3. Add to JalaAgent: `jala mcp add browseros` or run `jala setup`

## Connect
```
/browser connect    # Check for BrowserOS MCP, connect if configured
/browser status     # Show active browser backend
/browser disconnect # Disconnect browser session
```

## Common Use Cases
- **Web scraping with auth**: scrape dashboards that require login (Stripe, AWS, analytics)
- **Form filling**: automate repetitive form submissions with saved profiles
- **Monitoring**: check dashboards periodically, screenshot on changes
- **Research**: browse with persistent login, extract structured data across sessions
- **Testing**: verify web apps with real browser state

## License
BrowserOS is AGPL-3.0 licensed and runs as a separate process from JalaAgent (Apache-2.0). No license conflict — they communicate via MCP over HTTP.
