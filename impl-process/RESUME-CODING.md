# RESUME-CODING

## Session Snapshot
- Date: 2026-02-21
- Project: GitHub repository summarizer API
- Active phase: Phase 4 (`llm-gate` core + CLI)
- Status: Phase 4 scope implemented

## Phase 1 Scope Implemented
- Added FastAPI skeleton service exposing `POST /summarize`.
- Request body requires `{"github_url": "..."}` via Pydantic model.
- Endpoint currently returns:
  - HTTP `501`
  - `{"status":"error","message":"Not implemented"}`
- Added runtime dependency file `requirements.txt` with `fastapi[standard]`.
- Rewrote `README.md` with clean-machine setup/run/test instructions.

## Files Touched In Phase 1
- `app/main.py` (new)
- `requirements.txt` (new)
- `README.md` (updated)
- `impl-process/RESUME-CODING.md` (this file; moved from repo root and updated)
- `tests/smoke/conftest.py` (new)
- `tests/smoke/test_service_smoke.py` (new)

## Phase 2 Scope Implemented
- Added `github-gate` package with explicit DTOs, adapter methods, selection helpers, and typed exceptions.
- Implemented required methods:
  - `parse_repo_url`
  - `verify_repo_access`
  - `get_repo_metadata`
  - `get_languages`
  - `get_tree`
  - `get_readme`
  - `get_file_content`
  - `get_documentation`
  - `get_tests`
  - `get_code`
- Implemented adapter-owned retry/timeout policy wrapper:
  - attempt timeout cap `10s`
  - retries on retryable statuses/network failures
  - non-retryable failure mapping to typed exceptions
- Implemented ignore-rules consumption from `config/non-informative-files.json`.
- Added runtime limits file `config/runtime.json` as the primary default location for `github-gate` byte/link limits.
- Implemented Phase 2.1 addendum:
  - added `get_build_and_package_data(tree, limits) -> list[FileContent]`
  - added `build_package` CLI entity and `# Build and Package Data` section
  - added `max_build_package_total_bytes` limit and runtime config key
  - added `RepoSnapshot.build_and_package_files`
- Implemented docs-source requirement change:
  - removed README link crawling for documentation extraction
  - `get_documentation` now uses `RepoMetadata.homepage` (About link) as single external-doc source
  - no recursive page-link following
  - keeps docs folder extraction (`docs/`, `documentation/`) within byte limits
  - keeps best-effort behavior with warning-only homepage fetch failures
- Implemented deterministic extraction ordering:
  - docs/tests: breadth-first then lexicographic
  - code: entrypoint seeding first, then BFS remainder
- Added manual CLI:
  - `python -m app.github_gate.cli --github-url <url> --entities <list|all> --output <path.md>`
  - emits strict markdown sections in required order, with byte/token stats and warnings.
- Updated runtime dependencies with `ghapi`.
- Kept `/summarize` Phase-1 stub behavior unchanged.

## Phase 3 Scope Implemented
- Added `repo-processor` module with required interfaces:
  - `process_markdown(markdown_text, config=None) -> ProcessedRepoMarkdown`
  - `parse_extraction_markdown(markdown_text) -> ExtractedRepoMarkdown`
  - `render_processed_markdown(data) -> str`
- Added `ContextWindowLimitBookkeeper` utility with required conversion/budget methods.
- Implemented runtime config support for:
  - `llm_gate.model_context_window_tokens` (mandatory for processor budget)
  - `repo_processor` ratio/token-estimate/category-weights defaults/overrides
- Implemented mandatory algorithm:
  - baseline-first inclusion (`metadata`, `languages`, `tree`, `readme`)
  - README-first baseline truncation, then tree-end truncation if needed
  - weighted optional allocation + proportional redistribution (`documentation`, `build/package`, `tests`, `code`)
  - deterministic block-aware truncation using `## File:` blocks for optional categories
- Added `repo-processor` CLI:
  - `python -m app.repo_processor.cli --input <full.md> [--output <path>]`
  - supports required override flags
  - default output path: `[input-stem]-for-llm.md`
- Updated `config/runtime.json` with `llm_gate` and `repo_processor` sections.

## Phase 4 Scope Implemented
- Added `llm-gate` module with required interfaces:
  - `summarize(markdown_text, options=None) -> SummaryResult` (public wrapper + class method)
  - `parse_repo_digest_markdown(markdown_text) -> RepoDigest`
  - `render_user_prompt(digest, template_path=...) -> str`
