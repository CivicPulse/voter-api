# Phase 3: Claude Code Skills - Research

**Researched:** 2026-03-15
**Domain:** Claude Code Skills/Commands, Python text normalization, CSV data processing, PDF extraction
**Confidence:** HIGH

## Summary

Phase 3 builds two categories of artifacts: (1) Claude Code skill files that instruct Claude how to process GA SOS election data, and (2) a deterministic Python normalizer library (`lib/normalizer/`) that post-processes AI-generated markdown. The skills are prompt-engineering artifacts (markdown files with YAML frontmatter), while the normalizer is a standard Python library with CLI integration following the project's established library-first architecture.

The key technical insight is that Claude Code skills are **not code** -- they are SKILL.md files with structured instructions. The `.claude/skills/` directory is the modern format, replacing `.claude/commands/`. Skills support YAML frontmatter for invocation control, `$ARGUMENTS` substitution for parameterization, `!` backtick syntax for dynamic context injection, supporting files in the skill directory, and `context: fork` for subagent execution. The normalizer, by contrast, is a pure Python library that must be deterministic, idempotent, and independently testable.

The SOS CSV data presents significant AI parsing challenges: contest names are wildly inconsistent (ALL CAPS, mixed case, varying delimiter styles, missing spaces, different abbreviation patterns). This is the core value proposition for AI skills -- pattern matching that would require an enormous rule set if done deterministically. The normalizer handles everything that CAN be deterministic (title case, URL formatting, date formatting, UUID generation) while the skills handle what CANNOT be deterministic (contest name parsing, body/seat inference, candidate deduplication).

**Primary recommendation:** Build the normalizer library first (it is independently testable and provides the validation foundation), then build skills that reference format specs and includes, with the normalizer as the quality gate for skill output.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Skill Packaging & Invocation
- Both skills + commands: Skills in `.claude/skills/` for auto-triggering AND commands in `.claude/commands/` for explicit `/slash` invocation
- Namespaced commands: `/election:process`, `/election:enrich`, `/election:normalize`, `/election:calendar`, `/election:pipeline` -- following the existing hatchkit/speckit namespace pattern
- Interactive confirmation by default: Skill shows each file's content and asks for approval before writing. `--direct` flag skips confirmation and writes directly (review via git diff)
- Format specs referenced, not embedded: Skills point Claude to `docs/formats/markdown/` files at runtime -- no duplication of format rules in skill prompts
- Shared includes: Common prompt fragments in `.claude/skills/includes/` (e.g., `csv-columns.md`, `format-rules.md`) referenced via `@file` syntax. DRY -- update once, all skills stay in sync
- Normalizer is a separate explicit step: User runs normalizer independently after skill output. Not auto-invoked by skills. User can review AI output before normalization.

#### Skill Count & Boundaries
- 5 skills total (1:1 mapping to requirements + orchestrator):
  1. qualified-candidates (SKL-01) -- processes SOS CSV into election directory + candidate stubs
  2. normalize (SKL-02) -- also a CLI tool (`voter-api normalize elections <dir>` / `voter-api normalize candidates <dir>`)
  3. election-calendar (SKL-03) -- processes SOS PDFs into election metadata
  4. candidate-enrichment (SKL-04) -- adds bios, photos, contact info from web research
  5. process-election (orchestrator) -- runs full pipeline: CSV -> skill -> normalize -> review
- Candidate stub creation is part of SKL-01

#### Normalizer Design
- Location: New `lib/normalizer/` package following library-first pattern
- CLI commands: `voter-api normalize elections <dir>` and `voter-api normalize candidates <dir>`
- Enforcement scope: Text formatting, structural consistency, content validation, idempotency guarantee
- UUID generation by normalizer for records missing ID
- Smart title case: Not Python `str.title()` -- handles suffixes (III, Jr, Sr, II, IV), Scottish prefixes (Mc, Mac), compound names (De, La, Van)
- Report format: Terminal table + JSON report file

#### Candidate Enrichment
- Sources: Ballotpedia, campaign websites, official government sites, social media
- Uncertainty handling: Mark confidence inline with `(unverified)` or `(source: ballotpedia)` annotations
- URL validation: Skill validates URLs are live
- Enrichment depth: User-configurable via `--depth` flag (full/basic/minimal)
- Two-pass approach: Stub creation (SKL-01) then deep enrichment (SKL-04)

#### Agent Team Coordination
- Coordinator + batch workers: One coordinator agent assigns batches
- Partitioning by candidate count
- Concurrency: 4 parallel worker agents (default)
- Uses Claude Code's cooperative team support when enabled

