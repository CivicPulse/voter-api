---
description: Enrich candidate markdown files with bios, photos, and contact info from web research
---

Read and execute the candidate-enrichment skill at `.claude/skills/candidate-enrichment/SKILL.md`
with the arguments from `$ARGUMENTS`.

Pass `$ARGUMENTS` directly to the skill as-is. The skill expects:
- First argument: path to the candidates directory (typically `data/candidates/`)
- Optional flag: `--depth full|basic|minimal` (default: full)
- Optional flag: `--direct` to write enriched files without interactive confirmation
