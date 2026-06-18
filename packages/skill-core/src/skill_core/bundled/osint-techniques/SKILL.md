---
name: osint-techniques
description: Passive OSINT toolkit — phone/email/username tracing, holehe integration, Cloudflare bypass, .git enumeration.
version: 1.0.0
author: JalaAgent (ported from Hermes)
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 🔍
    provenance:
      source: hermes-agent
      original: osint-techniques
      category: osint
      ported: 2026-06-18
---

# OSINT Techniques

## Overview
Passive open-source intelligence gathering. Trace phone numbers, emails, usernames across 121 platforms. Legal, non-invasive methods only.

## Tool Chain
1. **PhoneInfoGA** — Phone carrier/location lookup
2. **holehe** — Check email registration on 121 platforms
3. **GitHub API** — Deep profile analysis (repos, orgs, activity)
4. **Jina AI Reader** — Bypass Cloudflare for web page extraction
5. **.git enumeration** — Find exposed .git directories
6. **Sherlock** — Username search across social media

## Legal Boundaries
- ONLY use on your own data or with explicit permission
- DO NOT use for stalking, harassment, or unauthorized access
- DO NOT attempt to bypass rate limits or authentication
- Some techniques are illegal in certain jurisdictions

## Process
1. Define target (what are you looking for?)
2. Start with passive sources (no interaction with target)
3. Cross-reference findings across 3+ sources
4. Document everything with timestamps and source URLs
5. Never store sensitive personal data in agent memory

## Anti-Patterns
- Don't use active scanning without permission (port scanning, brute force)
- Don't store found credentials in plain text
- Don't assume all findings are accurate (always verify)