#### Output & File Handling
- Full election directory per invocation
- Raw source file location: `data/import/` (flat directory, gitignored)
- Diff-aware updates when re-processing
- Regenerate vs. update: Operator chooses at execution time

#### SOS CSV Column Mapping
- 11 columns: CONTEST NAME, COUNTY, MUNICIPALITY, CANDIDATE NAME, CANDIDATE STATUS, POLITICAL PARTY, QUALIFIED DATE, INCUMBENT, OCCUPATION, EMAIL ADDRESS, WEBSITE
- AI-parsed: CONTEST NAME parsed by AI to infer Body ID, Seat ID, election type
- Column mapping documented in `.claude/skills/includes/csv-columns.md`

#### Election Calendar PDF Handling
- AI reads PDFs directly (no PDF parsing library needed)
- Both PDFs processed: Master calendar + per-election PDFs
- Fields extracted: Core dates, absentee dates, qualifying period, participating counties

#### Error Handling & Recovery
- Dual checkpointing: DB entry in `import_jobs` table + local JSONL checkpoint file
- Resume from checkpoint
- Strict CSV column validation at start

#### Testing Strategy
- AI skills tested via pipeline (downstream tools ARE the tests)
- Normalizer tested comprehensively: golden file tests, property-based tests (Hypothesis), unit tests per rule
- Synthetic CSV fixture (~20 candidates, 3-4 contests)

#### Data Processing Scope
- All three available CSVs processed: May 19 (2,346 rows), March 17 (9 rows), March 10 (38 rows)
- May 19 existing files regenerated from CSV, compared via git diff

### Claude's Discretion
- Plan count and sequencing
- Normalizer internal architecture (submodule breakdown within lib/normalizer/)
- Skill prompt engineering details and structure
- Shared include file organization and content
- Agent team implementation details
- Checkpoint file format
- Synthetic CSV fixture content and edge cases

### Deferred Ideas (OUT OF SCOPE)
- Absentee ballot data processing (A-12599.zip)
- Voter history import via skill (2026.csv)
- SOS results URL scraper
- Historical election backfill (2024-2025)
- Skill for populating county reference files
- Round-trip validation (MD -> JSONL -> DB -> export)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SKL-01 | Skill processes a GA SOS qualified candidates CSV into per-election structured markdown files following the enhanced format spec | Skills architecture, CSV column mapping, contest name parsing patterns, format spec references, shared includes design |
| SKL-02 | Deterministic Python normalizer post-processes AI-generated markdown to enforce title case, URL normalization, occupation formatting, and field consistency | Normalizer library architecture, smart title case algorithm, idempotency patterns, report generation, CLI integration patterns |
| SKL-03 | Skill processes a GA SOS election calendar PDF into election metadata (dates, deadlines) in the markdown format | PDF reading approach (native Claude), calendar field mapping, election overview format integration |
| SKL-04 | Skill enriches candidate markdown with bios, photo URLs, and contact info from web research | Agent team coordination, web research sources, confidence annotation patterns, candidate file format |
</phase_requirements>

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python 3.13 | 3.13 | Runtime | Project standard per `.python-version` |
| Typer | >=0.15.0 | CLI for normalizer commands | Established project CLI framework |
| Loguru | >=0.7.0 | Logging in normalizer | Established project logging |
| Hypothesis | >=6.100 (NEW) | Property-based testing for normalizer | Required by CONTEXT testing strategy |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| re (stdlib) | N/A | Regex for normalizer rules | Title case, URL normalization, content validation |
| uuid (stdlib) | N/A | UUID generation in normalizer | Generating missing IDs |
| pathlib (stdlib) | N/A | File path handling | All file operations |
| csv (stdlib) | N/A | CSV reading in synthetic fixture creation | Test fixtures |
| json (stdlib) | N/A | JSON report output | Normalizer reports |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Python `str.title()` | Custom smart title case | `str.title()` breaks on suffixes (III -> Iii), Scottish prefixes (McDonald -> Mcdonald), and other edge cases. Custom is required. |
| PDF parsing library (pdfplumber) | Claude native PDF reading | CONTEXT locks decision: "AI reads PDFs directly. No PDF parsing library needed." Claude can read PDFs natively. |
| regex library | re (stdlib) | stdlib `re` is sufficient for normalizer rules. No need for external regex library. |

### Not Adding

No new Python dependencies are needed for the normalizer -- it uses only stdlib modules plus the existing Typer/Loguru stack. Hypothesis needs to be added as a dev dependency for property-based testing.

