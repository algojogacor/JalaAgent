---
name: test-driven-development
description: Red-Green-Refactor cycle. NO production code without a failing test first. Watch tests fail, then watch them pass. Regression tests before bug fixes.
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 🧪
---

# Test-Driven Development

## Iron Law
```
NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST.
YOU MUST WATCH THE TEST FAIL. IF YOU DIDN'T SEE IT FAIL, YOU DON'T KNOW WHAT IT TESTS.
```

## Red-Green-Refactor Cycle

```
RED   → Write a minimal failing test. Watch it fail.         (30s)
GREEN → Write the simplest code to make it pass. Watch it.   (30s)
REFACTOR → Clean up while tests stay green.                  (60s)
```

## Rules

1. **Never write production code before its test exists and fails.**
2. **Watch every test fail before making it pass.** Skip this and you don't know if the test actually tests anything.
3. **One behavior per test.** One assertion per test where practical.
4. **Cheating is OK in GREEN.** Hardcode return values, copy-paste — refactor later in REFACTOR phase.
5. **If a test is hard to write, the API is wrong.** Fix the API, not the test.

## Good vs Bad

`<Bad>` Tests implementation details (mock verify, internal state) — brittle.
`<Good>` Tests observable behavior (input → output, side effects) — robust.

`<Bad>` Long test with setup, act, assert, assert, assert — unclear what broke.
`<Good>` Short test: arrange, act, assert (one assertion) — exact failure point.

## Debugging Integration

Before fixing a bug:
1. Write a regression test that reproduces it
2. Watch it fail (confirming the bug)
3. Apply the fix
4. Watch it pass (confirming the fix works)
5. Run the full suite

## Verification Checklist
- [ ] Did I write the test first?
- [ ] Did I watch it fail?
- [ ] Did I watch it pass?
- [ ] Does the full suite still pass?
- [ ] Is the test testing behavior, not implementation?
