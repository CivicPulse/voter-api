---
description: Extract election dates and deadlines from GA SOS calendar PDFs into election overview metadata
---

Read and execute the election-calendar skill at `.claude/skills/election-calendar/SKILL.md`
with the arguments from `$ARGUMENTS`.

Pass `$ARGUMENTS` directly to the skill as-is. The skill expects:
- First argument: path to a GA SOS calendar PDF file or a directory containing PDF files
- Second argument: election date in YYYY-MM-DD format (identifies which overview file to update)
- Optional flag: `--direct` to write the updated overview file without confirmation
