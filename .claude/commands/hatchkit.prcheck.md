---
description: Diagnose and fix failing GitHub Actions checks on the current PR
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Prerequisites

- The `gh` CLI must be installed and authenticated (`gh auth status`).
- A pull request must exist for the current branch.

## Goal

Fetch all GitHub Actions check statuses on the current PR. Make a plan to fix the failing checks. Using sub-agents for each failing check, address the issues and commit the changes. Once all have been addressed, perform all the same checks that the GitHub Actions workflows would and fix any issues found then. Finally, commit, push, then reply to the PR with a summary of the changes. This command MUST run only after a PR has been created and is active.

## Operating Constraints

- Keep changes focused on addressing failing checks — no unrelated modifications.
- The project constitution (`.specify/memory/constitution.md`) is non-negotiable; constitution conflicts are automatically CRITICAL.
- All local checks, tests, linters, formatters, and quality gates that run in CI MUST be executed locally before pushing. Do not rely on CI to catch issues that can be found locally.

## Execution Steps

### 1. Discover the PR

Auto-detect the PR number from the current branch:

```bash
hatchkit pr info
```

If no PR is found, stop and inform the user.

### 2. Fetch GitHub Actions Check Statuses

Retrieve the status of all checks on the current PR:

```bash
hatchkit pr checks
```

If all checks are passing, stop and inform the user.

For each **failing** check, fetch the detailed failure logs using the `gh` CLI:

```bash
gh run view <run-id> --log-failed
```

The `<run-id>` can be obtained from the check output or by listing workflow runs:

```bash
gh run list --branch $(git branch --show-current) --limit 5
```

Capture the relevant error output for each failing job — this is the primary input for diagnosis.

### 3. Deduplicate and Categorize

Before implementing anything, group failing checks by workflow and job. Multiple jobs may fail for the same root cause (e.g., a missing import causes both lint and test failures).

Categorize each failure as:

- **Code fix** — bug, type error, missing import, logic error
- **Test fix** — failing assertions, missing fixtures, stale test data
- **CI/workflow config** — workflow YAML, environment variables, dependency issues
- **Documentation update** — if a docs-publishing or docs-lint check fails

### 4. Prioritize and Plan

Order work by severity and dependencies. Outline the specific changes needed per file. If the user provided input, incorporate their priorities.

### 5. Implement Fixes

Use a **sub-agent for each failing workflow/job** to address the issues in parallel. Each sub-agent should receive the relevant log output from Step 2, the categorization from Step 3, and the plan from Step 4.

Address each deduplicated failure cluster, not each individual error line. Make the necessary code changes, test fixes, or configuration adjustments.

### 6. Reproduce CI Locally

Run the same checks that the failing GitHub Actions workflows execute locally. At minimum:

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest
```

If the failing workflow runs additional checks (e.g., E2E tests, type checking, coverage thresholds), run those locally too. Match the CI environment as closely as possible.

Fix any failures found. If available, use the SonarQube MCP to check code quality.

### 7. Commit and Push

Commit with a summary-style message grouped by theme, not per-check:

```
fix(ci): address failing GitHub Actions checks

- fix missing import causing lint failure
- update test fixture to match new schema
- add missing env var to E2E workflow
```

Push to the PR branch.

### 8. Verify CI

After pushing, run `hatchkit pr checks` to confirm previously failing checks now pass:

```bash
hatchkit pr checks
```

If any check that was failing before is still failing, investigate and fix. Repeat Steps 5–8 until all targeted checks pass.

### 9. Finalize Comment

Add a final PR comment summarizing:
- How many checks were fixed
- Key changes grouped by workflow/job
- Any checks that remain failing with an explanation of why they are outside scope (e.g., pre-existing failures on the base branch)
