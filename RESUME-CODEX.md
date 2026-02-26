# RESUME-CODEX

## Session Snapshot
- Date: 2026-02-22
- Project: GitHub repository summarizer API
- Mode: discussion/documentation only (no code implementation)

## Latest Update (2026-02-25)
- Added phase-5 integration implementation spec at `impl-process/phase5-integration.md`.
- Added phase-5 coding-agent kickoff prompt at `impl-process/phase5-integration-kickoff.md`.
- Refactored github entity list into single source of truth at `app/github_gate/entities.py` and reused in CLI/service path.
- Removed hardcoded service-side requested-sections argument by adding `render_full_extraction_markdown(...)` in `app/github_gate/markdown_renderer.py`.
- Test maintenance after refactor:
  - updated `tests/test_phase5_integration_api.py` monkeypatch target to `render_full_extraction_markdown`
  - updated `tests/smoke/test_github_gate_cli_live_smoke.py` to skip on transient GitHub/network upstream failures
- Locked phase-5 decisions:
  - explicit error-to-HTTP mapping across github-gate/repo-processor/llm-gate exceptions
  - best-effort partial extraction for optional github categories
  - service must fetch same entity set as github-gate CLI `--entities all`
  - startup fail-fast validation via `ConfigValidator`
  - console progress logging + per-request debug log file
  - temporary milestone behavior: on repo-processor budget overflow, continue using overflowed/full extraction markdown instead of failing request
- Phase-5 spec includes required interfaces, orchestration contract, logging contract, and minimum integration test requirements.

## What Was Updated
- Expanded `docs/architecture-and-design.md` into an implementable design spec with:
  - API request/response contract and HTTP error mapping
  - End-to-end flow: one-pass github-gate extraction + repo-processor prompt-budget fitting
  - Detailed responsibilities/interfaces for `service`, `github-gate`, `repo-processor`, `llm-gate`
  - Repository content selection and token-budget strategy
  - Concrete GitHub timeout/retry defaults for transient failures
  - v1 inaccessible/private repository handling unified under `404` (unauthenticated mode)
  - Explicit `github-gate` interface methods, including `get_documentation`, `get_tests`, and `get_code`
  - GitHub adapter implementation decision: use `ghapi` in v1
  - Documentation retrieval policy: one About/homepage page (no recursive crawling) plus `docs/` and `documentation/` tree extraction with limits
  - Commit title retrieval deferred from v1 scope
  - Added production prompt contract at `app/llm_gate/prompt.md` (strict JSON schema + style constraints)
  - Added implementation prompts for github-gate:
    - `impl-process/phase2-github-gate.md` (core + CLI, no automated tests)
    - `impl-process/phase2-github-gate-1.1.md` (addendum: build/package extraction method)
    - `impl-process/v2/phase2-github-gate-v2.md` (deferred hardening and automated test plan)
    - `impl-process/phase2-github-gate-live-cli-smoke-test.md` (single live CLI smoke test spec)
  - Added phase-3 repo-processor implementation prompt:
    - `impl-process/phase3-repo-processor.md` (full-markdown input -> prompt-fit markdown output, budget bookkeeper, CLI)
  - Added phase-3 v2 hardening plan:
    - `impl-process/v2/phase3-repo-processor-v2.md` (strict budget-compliance fix + parser/truncation regression tests)
  - Added phase-4 implementation prompt:
    - `impl-process/phase4-llm-gate.md` (llm-gate core + CLI, strict output validation, timeout/retry defaults)
  - Refined phase-4 llm-gate spec:
    - simplified public interface to one method: `summarize(markdown_text, options=None) -> SummaryResult`
    - mandatory runtime config keys: `llm_gate.model_id`, `llm_gate.model_context_window_tokens`
    - default model config set to:
      - `llm_gate.model_id = Qwen/Qwen3-30B-A3B-Thinking-2507`
      - `llm_gate.model_context_window_tokens = 262000`
    - removed `summary/structure` 900-character caps from llm-gate validation rules
    - clarified CLI uses real LLM API calls (except explicit `--dry-run`)
    - aligned llm-gate input source to repo-processor output markdown
  - Updated `app/llm_gate/prompt.md`:
    - removed `maxLength: 900` for `summary` and `structure` in JSON schema
    - added explicit build/package section placeholder in user prompt template
  - Updated `docs/architecture-and-design.md` flow and repo-processor design:
    - github-gate fetches all configured entities in one pass (bounded by github-gate limits)
    - repo-processor now consumes full extraction markdown and enforces prompt-size budget
    - added default repo budget ratio (`0.65`) and weighted optional-category allocation
    - repo-processor output markdown keeps only the 8 core sections (no Processor Stats/Warn sections)
  - Phase 2 prompt now requires:
    - entrypoint seeding then breadth-first traversal for code retrieval
    - UTF-8 byte-based budgeting with token estimates
    - best-effort partial-failure behavior with warning reporting
    - strict markdown output format for CLI payload export
  - Added `config/non-informative-files.json` with default file/dir/pattern exclusions
  - Live smoke test decision:
    - v1: run as part of normal `pytest` flow (no env-var gate)
    - v2 hardening: consider optional `RUN_LIVE_GITHUB_SMOKE=1` gate for CI stability
  - Prompt contract and output validation plan
  - Logging/observability format and security notes
  - Reliability constraints and testing strategy
  - Explicit list of open decisions

## Current Agreed Direction
- Keep v1 scope small: one endpoint (`POST /summarize`), public repos only.
- Use GitHub API access through adapter (`github-gate`) without cloning repos.
- Implement `github-gate` using `ghapi`, while keeping retries/error mapping in adapter-owned policy.
- Use one-pass github-gate extraction (bounded by github-gate limits), then repo-processor prompt-fit trimming based on model context budget.
- Keep commit titles out of v1 retrieval for now.
- In `github-gate`, include explicit extraction helpers for documentation/tests/code with configurable limits.
- Use structured JSON output contract from LLM via `llm-gate`.
- Keep per-request sequential debug logs in one file.

## Open Decisions (Need User Input)
1. Whether optional GitHub token support should be in v1 or v1.1.
2. Whether API should expose any confidence/uncertainty metadata.

## Suggested Next Discussion Step
- Finalize the two open decisions above, then derive:
  - final config schema (`runtime` + ignore rules),
  - concrete prompt template,
  - exception hierarchy and status-code mapping table with exact messages.

## Files To Read First On Resume
1. `docs/project-description.md`
2. `docs/architecture-and-design.md`
3. `RESUME-CODEX.md`
4. `app/llm_gate/prompt.md`
5. `impl-process/phase2-github-gate.md`
6. `impl-process/phase2-github-gate-1.1.md`
7. `impl-process/v2/phase2-github-gate-v2.md`
8. `config/non-informative-files.json`
9. `impl-process/phase3-repo-processor.md`
10. `impl-process/phase4-llm-gate.md`
11. `impl-process/v2/phase3-repo-processor-v2.md`