**Installation:**
```bash
uv add --dev hypothesis
```

## Architecture Patterns

### Recommended Project Structure

```
.claude/
├── skills/
│   ├── includes/                     # Shared prompt fragments
│   │   ├── csv-columns.md            # SOS CSV column mapping reference
│   │   ├── format-rules.md           # Common formatting rules
│   │   └── contest-patterns.md       # Contest name parsing examples
│   ├── qualified-candidates/         # SKL-01
│   │   ├── SKILL.md                  # Main skill instructions
│   │   └── examples/                 # Example outputs
│   ├── normalize/                    # SKL-02 (skill wrapper for CLI)
│   │   └── SKILL.md
│   ├── election-calendar/            # SKL-03
│   │   └── SKILL.md
│   ├── candidate-enrichment/         # SKL-04
│   │   └── SKILL.md
│   └── process-election/             # Orchestrator
│       └── SKILL.md
├── commands/                         # Legacy format (namespaced)
│   ├── election.process.md           # /election:process
│   ├── election.enrich.md            # /election:enrich
│   ├── election.normalize.md         # /election:normalize
│   ├── election.calendar.md          # /election:calendar
│   └── election.pipeline.md          # /election:pipeline
src/voter_api/
├── lib/
│   └── normalizer/                   # New library
│       ├── __init__.py               # Public API
│       ├── rules.py                  # Individual normalization rules
│       ├── title_case.py             # Smart title case implementation
│       ├── report.py                 # Report generation (terminal + JSON)
│       ├── types.py                  # Internal data types
│       └── uuid_handler.py           # UUID generation and file renaming
├── cli/
│   └── normalize_cmd.py              # CLI commands
data/
├── import/                           # Gitignored, SOS source files
│   ├── .gitkeep
│   └── (SOS CSV/PDF files)
├── candidates/                       # Populated by skills
│   └── (candidate markdown files)
tests/
├── unit/
│   └── lib/
│       └── test_normalizer/
│           ├── __init__.py
│           ├── test_title_case.py     # Smart title case unit tests
│           ├── test_rules.py          # Individual rule tests
│           ├── test_golden_files.py   # Before/after fixture tests
│           └── test_idempotency.py    # Property-based idempotency tests
├── fixtures/
│   └── normalizer/
│       ├── before/                   # Pre-normalization markdown
│       ├── after/                    # Expected post-normalization markdown
│       └── synthetic.csv             # Synthetic SOS CSV fixture
```

### Pattern 1: Claude Code Skill File Structure

**What:** Each skill is a directory with SKILL.md as the entrypoint, optional supporting files for examples and reference material.

**When to use:** For all 5 skills defined in this phase.

**Key design points from official docs:**
- SKILL.md supports YAML frontmatter with fields: `name`, `description`, `argument-hint`, `disable-model-invocation`, `allowed-tools`, `context`, `agent`
- Skills reference format specs via relative paths in instructions, not by embedding content
- `$ARGUMENTS` placeholder receives all arguments passed after the skill name
- `$0`, `$1`, etc. access individual positional arguments
- `!` backtick syntax runs shell commands before skill content reaches Claude (preprocessing)
- `${CLAUDE_SKILL_DIR}` resolves to the directory containing the SKILL.md file
- Keep SKILL.md under 500 lines; move reference material to supporting files

**Example (qualified-candidates skill):**
```yaml
---
name: qualified-candidates
description: Process a GA SOS qualified candidates CSV into per-election structured markdown files. Use when importing new election data from the Georgia Secretary of State.
argument-hint: <csv-file-path> [--direct]
disable-model-invocation: true
---

# Qualified Candidates Processor

Process the GA SOS qualified candidates CSV at `$0` into structured election markdown files.

## Format References

Read these format specifications before generating any output:
- Election overview format: [docs/formats/markdown/election-overview.md](docs/formats/markdown/election-overview.md)
- Single-contest format: [docs/formats/markdown/single-contest.md](docs/formats/markdown/single-contest.md)
- Multi-contest format: [docs/formats/markdown/multi-contest.md](docs/formats/markdown/multi-contest.md)
- Candidate file format: [docs/formats/markdown/candidate-file.md](docs/formats/markdown/candidate-file.md)

## CSV Column Reference

Read the column mapping: [csv-columns.md](${CLAUDE_SKILL_DIR}/../includes/csv-columns.md)

## Steps

1. Validate CSV headers match expected 11 columns
2. Parse CONTEST NAME to infer election type, Body ID, Seat ID
3. Group candidates by contest
4. Deduplicate candidates appearing in multiple county rows
5. Generate election directory structure
...
```

