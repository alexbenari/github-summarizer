# Phase 2 - Add Live CLI Smoke Test for `github-gate`

Implement one basic integration smoke test for the `github-gate` CLI using real network responses.

## Goal
Validate that CLI end-to-end extraction works against a real public GitHub repository and produces:
1. all required markdown sections
2. sections in the expected order
3. actual content (not `Not requested` / `Not found`) in each extracted section

This is intentionally a single high-level smoke test. Detailed mocked tests remain in v2.

## Test To Add
Create:
- `tests/smoke/test_github_gate_cli_live_smoke.py`

## Live Test Constraints
- Use real GitHub and real external page fetches (no mocks).
- Use one known public repository with docs/tests/code/build metadata, e.g.:
  - `https://github.com/psf/requests`

## Execution Model
- Invoke CLI as subprocess (not direct function call):
  - `python -m app.github_gate.cli ...`
- Use `tmp_path` for output markdown file.
- Use entities:
  - `metadata,languages,tree,readme,documentation,build_package,tests,code`

## Assertions (Required)
1. Process exits with code `0`.
2. Output markdown file exists and is non-empty.
3. The following top-level sections exist and are in this exact order:
   1. `# Repository Metadata`
   2. `# Language Stats`
   3. `# Directory Tree`
   4. `# README`
   5. `# Documentation`
   6. `# Build and Package Data`
   7. `# Tests`
   8. `# Code`
   9. `# Extraction Stats`
   10. `# Warnings`
4. For sections 1-8:
   - section body is not empty
   - section body is not exactly `Not requested`
   - section body is not exactly `Not found`
5. `# Extraction Stats` contains at least:
   - `total_utf8_bytes:`
   - `total_estimated_tokens:`

## Practical Stability Note
Run this live smoke test as part of normal test execution for now (no env-var gate).
Potential future hardening (tracked in v2): make live smoke opt-in behind `RUN_LIVE_GITHUB_SMOKE=1` to reduce CI flakiness.

## Suggested Test Implementation Notes
- Use `sys.executable` for subprocess python path.
- Use `subprocess.run(..., capture_output=True, text=True, timeout=180)`.
- Parse markdown section positions using `str.find()` and assert monotonic increase.
- For section body checks, slice text between current section start and next section start.
- On failure, include `stdout` and `stderr` in assertion message.

## Acceptance Criteria
- New test file exists and passes locally as part of normal `pytest` execution.
- Live smoke test runs as part of normal `pytest` execution in v1 (no env-var gate).
- Test validates section order and non-empty content for extracted sections.
