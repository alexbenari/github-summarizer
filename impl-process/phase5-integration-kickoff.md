# Phase 5 - Integration Coding Agent Prompt

Implement Phase 5 according to `impl-process/phase5-integration.md`.

## Read First
1. `impl-process/phase5-integration.md`
2. `docs/architecture-and-design.md` (especially End-to-End Flow)
3. Current code in:
   - `app/main.py`
   - `app/github_gate`
   - `app/repo_processor`
   - `app/llm_gate`

## Goal
Wire all existing components into a working `POST /summarize` endpoint.

## Required Changes

1. Implement service orchestration in `app/main.py`
- Replace the current stub.
- Add `summarize_service(github_url: str)` as the orchestration boundary.
- Flow:
  - parse/normalize URL
  - verify repo access
  - fetch all repo entities (same as github-gate CLI `all`)
  - render full extraction markdown
  - run repo-processor
  - if `RepoProcessorBudgetError`, log warning and continue with full extraction markdown
  - call llm-gate summarize
  - return `{summary, technologies, structure}`

2. Add startup config validation
- Create `app/config_validator.py` with `ConfigValidator.validate_startup()`.
- Validate:
  - `LlmGateConfig`
  - `RepoProcessorConfig`
  - `GithubGateLimits` positive values
  - `NEBIUS_API_KEY` present and non-empty
- Fail fast on startup with clear error.

3. Add explicit HTTP error mapping
- Implement mapping exactly per `impl-process/phase5-integration.md`.
- Include explicit handler for FastAPI `RequestValidationError` to return `400` (not default `422`).

4. Reuse markdown renderer from github-gate
- Extract markdown rendering from `app/github_gate/cli.py` into reusable module (e.g. `app/github_gate/markdown_renderer.py`).
- Reuse from CLI and service path.
- Do not shell out to CLI.

5. Logging
- Add console progress logs with request id at the milestones defined in phase5 spec.
- Add per-request debug log file:
  - filename format: `requested-[repo]-[timestamp]-[request-id].log`
  - include required sections from phase5 spec
  - never log secrets.

6. Tests
- Add one API-level integration test with monkeypatched gates:
  - assert 200
  - assert exact response keys
  - assert orchestration call order
- Add one error-path test:
  - e.g. invalid URL maps to 400.

7. Docs/Process
- Update `README.md` only if run behavior changed.
- Update `impl-process/RESUME-CODING.md` with:
  - what changed
  - files touched
  - test commands + results
  - limitations/open issues

## Constraints
- Keep changes minimal and focused on Phase 5.
- Do not change API response contract.
- Do not add v2 scope work.
- Do not modify unrelated files.

## Completion Output
At the end, provide:
1. changed files list
2. short behavior summary
3. exact test commands run
4. test results
5. any open issues
