# RESUME-CODEX

## Session Snapshot
- Date: 2026-02-22
- Project: GitHub repository summarizer API
- Mode: discussion/documentation only (no code implementation)

## What Was Updated
- Expanded `docs/architecture-and-design.md` into an implementable design spec with:
  - API request/response contract and HTTP error mapping
  - Hybrid 2-phase end-to-end flow across modules (baseline fetch + budget-aware expansion)
  - Detailed responsibilities/interfaces for `service`, `github-gate`, `repo-processor`, `llm-gate`
  - Repository content selection and token-budget strategy
  - Concrete GitHub timeout/retry defaults for transient failures
  - v1 inaccessible/private repository handling unified under `404` (unauthenticated mode)
  - Explicit `github-gate` interface methods, including `get_documentation`, `get_tests`, and `get_code`
  - GitHub adapter implementation decision: use `ghapi` in v1
  - Documentation retrieval policy: single direct README-linked page plus `docs/` and `documentation/` tree extraction with limits
  - Commit title retrieval deferred from v1 scope
  - Added production prompt contract at `llm-gate/prompt.md` (strict JSON schema + style constraints)
  - Added implementation prompts for github-gate:
    - `impl-process/phase2-github-gate.md` (core + CLI, no automated tests)
    - `impl-process/v2/phase2-github-gate-v2.md` (deferred hardening and automated test plan)
  - Phase 2 prompt now requires:
    - entrypoint seeding then breadth-first traversal for code retrieval
    - UTF-8 byte-based budgeting with token estimates
    - best-effort partial-failure behavior with warning reporting
    - strict markdown output format for CLI payload export
  - Added `config/non-informative-files.json` with default file/dir/pattern exclusions
  - Prompt contract and output validation plan
  - Logging/observability format and security notes
  - Reliability constraints and testing strategy
  - Explicit list of open decisions

## Current Agreed Direction
- Keep v1 scope small: one endpoint (`POST /summarize`), public repos only.
- Use GitHub API access through adapter (`github-gate`) without cloning repos.
- Implement `github-gate` using `ghapi`, while keeping retries/error mapping in adapter-owned policy.
- Use a hybrid retrieval strategy:
  - always fetch metadata/languages/tree/README first
  - then fetch additional artifacts incrementally based on remaining token budget
- Use a scoring + exclusion + truncation pipeline (`repo-processor`) to fit LLM context.
- Keep commit titles out of v1 retrieval for now.
- In `github-gate`, include explicit extraction helpers for documentation/tests/code with configurable limits.
- Use structured JSON output contract from LLM via `llm-gate`.
- Keep per-request sequential debug logs in one file.

## Open Decisions (Need User Input)
1. Final Nebius model id for v1.
2. Whether optional GitHub token support should be in v1 or v1.1.
3. Whether API should expose any confidence/uncertainty metadata.

## Suggested Next Discussion Step
- Finalize the three open decisions above, then derive:
  - final config schema (`runtime` + ignore rules),
  - concrete prompt template,
  - exception hierarchy and status-code mapping table with exact messages.

## Files To Read First On Resume
1. `docs/project-description.md`
2. `docs/architecture-and-design.md`
3. `RESUME-CODEX.md`
4. `llm-gate/prompt.md`
5. `impl-process/phase2-github-gate.md`
6. `impl-process/v2/phase2-github-gate-v2.md`
7. `config/non-informative-files.json`
