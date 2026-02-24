# Phase 2 v2 - `github-gate` Hardening and Test Plan

This document captures deferred work after Phase 2 core implementation.

## Goals
- Add comprehensive automated tests.
- Harden reliability behavior under upstream failures.
- Validate CLI output contract with stable fixtures.
- Tighten extraction heuristics and edge-case handling.

## Scope
1. Add unit tests for URL parsing/normalization.
2. Add unit tests for retry classifier and backoff decisions.
3. Add unit tests for breadth-first traversal ordering.
4. Add unit tests for byte-budget enforcement and token estimation.
5. Add unit tests for docs/tests/code selectors.
6. Add integration-like tests with mocked `ghapi` responses.
7. Add CLI contract tests (golden-file markdown snapshots).
8. Add negative tests for malformed upstream payloads and mapping to typed exceptions.
9. Add optional env-var gate for live smoke test execution (`RUN_LIVE_GITHUB_SMOKE=1`) for CI stability control.

## Test Matrix

### URL Parsing
- canonical repo URL
- trailing slash
- non-GitHub host
- owner-only path
- extra path segments

### Retry Policy
- retry on `429/502/503/504`
- retry on rate-limit `403` only
- no retry on non-rate-limit `403`, `404`, `400`
- timeout and network error paths

### Breadth-First Retrieval
- top-level files selected before nested files
- deterministic ordering at equal depth
- entrypoint seeding does not violate deterministic BFS continuation

### Byte Budgeting
- stop at section byte cap (`docs/tests/code`)
- enforce max single-file byte cap
- estimated tokens tracked as `bytes / 4` (conservative)

### Extraction Behavior
- one About/homepage documentation page max (no recursive link-following)
- docs directory discovery
- test path detection
- entrypoint-first code extraction followed by BFS

### CLI Contract
- `--entities all`
- entity subset selection
- missing sections marked `Not found`
- unrequested sections marked `Not requested`
- stable section order and extraction stats section

## Deliverables
- New tests under `tests/github_gate/`.
- Optional fixture repos/mocks under `tests/fixtures/github_gate/`.
- Updated `impl-process/RESUME-CODING.md` with test run output summary.

## Exit Criteria
- Tests pass in CI/local without live GitHub dependency.
- Deterministic output for selector and CLI contract tests.
- Exception and retry behavior aligned with `docs/architecture-and-design.md`.
- Live smoke test can be toggled off by default in CI and enabled explicitly via env var.
