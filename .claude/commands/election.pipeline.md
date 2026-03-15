---
description: Run the full election data pipeline - SOS CSV to normalized, enriched markdown
---

Read and execute the process-election skill at `.claude/skills/process-election/SKILL.md`
with the arguments from `$ARGUMENTS`.

Pass `$ARGUMENTS` directly to the skill as-is. The skill expects:
- First argument: path to the SOS qualified candidates CSV file
- Optional flag: `--direct` to skip interactive confirmation at each pipeline step
- Optional flag: `--skip-enrich` to skip the candidate enrichment step (useful for large elections or when enrichment is deferred)
