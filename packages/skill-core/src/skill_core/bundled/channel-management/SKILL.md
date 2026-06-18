---
name: channel-management
description: Multi-channel routing, message formatting per platform. Adapt responses for CLI, Telegram, and future channels.
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 📡
---

# Channel Management

## Overview
Route and format agent responses for different communication channels. Each channel has different constraints.

## Channel Constraints
- **CLI**: Full markdown, code blocks, rich formatting. No length limits.
- **Telegram**: 4096 char limit per message. HTML/MarkdownV2. Inline keyboards.
- **Discord (future)**: 2000 char limit. Embeds. Slash commands.
- **Web (future)**: Full HTML/CSS/JS. Streaming. Interactive components.

## Formatting Rules
- Code blocks: always specify language for syntax highlighting
- Long responses: split at paragraph boundaries, not mid-sentence
- Links: use descriptive text, not raw URLs
- Emojis: use sparingly on CLI, freely on messaging platforms

## Routing
- Same message to multiple channels: adapt formatting, keep content
- Approval requests: CLI uses prompt, Telegram uses inline keyboards
- Streaming: CLI uses live-updating panel, Telegram edits message in place

## Anti-Patterns
- Don't send raw markdown to Telegram (convert to MarkdownV2)
- Don't truncate mid-word when splitting messages
- Don't assume all channels support the same formatting