- Added typed exceptions:
  - `LlmConfigError`
  - `LlmDigestParseError`
  - `LlmRateLimitError`
  - `LlmTimeoutError`
  - `LlmUpstreamError`
  - `LlmOutputValidationError`
- Implemented prompt contract loading from `app/llm_gate/prompt.md`:
  - system prompt extraction
  - json schema extraction
  - user template rendering from parsed digest
- Implemented Nebius call adapter:
  - OpenAI-compatible `/chat/completions` payload
  - `response_format` json schema mode
  - adapter-owned timeout/retry policy with retryable/non-retryable mapping
- Implemented strict output normalization/validation to exact response keys:
  - `summary`, `technologies`, `structure`
  - trim + technology dedupe + max lengths/items
- Added CLI:
  - `python -m app.llm_gate.cli --input <digest.md> --output <result.json>`
  - supports `--model-id`, `--temperature`, `--max-output-tokens`, `--timeout-seconds`, `--dry-run`
- Updated `config/runtime.json` `llm_gate` settings with defaults from phase spec.
- Added explicit `httpx` dependency to `requirements.txt`.

## Files Touched In Phase 2
- `app/__init__.py` (new)
- `app/github_gate/__init__.py` (new)
- `app/github_gate/models.py` (new)
- `app/github_gate/errors.py` (new)
- `app/github_gate/selectors.py` (new)
- `app/github_gate/client.py` (new)
- `app/github_gate/cli.py` (new)
- `app/github_gate/selectors.py` (updated with build/package matcher)
- `app/llm_gate/prompt.md` (moved from `llm-gate/prompt.md`)
- `app/llm_gate/__init__.py` (new)
- `config/runtime.json` (new)
- `app/github_gate/models.py` (updated: removed `max_readme_doc_links`)
- `config/runtime.json` (updated: removed `max_readme_doc_links`)
- `tests/smoke/test_github_gate_cli_live_smoke.py` (new live CLI smoke test)
- `requirements.txt` (updated with `ghapi`)
- `tests/smoke/conftest.py` (updated readiness/failure handling robustness)
- `impl-process/RESUME-CODING.md` (updated)
- `app/repo_processor/__init__.py` (new)
- `app/repo_processor/errors.py` (new)
- `app/repo_processor/models.py` (new)
- `app/repo_processor/bookkeeper.py` (new)
- `app/repo_processor/parser.py` (new)
- `app/repo_processor/processor.py` (new)
- `app/repo_processor/cli.py` (new)
- `config/runtime.json` (updated with `llm_gate` and `repo_processor`)
- `app/llm_gate/__init__.py` (updated exports)
- `app/llm_gate/errors.py` (new)
- `app/llm_gate/models.py` (new)
- `app/llm_gate/markdown_parser.py` (new)
- `app/llm_gate/prompt_loader.py` (new)
- `app/llm_gate/client.py` (new)
- `app/llm_gate/cli.py` (new)
- `requirements.txt` (updated with `httpx`)
- `config/runtime.json` (updated with full llm-gate runtime defaults)

## Canonical Spec Paths
- `docs/project-description.md`
- `docs/architecture-and-design.md`
- `docs/testcases.md`

## Runbook (Resume Quickly)
1. Create venv:
   - `python -m venv .venv`
2. Activate venv (PowerShell):
   - `.\.venv\Scripts\Activate.ps1`
3. Install deps:
   - `pip install -r requirements.txt`
4. Start server:
   - `uvicorn app.main:app --host 0.0.0.0 --port 8000`
5. Smoke test:
   - `curl.exe --% -X POST http://localhost:8000/summarize -H "Content-Type: application/json" --data-raw "{\"github_url\":\"https://github.com/psf/requests\"}"`

Expected current response:
- `{"status":"error","message":"Not implemented"}`

## Open Decisions (Still Tracked)
1. Exact Nebius model id for v1.
2. Whether optional GitHub token support stays in v1.1 or moves into v1.
3. Whether to expose confidence/uncertainty metadata in API response.

## Next Likely Phase
- Integrate `github-gate` + `repo-processor` + `llm-gate` into service `/summarize` orchestration.
- Add unit tests for llm-gate parser/prompt rendering/output validation.
- Add integration tests for non-happy-path HTTP error mapping across modules.

