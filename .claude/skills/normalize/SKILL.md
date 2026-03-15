---
name: normalize
description: Normalize AI-generated election and candidate markdown files to enforce formatting consistency and generate UUIDs
argument-hint: <elections|candidates> <directory> [--dry-run]
disable-model-invocation: true
---

# Normalize Skill

Runs the deterministic markdown normalizer CLI on a directory of election or candidate files.
This skill wraps the `voter-api normalize` CLI commands for explicit invocation.

## Usage

```
/election:normalize elections <directory> [--dry-run]
/election:normalize candidates <directory> [--dry-run]
```

## Steps

**Step 1: Parse arguments**

From `$ARGUMENTS`, extract:
- Subcommand: `elections` or `candidates` (required, first argument)
- Directory path: path to the directory to normalize (required, second argument)
- `--dry-run` flag: if present, report what would change without writing any files

If subcommand is missing or unrecognized: print usage and stop.

**Step 2: Run the normalizer CLI**

For `elections` subcommand:
```bash
uv run voter-api normalize elections <directory> [--dry-run]
```

For `candidates` subcommand:
```bash
uv run voter-api normalize candidates <directory> [--dry-run]
```

Add `--dry-run` to the command if the flag was requested.

**Step 3: Show output**

Display the full normalizer output (terminal table report and any warnings).

**Step 4: Summarize warnings**

If the normalizer reports any warnings:
- List each warning with its file path and description
- Group by warning type (e.g., ALL CAPS remnants, missing UUIDs, duplicate candidates)
- Suggest remediation steps for common issues

**Step 5: Report completion**

Print a brief summary:
```
Normalization complete.
  Files processed: {N}
  Files modified: {N}
  Warnings: {N}
  UUIDs generated: {N}
```

For `candidates` subcommand, also note:
```
  Files renamed (00000000 → UUID hash): {N}
```

If `--dry-run` was used: remind the operator to re-run without `--dry-run` to apply changes.
