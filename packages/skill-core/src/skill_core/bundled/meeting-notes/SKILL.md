---
name: meeting-notes
description: Meeting transcription summaries, action items extraction, decision logs. Structured output from unstructured conversation.
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 📋
---

# Meeting Notes

## Overview
Extract structured summaries from meeting transcripts. Focus on decisions, action items, and follow-ups.

## Output Format
```markdown
# Meeting: [Topic]
**Date**: YYYY-MM-DD
**Attendees**: [Names]

## Decisions Made
1. [Decision] — [Rationale, one sentence]

## Action Items
- [ ] [Owner]: [Task] — Due [Date]
- [ ] [Owner]: [Task] — Due [Date]

## Key Discussion Points
- [Topic]: [One-paragraph summary]

## Follow-up
- Next meeting: [Date/Time]
- Open questions: [List]
```

## Process
1. Read full transcript before writing anything
2. Extract all explicit decisions first
3. Extract all "I will" / "we need to" statements as action items
4. Group discussion by topic, not chronology
5. Verify each action has an owner and deadline

## Anti-Patterns
- Don't transcribe verbatim (summarize)
- Don't assign actions without asking who owns them
- Don't bury decisions in prose (pull them out explicitly)
