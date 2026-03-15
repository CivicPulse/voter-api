---
description: Normalize election or candidate markdown files (enforce formatting, generate UUIDs)
---

Read and execute the normalize skill at `.claude/skills/normalize/SKILL.md`
with the arguments from `$ARGUMENTS`.

Pass `$ARGUMENTS` directly to the skill as-is. The skill expects:
- First argument: subcommand — `elections` or `candidates`
- Second argument: directory path to normalize
- Optional flag: `--dry-run` to preview changes without writing files