## Continuation Log
- 2026-02-21: Initialized resume file and documented pre-implementation state.
- 2026-02-21: Implemented Phase 1 skeleton service and moved resume file to `impl-process/`.
- 2026-02-21: Added smoke tests that start uvicorn on `127.0.0.1` + free port, wait for `/openapi.json`, and assert `POST /summarize` returns the Phase 1 501 contract for `{\"github_url\": \"\"}`.
- 2026-02-21: Local `pytest` run skipped smoke test because `uvicorn` is not installed in the currently active Python runtime.
- 2026-02-21: Implemented Phase 2 `github-gate` core adapter, selectors, typed errors, DTOs, and CLI markdown exporter.
- 2026-02-21: Added `config/runtime.json` defaults for `github-gate` extraction limits.
- 2026-02-22: Implemented `phase2-github-gate-1.1` addendum for build/package extraction and CLI/entity/schema updates.
- 2026-02-22: Moved `llm-gate` under `app/` to align module hierarchy (`app/llm_gate`).
- 2026-02-22: Updated documentation extraction to About/homepage-source model and removed README-link crawling + related limits/CLI args.
- 2026-02-22: Added live subprocess CLI smoke test for `github-gate` covering section order/content and extraction stats assertions.
- 2026-02-21: Manual syntax checks passed for all new Phase 2 modules.
- 2026-02-21: Local smoke test remains unstable in this machine context due Python `3.9` runtime incompatibilities with the project’s FastAPI/Pydantic setup (project target is Python `3.10+`).
- 2026-02-22: Implemented Phase 3 `repo-processor` package, CLI, runtime config wiring, and context-window budget utility.
- 2026-02-22: Implemented Phase 4 `llm-gate` package, runtime config defaults, and CLI (dry-run + live-call paths).
- 2026-02-22: Patched llm-gate timeout/retry/output-validation/parser issues from review feedback:
  - enforce attempt-cap without blocking on worker completion,
  - strict output type checks (no `str(...)` coercion),
  - malformed digest markdown now raises `LlmDigestParseError`,
  - retryable upstream 502/503/504 now map to `LlmUpstreamError` (429 remains `LlmRateLimitError`).

## Manual Validation Results (Phase 2)
- ✅ `app/github_gate/*` modules parse successfully (`ast.parse` syntax check).
- ✅ Smoke test passes in Python 3.11 venv: `python -m pytest tests/smoke/test_service_smoke.py -q`
- ✅ Live CLI smoke test passes: `python -m pytest tests/smoke/test_github_gate_cli_live_smoke.py -q`
- ⚠️ CLI runtime was not executed end-to-end locally because `ghapi` is now declared in `requirements.txt` but not installed in the active local venv at validation time.
- ✅ `github-gate` default limits now live in `config/runtime.json` (code retains safe fallback defaults if config is missing).
- ⚠️ Existing smoke test currently fails in this machine context because OpenAPI generation in local Python `3.9` returns `500`; target runtime remains Python `3.10+` per project requirements.

## Manual Validation Results (Phase 3)
- ✅ New repo-processor modules parse successfully (`ast.parse` syntax check).
- ✅ `python -m app.repo_processor.cli --input outputs/psf-requests.md` succeeded.
- ✅ Output file written: `outputs/psf-requests-for-llm.md`.
- ✅ Processor stats reported expected byte/token reductions (`input_bytes=495207`, `output_bytes=67783`, `max_repo_data_bytes=85196`).
- ✅ Existing Phase-1 API smoke test still passes: `python -m pytest tests/smoke/test_service_smoke.py -q`.

## Manual Validation Results (Phase 4)
- ✅ New llm-gate modules parse successfully (`ast.parse` syntax check).
- ✅ Dry-run CLI works and renders prompt payload from digest markdown:
  - `python -m app.llm_gate.cli --input outputs/psf-requests-for-llm.md --output outputs/llm-result.json --dry-run`
- ✅ Missing API key path returns clear typed config error:
  - `llm_config_error: NEBIUS_API_KEY is required.`
- ✅ Existing service smoke remains green after llm-gate changes:
  - `python -m pytest tests/smoke/test_service_smoke.py -q`.

## Known Limitations
- No automated test suite for `github-gate` yet (explicitly deferred by scope to later phase).
- `ghapi` operations are implemented but require dependency installation and network access for live repo validation.
