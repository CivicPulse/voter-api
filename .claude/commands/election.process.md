---
description: Process a GA SOS qualified candidates CSV into structured election markdown files
---

Read and execute the qualified-candidates skill at `.claude/skills/qualified-candidates/SKILL.md`
with the arguments from `$ARGUMENTS`.

Pass `$ARGUMENTS` directly to the skill as-is. The skill expects:
- First argument: path to the SOS qualified candidates CSV file
- Optional flag: `--direct` to skip interactive confirmation and write files immediately