### Pattern 2: Namespace Commands (.claude/commands/)

**What:** The existing project uses dotted namespace convention in `.claude/commands/` for command groups (e.g., `speckit.plan.md` creates `/speckit:plan`).

**When to use:** For all 5 `/election:*` commands defined in CONTEXT.

**Key points:**
- Files in `.claude/commands/` still work and support the same frontmatter as SKILL.md
- If a skill and a command share the same name, the skill takes precedence
- Namespace convention: `election.process.md` creates `/election:process`
- Commands and skills serve different purposes here: commands are explicit invocations, skills can also auto-trigger

**Example (election.process.md):**
```yaml
---
description: Process a GA SOS qualified candidates CSV into structured election markdown files
---

$ARGUMENTS

Read the skill instructions and execute the qualified-candidates workflow.
```

### Pattern 3: Library-First Normalizer

**What:** The normalizer follows the same pattern as `lib/converter/` -- standalone library with public API via `__init__.py`, CLI wrapper in `cli/normalize_cmd.py`, and comprehensive unit tests.

**When to use:** For SKL-02 (the normalizer is both a skill and a library).

**Key pattern from existing converter:**
```python
# lib/normalizer/__init__.py - Public API
from voter_api.lib.normalizer.normalize import normalize_directory, normalize_file
from voter_api.lib.normalizer.report import NormalizationReport

__all__ = [
    "normalize_directory",
    "normalize_file",
]
```

### Pattern 4: Smart Title Case

**What:** Custom title case that handles edge cases in GA election data.

**When to use:** Normalizer rule for candidate names, occupation fields, contest names.

**Key edge cases from the actual SOS data:**
```python
# Suffixes that stay uppercase
UPPERCASE_SUFFIXES = {"III", "II", "IV", "JR", "SR"}

# Scottish/compound prefixes
SPECIAL_PREFIXES = {
    "Mc": lambda rest: "Mc" + rest[0].upper() + rest[1:].lower(),
    "Mac": lambda rest: "Mac" + rest[0].upper() + rest[1:].lower(),
    "O'": lambda rest: "O'" + rest[0].upper() + rest[1:].lower(),
}

# Words that stay lowercase (unless first word)
LOWERCASE_WORDS = {"of", "the", "and", "in", "for", "at", "by", "to"}

# Acronyms that stay uppercase in occupations
OCCUPATION_ACRONYMS = {"CEO", "CFO", "CPA", "LLC", "LLP", "CNC", "RN", "MD", "DDS", "JD", "PhD"}

# Examples from actual SOS data:
# "JOHN A COWAN JR" -> "John A. Cowan Jr"
# "DAVID LAFAYETTE MINCEY III" -> "David Lafayette Mincey III"
# "LISA WILLIAMS GARRETT-BOYD" -> "Lisa Williams Garrett-Boyd"
# "CARLOS ANTONIO MCCLOUD" -> "Carlos Antonio McCloud"
# "SOFTWARE ENGINEER" -> "Software Engineer"
# "CNC MACHINIST" -> "CNC Machinist"
# "RETIRED EDUCATOR" -> "Retired Educator"
# "NOT EMPLOYED" -> "Not Employed"
```

### Pattern 5: Report Generation (Terminal + JSON)

**What:** Dual-format report following the existing converter pattern.

**When to use:** Normalizer output reporting.

**Existing pattern from `lib/converter/report.py`:**
- `ConversionReport` class tracks file results (success/failure/warnings)
- `render_terminal()` produces human-readable summary table
- `write_json()` produces machine-readable JSON file
- File results include: path, status, record counts, errors, warnings

The normalizer report should follow this same pattern with:
- Files processed count
- Changes applied per file (field-level diffs)
- Warnings for ambiguous cases (ALL CAPS remnants, possible duplicate candidates)
- UUIDs generated count
- Files renamed count

### Anti-Patterns to Avoid

