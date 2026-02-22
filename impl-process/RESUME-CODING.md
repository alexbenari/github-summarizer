# RESUME-CODING

## Session Snapshot
- Date: 2026-02-21
- Project: GitHub repository summarizer API
- Active phase: Phase 2 (`github-gate` core + CLI)
- Status: Phase 2 scope implemented (manual runtime validation partially blocked by local environment)

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
- Implemented deterministic extraction ordering:
  - docs/tests: breadth-first then lexicographic
  - code: entrypoint seeding first, then BFS remainder
- Added manual CLI:
  - `python -m app.github_gate.cli --github-url <url> --entities <list|all> --output <path.md>`
  - emits strict markdown sections in required order, with byte/token stats and warnings.
- Updated runtime dependencies with `ghapi`.
- Kept `/summarize` Phase-1 stub behavior unchanged.

## Files Touched In Phase 2
- `app/__init__.py` (new)
- `app/github_gate/__init__.py` (new)
- `app/github_gate/models.py` (new)
- `app/github_gate/errors.py` (new)
- `app/github_gate/selectors.py` (new)
- `app/github_gate/client.py` (new)
- `app/github_gate/cli.py` (new)
- `requirements.txt` (updated with `ghapi`)
- `tests/smoke/conftest.py` (updated readiness/failure handling robustness)
- `impl-process/RESUME-CODING.md` (updated)

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
- Integrate `github-gate` into `service` orchestration with HTTP error mapping.
- Add dedicated tests for URL parsing, retry/error mapping, and extraction ordering.
- Add integration test path for CLI output contract and warning handling.

## Continuation Log
- 2026-02-21: Initialized resume file and documented pre-implementation state.
- 2026-02-21: Implemented Phase 1 skeleton service and moved resume file to `impl-process/`.
- 2026-02-21: Added smoke tests that start uvicorn on `127.0.0.1` + free port, wait for `/openapi.json`, and assert `POST /summarize` returns the Phase 1 501 contract for `{\"github_url\": \"\"}`.
- 2026-02-21: Local `pytest` run skipped smoke test because `uvicorn` is not installed in the currently active Python runtime.
- 2026-02-21: Implemented Phase 2 `github-gate` core adapter, selectors, typed errors, DTOs, and CLI markdown exporter.
- 2026-02-21: Manual syntax checks passed for all new Phase 2 modules.
- 2026-02-21: Local smoke test remains unstable in this machine context due Python `3.9` runtime incompatibilities with the project’s FastAPI/Pydantic setup (project target is Python `3.10+`).

## Manual Validation Results (Phase 2)
- ✅ `app/github_gate/*` modules parse successfully (`ast.parse` syntax check).
- ⚠️ CLI runtime was not executed end-to-end locally because `ghapi` is now declared in `requirements.txt` but not installed in the active local venv at validation time.
- ⚠️ Existing smoke test currently fails in this machine context because OpenAPI generation in local Python `3.9` returns `500`; target runtime remains Python `3.10+` per project requirements.

## Known Limitations
- No automated test suite for `github-gate` yet (explicitly deferred by scope to later phase).
- `ghapi` operations are implemented but require dependency installation and network access for live repo validation.
