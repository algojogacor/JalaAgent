## Skill Name
<!-- Brief description of what the skill does -->

## Trigger Conditions
<!-- When should JalaAgent load this skill? What user requests trigger it? -->

## Checklist
- [ ] SKILL.md follows the required frontmatter format
- [ ] `name` and `description` fields are present and clear
- [ ] `jala skills validate <path>` passes (no CRITICAL/HIGH findings)
- [ ] Skill has been tested locally: `jala skills list` shows it
- [ ] Skill works in a real session: `jala --prompt "/<skill-name> help"`
- [ ] Platform compatibility is specified (check `platforms` field)
- [ ] No hardcoded credentials, API keys, or tokens
- [ ] No `eval()`, `exec()`, or shell injection patterns
- [ ] Skill body is specific and concrete — no vague instructions

## Security Scan Results
<!-- Paste the output of `jala skills validate <path>` -->

## Category
- [ ] Software Development
- [ ] DevOps
- [ ] Data & Research
- [ ] Creative
- [ ] Communication
- [ ] JalaAgent Exclusive
- [ ] Other

## Related Issues/PRs
<!-- Link to related issues or discussions -->