- **Embedding format specs in skill prompts:** Skills MUST reference `docs/formats/markdown/` files, not duplicate their content. This was an explicit CONTEXT decision.
- **Making normalizer non-idempotent:** Running normalizer twice on the same file must produce identical output. This is the fundamental contract.
- **Auto-invoking normalizer from skills:** CONTEXT decision: "User runs normalizer independently after skill output. Not auto-invoked by skills."
- **Using str.title() for title case:** Breaks on III, Jr, McDonald, hyphenated names, etc. Must use custom smart title case.
- **Generating UUIDs in the converter:** The converter must never generate UUIDs (per uuid-strategy.md). The normalizer generates them for records missing IDs.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| PDF text extraction | Custom PDF parser | Claude's native PDF reading | CONTEXT decision. Claude reads PDFs directly. |
| CSV parsing | Custom tokenizer | Python stdlib `csv` module | Already handles quoted fields, encoding |
| UUID generation | Custom ID scheme | `uuid.uuid4()` | Per uuid-strategy.md, use random v4 UUIDs |
| Markdown generation | Template engine | String formatting with format spec reference | Skills generate markdown by following spec instructions |
| Title case | `str.title()` | Custom smart title case in `lib/normalizer/title_case.py` | Edge cases are too numerous for stdlib |
| Agent orchestration | Custom agent framework | Claude Code's built-in cooperative team / `context: fork` | Framework already handles agent spawning and coordination |

**Key insight:** The skills ARE prompt engineering, not code. The only Python code to build is the normalizer library. Everything else is markdown instruction files that leverage Claude's capabilities.

## Common Pitfalls

### Pitfall 1: Contest Name Parsing Ambiguity

**What goes wrong:** The SOS CONTEST NAME column is wildly inconsistent. The same office type appears in dozens of variations:
- `Board of Commissioner District 2 (D)` (singular, no comma)
- `Board of Commissioners - District 2 (R)` (plural, dash separator)
- `BOARD OF EDUCATION AT LARGE-POST 7` (all caps, hyphen separator)
- `Board of Education D3` (abbreviated district)
- `Board of Education, District 1` (comma separator)
- `Board of Commissioner District 2(R)` (no space before party)

**Why it happens:** Different counties submit data with different formatting conventions. No centralized standard.

**How to avoid:** The qualified-candidates skill prompt must include extensive examples of these variations. The `includes/contest-patterns.md` file should contain a representative sample of actual contest name patterns grouped by type. AI parsing is the right approach here -- a deterministic rule set would be enormous.

**Warning signs:** If the skill consistently misparses a pattern, add that pattern to the examples. Test with all three CSVs (May 19 has the most variety at 2,346 rows).

### Pitfall 2: Multi-County Candidate Deduplication

**What goes wrong:** The same candidate appears in multiple rows for multi-county contests (e.g., U.S. House candidates appear once per county in their district). Without deduplication, a candidate could appear 15+ times.

**Why it happens:** The SOS CSV structure is county-centric -- each row represents a candidate's appearance in a county's ballot.

**How to avoid:** Group by (CONTEST NAME, CANDIDATE NAME, POLITICAL PARTY) before generating output. The skill must collect all county rows for multi-county contests (US House, State House/Senate, judicial circuits) and emit each candidate only once. The COUNTY column determines which county files reference the contest.

**Warning signs:** Candidate count in generated files exceeds unique candidate count from CSV. Test with US House District 11 in the May 19 CSV (multiple counties, multiple candidates).

### Pitfall 3: Normalizer Non-Idempotency

**What goes wrong:** Running the normalizer twice produces different output -- typically from UUID generation, date reformatting, or title case instability.

**Why it happens:** UUID generation is not idempotent by definition. Title case edge cases may oscillate between runs if rules conflict.

**How to avoid:** UUID generation must only trigger when ID is MISSING. If ID is present and valid, leave it unchanged. Title case rules must be ordered deterministically with no ambiguity. Golden file tests MUST verify: normalize(input) == expected AND normalize(expected) == expected (idempotency check).

**Warning signs:** Golden file tests fail on second run. `git diff` shows changes after re-running normalizer on already-normalized files.

### Pitfall 4: Skill Context Overflow

**What goes wrong:** Skill instructions plus referenced format specs exceed Claude's effective context, causing the model to miss rules or hallucinate.

**Why it happens:** Five format specs (single-contest, multi-contest, overview, candidate-file, county-reference) plus vocabularies plus includes could be 20+ pages.

**How to avoid:** Skills reference format specs but instruct Claude to read them on demand (not all at once). The `includes/` directory provides curated excerpts of the most critical rules. The qualified-candidates skill should load format specs in stages: overview format first, then contest formats as needed.

**Warning signs:** Skill produces markdown that doesn't match format specs. Metadata table fields are wrong or missing.

### Pitfall 5: File Naming Collisions in Candidate Stubs

**What goes wrong:** Two candidates with the same name get the same placeholder filename (`jane-doe-00000000.md`), causing one to overwrite the other.

**Why it happens:** Before UUID assignment, placeholder filenames are based only on the slugified name.

**How to avoid:** The skill should detect name collisions during stub creation and use a sequence number or temporary disambiguator in the placeholder filename. The normalizer then generates UUIDs and renames to final names (`jane-doe-a3f2e1b4.md`).

**Warning signs:** Fewer candidate files than unique candidates in the CSV.

### Pitfall 6: Shared Includes Path Resolution

**What goes wrong:** Skills reference `${CLAUDE_SKILL_DIR}/../includes/csv-columns.md` but the path doesn't resolve correctly.

**Why it happens:** `${CLAUDE_SKILL_DIR}` resolves to the skill's own directory. The `includes/` directory is a sibling, requiring `../includes/` traversal.

**How to avoid:** Test path resolution by running the skill and verifying Claude reads the include files. Use `${CLAUDE_SKILL_DIR}` consistently. Alternative: use absolute project-root-relative paths in instructions (e.g., `.claude/skills/includes/csv-columns.md`).

**Warning signs:** Skill output doesn't follow rules documented in include files.

## Code Examples

### Normalizer - Smart Title Case Function

```python
# Source: Custom implementation based on SOS data analysis

import re

# Suffixes that stay ALL CAPS
UPPERCASE_SUFFIXES = frozenset({"III", "II", "IV", "JR", "SR"})

# Words that stay lowercase (unless first or last)
LOWERCASE_WORDS = frozenset({"of", "the", "and", "in", "for", "at", "by", "to"})

# Acronyms in occupations
OCCUPATION_ACRONYMS = frozenset({
    "CEO", "CFO", "CPA", "LLC", "LLP", "CNC", "RN", "MD",
    "DDS", "JD", "PhD", "CTO", "COO", "VP", "HR",
})


def smart_title_case(text: str, *, is_occupation: bool = False) -> str:
    """Apply smart title case handling edge cases in GA election data.

    Args:
        text: Input text, typically ALL CAPS from SOS data.
        is_occupation: If True, also preserve occupation acronyms.

    Returns:
        Title-cased text with edge cases handled.
    """
    if not text or not text.strip():
        return text

    words = text.split()
    result = []

    for i, word in enumerate(words):
        upper = word.upper()

        # Check for suffixes (III, Jr, etc.)
        if upper in UPPERCASE_SUFFIXES:
            result.append(upper if upper in {"III", "II", "IV"} else upper.title())
            continue

        # Check for occupation acronyms
        if is_occupation and upper in OCCUPATION_ACRONYMS:
            result.append(upper)
            continue

        # Handle hyphenated words
        if "-" in word:
            parts = word.split("-")
            result.append("-".join(_title_word(p) for p in parts))
            continue

        # Handle Mc/Mac prefixes
        if len(word) > 2 and upper[:2] == "MC":
            result.append("Mc" + word[2:].title())
            continue
        if len(word) > 3 and upper[:3] == "MAC" and len(word) > 4:
            result.append("Mac" + word[3:].title())
            continue

        # Handle O' prefix
        if len(word) > 2 and upper[:2] == "O'" :
            result.append("O'" + word[2:].title())
            continue

        # Lowercase words (not first or last)
        if i > 0 and i < len(words) - 1 and word.lower() in LOWERCASE_WORDS:
            result.append(word.lower())
            continue

        result.append(_title_word(word))

    return " ".join(result)


def _title_word(word: str) -> str:
    """Title case a single word."""
    if not word:
        return word
    return word[0].upper() + word[1:].lower()
```

### Normalizer - URL Normalization

```python
# Source: Based on CONTEXT.md URL handling rules

import re
from urllib.parse import urlparse


def normalize_url(url: str) -> str:
    """Normalize a URL to lowercase with https protocol.

    Args:
        url: Raw URL string (may be missing protocol, uppercase, etc.).

    Returns:
        Normalized URL with https:// prefix and lowercase.
    """
    if not url or url.strip() in ("--", "\u2014", ""):
        return url

    url = url.strip()

    # Add protocol if missing
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    # Upgrade http to https
    if url.startswith("http://"):
        url = "https://" + url[7:]

    # Lowercase the URL
    return url.lower()
```

### Normalizer - Date Format Normalization

```python
# Source: Based on format specs (MM/DD/YYYY for contest tables)

import re


def normalize_date(date_str: str, *, target_format: str = "slash") -> str:
    """Normalize a date string to the target format.

    Args:
        date_str: Input date string in various formats.
        target_format: "slash" for MM/DD/YYYY, "iso" for YYYY-MM-DD.

    Returns:
        Normalized date string.
    """
    if not date_str or date_str.strip() in ("--", "\u2014"):
        return date_str

    # Try to parse MM/DD/YYYY
    match = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", date_str.strip())
    if match:
        month, day, year = match.groups()
        if target_format == "slash":
            return f"{int(month):02d}/{int(day):02d}/{year}"
        return f"{year}-{int(month):02d}-{int(day):02d}"

    # Try to parse YYYY-MM-DD
    match = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", date_str.strip())
    if match:
        year, month, day = match.groups()
        if target_format == "iso":
            return f"{year}-{int(month):02d}-{int(day):02d}"
        return f"{int(month):02d}/{int(day):02d}/{year}"

    return date_str  # Return unchanged if unparseable
```

### CLI Registration Pattern

```python
# Source: Existing pattern from cli/app.py and cli/convert_cmd.py

# cli/normalize_cmd.py
import typer

normalize_app = typer.Typer()


@normalize_app.command("elections")
def normalize_elections_cmd(
    directory: Path = typer.Argument(..., help="Election directory to normalize."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Report changes without writing."),
    report: Path | None = typer.Option(None, "--report", help="Write JSON report to file."),
) -> None:
    """Normalize all election markdown files in a directory."""
    ...


@normalize_app.command("candidates")
def normalize_candidates_cmd(
    directory: Path = typer.Argument(..., help="Candidates directory to normalize."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Report changes without writing."),
    report: Path | None = typer.Option(None, "--report", help="Write JSON report to file."),
) -> None:
    """Normalize all candidate markdown files in a directory."""
    ...


# In cli/app.py - add to _register_subcommands():
# from voter_api.cli.normalize_cmd import normalize_app
# app.add_typer(normalize_app, name="normalize", help="Normalize markdown files")
```

### SKILL.md Frontmatter Reference

```yaml
# Source: Official Claude Code docs (https://code.claude.com/docs/en/skills)

# For task-oriented skills (qualified-candidates, election-calendar)
---
name: qualified-candidates
description: Process a GA SOS qualified candidates CSV into structured election markdown files
argument-hint: <csv-file-path> [--direct]
disable-model-invocation: true
---

# For enrichment skill (needs web access)
---
name: candidate-enrichment
description: Enrich candidate markdown files with bios, photos, and contact info from web research
argument-hint: <candidates-dir> [--depth full|basic|minimal]
disable-model-invocation: true
allowed-tools: Read, Write, Grep, Glob, Bash, WebSearch, WebFetch
---

# For orchestrator (runs sub-skills)
---
name: process-election
description: Full election data pipeline - CSV to normalized markdown
argument-hint: <csv-file-path> [--direct]
disable-model-invocation: true
---
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `.claude/commands/` flat files | `.claude/skills/<name>/SKILL.md` directories | 2025 Q3 | Skills support directories, supporting files, frontmatter config |
| Manual election file creation | Formalized skills + normalizer | Phase 3 (this phase) | Reproducible, consistent output |
| Existing ~200 markdown files (pre-format-spec) | Regenerated from CSV via skills | Phase 3 | Files match enhanced format spec from Phase 1 |

**Key compatibility note:** `.claude/commands/` files still work. The CONTEXT decision to have both skills AND commands means we use the skills directory for the full-featured skill and the commands directory for the namespaced `/election:*` invocations. Commands can delegate to skills.

## Open Questions

1. **Shared includes path resolution**
   - What we know: `${CLAUDE_SKILL_DIR}` resolves to the skill's directory. Includes are in `.claude/skills/includes/`.
   - What's unclear: Whether `${CLAUDE_SKILL_DIR}/../includes/` reliably resolves in all Claude Code contexts.
   - Recommendation: Test with a simple skill first. Fallback: use project-root-relative paths (`.claude/skills/includes/csv-columns.md`).

2. **Agent team coordination for enrichment**
   - What we know: Claude Code supports cooperative teams and `context: fork` for subagent execution. The enrichment skill needs to process thousands of candidates in parallel.
   - What's unclear: Exact syntax for cooperative team coordination, rate limiting behavior, how results aggregate.
   - Recommendation: Start with sequential processing for the enrichment skill. Add parallelization via `context: fork` + coordinator pattern once the single-agent version works correctly.

3. **Checkpoint file format for resumable processing**
   - What we know: Dual checkpointing (DB `import_jobs` + JSONL file). Converter and importer already use `import_jobs`.
   - What's unclear: Whether skills can access the database directly for checkpointing, or if JSONL-only checkpoints are more practical.
   - Recommendation: JSONL checkpoint file only for skill-level checkpointing (skills run in Claude Code context, not as API requests). DB integration is for the normalizer CLI, which runs as a Python process.

4. **Hypothesis integration with existing test infrastructure**
   - What we know: Hypothesis is not currently a dependency. pytest is configured with asyncio_mode=auto.
   - What's unclear: Whether Hypothesis generates markdown inputs complex enough to exercise normalizer edge cases, or if hand-crafted golden files are more valuable.
   - Recommendation: Add hypothesis as dev dependency. Use @given with custom strategies for normalizer property tests. Golden files remain the primary test mechanism; Hypothesis supplements by checking properties like idempotency across random inputs.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + Hypothesis 6.x |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/unit/lib/test_normalizer/ -x` |
| Full suite command | `uv run pytest --cov=voter_api --cov-report=term-missing` |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SKL-01 | Skill produces valid markdown from CSV | integration (pipeline) | `uv run voter-api normalize elections data/elections/2026-05-19/ --dry-run` | Wave 0 |
| SKL-02 | Normalizer enforces formatting rules | unit | `uv run pytest tests/unit/lib/test_normalizer/ -x` | Wave 0 |
| SKL-02 | Normalizer is idempotent | unit (property) | `uv run pytest tests/unit/lib/test_normalizer/test_idempotency.py -x` | Wave 0 |
| SKL-02 | Normalizer golden file tests | unit | `uv run pytest tests/unit/lib/test_normalizer/test_golden_files.py -x` | Wave 0 |
| SKL-02 | Normalizer CLI runs successfully | integration | `uv run voter-api normalize elections data/elections/2026-05-19/ --dry-run` | Wave 0 |
| SKL-03 | Calendar skill produces valid metadata | integration (pipeline) | `uv run voter-api normalize elections data/elections/2026-05-19/ --dry-run` | Wave 0 |
| SKL-04 | Enrichment skill adds valid candidate data | manual | Inspect enriched candidate files, run normalizer | N/A (manual) |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/unit/lib/test_normalizer/ -x && uv run ruff check . && uv run ruff format --check .`
- **Per wave merge:** `uv run pytest --cov=voter_api --cov-report=term-missing`
- **Phase gate:** Full suite green + normalizer produces clean output on all three election CSVs

### Wave 0 Gaps

- [ ] `tests/unit/lib/test_normalizer/__init__.py` -- package init
- [ ] `tests/unit/lib/test_normalizer/test_title_case.py` -- smart title case rules
- [ ] `tests/unit/lib/test_normalizer/test_rules.py` -- URL, date, occupation rules
- [ ] `tests/unit/lib/test_normalizer/test_golden_files.py` -- before/after fixtures
- [ ] `tests/unit/lib/test_normalizer/test_idempotency.py` -- Hypothesis property tests
- [ ] `tests/fixtures/normalizer/` -- golden file fixtures directory
- [ ] `tests/fixtures/normalizer/synthetic.csv` -- synthetic SOS CSV fixture
- [ ] Hypothesis dev dependency: `uv add --dev hypothesis`

## Sources

### Primary (HIGH confidence)

- [Claude Code Skills Documentation](https://code.claude.com/docs/en/skills) -- Full skills format, frontmatter reference, supporting files, invocation control, subagent execution, dynamic context injection
- Project codebase analysis -- `lib/converter/` pattern, `cli/app.py` registration, `docs/formats/` specifications, existing SOS CSV data
- SOS CSV data analysis -- Direct inspection of all three CSV files, unique contest name analysis showing formatting inconsistencies

### Secondary (MEDIUM confidence)

- [Anthropic Skills GitHub](https://github.com/anthropics/skills) -- Public skills repository showing community patterns
- [Agent Skills open standard](https://agentskills.io) -- Cross-tool compatibility standard that Claude Code follows

### Tertiary (LOW confidence)

- Agent team coordination specifics -- Claude Code's cooperative team support is documented but exact coordination patterns for batch processing at scale need validation during implementation

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- normalizer uses only stdlib + existing project dependencies. Skills are markdown files.
- Architecture: HIGH -- follows established `lib/` pattern from converter. Skills format verified against official docs.
- Pitfalls: HIGH -- derived from direct analysis of actual SOS CSV data (2,346 rows with contest name variations).
- Agent coordination: MEDIUM -- cooperative team pattern is documented but batch enrichment at scale (2,000+ candidates) hasn't been tested.

**Research date:** 2026-03-15
**Valid until:** 2026-04-15 (stable -- skills format is unlikely to change rapidly; normalizer rules are project-specific)
