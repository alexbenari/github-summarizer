# Phase 5 - Integrate End-to-End `/summarize` Service (Kickoff Prompt)

Implement the final integration phase for the FastAPI service endpoint according to:
- `docs/architecture-and-design.md` (especially section `### 4) End-to-End Flow`)
- existing module implementations in:
  - `app/github_gate`
  - `app/repo_processor`
  - `app/llm_gate`

This phase wires existing components into a working `POST /summarize` endpoint.

## Objective
Replace the current stub endpoint with a working orchestration flow:
1. validate request and config
2. fetch full repository extraction (`all` entity set)
3. process extraction markdown for prompt budget
4. summarize via llm-gate
5. return contract-compliant API response

## Scope (In)
1. Implement endpoint orchestration in `app/main.py`.
2. Add startup config validation (`ConfigValidator`) and fail-fast behavior.
3. Add explicit error-to-HTTP mapping for all known typed exceptions.
4. Add request-level progress logging to console and per-request debug log file.
5. Ensure service path fetches the same data entities as github-gate CLI `--entities all`.
6. Add one API-level integration test with monkeypatched gates and call-order assertions.
7. Update `README.md` usage examples if endpoint behavior changes.
8. Update `impl-process/RESUME-CODING.md` after implementation.

## Scope (Out)
- No API contract expansion beyond current request/response shape.
- No additional crawler depth or GitHub domain restriction changes.
- No v2 hardening tasks (full retry observability tests, chaos tests, etc.).

## Agreed Behavioral Decisions (Must Implement)
1. **Best-effort data extraction from github-gate optional selectors**:
   - Continue on partial failures for `documentation`, `build_package`, `tests`, `code`.
   - Fail request only if core repository access/identity fails.
2. **Fetch all repo entities** exactly as CLI `all` semantic set:
   - `metadata`, `languages`, `tree`, `readme`, `documentation`, `build_package`, `tests`, `code`.
3. **Repo-processor overflow in this milestone**:
   - If `RepoProcessorBudgetError` occurs, do not fail request.
   - Log warning and continue using full extraction markdown (overflow allowed for v1 milestone).
4. **Startup config validation**:
   - Add `ConfigValidator` and run it at app startup (fail fast if invalid).

## Required Interfaces (Must Exist)

### `ConfigValidator`
Create `app/config_validator.py` with explicit API:
- `class ConfigValidator`
- `def validate_startup(self) -> None`

Validation responsibilities:
- Load and validate `LlmGateConfig` (mandatory model id + context window + numeric constraints).
- Load and validate `RepoProcessorConfig`.
- Load `GithubGateLimits` and validate all limits are positive integers.
- Verify `NEBIUS_API_KEY` is present and non-empty at startup.
- Raise typed/clear exception on failure with actionable message.

### Integration service boundary
In `app/main.py`, add a dedicated orchestration function:
- `summarize_service(github_url: str) -> dict[str, object]`

The route handler should be thin:
- parse request
- call orchestration
- map exceptions to HTTP status
- return JSON payload

### Shared markdown rendering for github-gate output
Service integration must produce markdown compatible with `repo-processor` input contract.

Requirement:
- Extract markdown rendering logic currently embedded in `app/github_gate/cli.py` into a reusable module (example: `app/github_gate/markdown_renderer.py`), then reuse from both:
  - github-gate CLI
  - service integration path

Do **not** shell out to CLI from the service.

## End-to-End Flow (Implementation Contract)
For each request:
1. Generate request id.
2. Parse and normalize GitHub URL via `GithubGate.parse_repo_url`.
3. Verify access via `GithubGate.verify_repo_access`.
4. Fetch all entities in best-effort mode:
   - `get_repo_metadata`
   - `get_languages`
   - `get_tree`
   - `get_readme`
   - `get_documentation`
   - `get_build_and_package_data`
   - `get_tests`
   - `get_code`
5. Render full extraction markdown (same section order as github-gate CLI).
6. Process via `repo_processor.process_markdown`.
7. If processor succeeds, render processed markdown with `repo_processor.render_processed_markdown`.
8. If `RepoProcessorBudgetError`, log warning and use full extraction markdown as llm input for this milestone.
9. Call `LlmGate.summarize(markdown_text=...)`.
10. Return:
```json
{
  "summary": "...",
  "technologies": ["..."],
  "structure": "..."
}
```

## HTTP Error Mapping (Explicit)
Map known exceptions to status codes:

### Request/validation
- `InvalidGithubUrlError` -> `400`
- Request body/schema validation errors -> `400`
- Implementation note: FastAPI defaults validation failures to `422`; add an explicit `RequestValidationError` handler to enforce `400` per API contract.

### GitHub gate
- `RepositoryInaccessibleError` -> `404`
- `GithubRateLimitError` -> `429`
- `GithubTimeoutError` -> `504`
- `GithubResponseShapeError` -> `502`
- `GithubUpstreamError`:
  - upstream status `429` -> `429`
  - upstream status `504` -> `504`
  - otherwise -> `503`

### Repo processor
- `RepoProcessorParseError` -> `422`
- `RepoProcessorBudgetError` -> do not return error in this milestone; continue with overflow fallback
- `RepoProcessorConfigError` -> `500`
- `RepoProcessorOutputError` -> `500`

### LLM gate
- `LlmDigestParseError` -> `422`
- `LlmOutputValidationError` -> `502`
- `LlmRateLimitError` -> `429`
- `LlmTimeoutError` -> `504`
- `LlmUpstreamError`:
  - upstream status `429` -> `429`
  - upstream status `504` -> `504`
  - otherwise -> `503`
- `LlmConfigError` -> `500`

### Fallback
- Any other unhandled exception -> `500`

Error response body shape remains:
```json
{
  "status": "error",
  "message": "..."
}
```

## Logging Requirements

### Console progress logs (mandatory)
Use concise progress lines similar to llm-gate CLI style and include request id:
- `[service] request_start request_id=... repo_url=...`
- `[service] github_fetch_start request_id=...`
- `[service] github_fetch_done request_id=... bytes=... warnings=...`
- `[service] repo_process_start request_id=...`
- `[service] repo_process_done request_id=... output_bytes=...`
- `[service] llm_start request_id=... model=...`
- `[service] llm_done request_id=...`
- `[service] request_end request_id=... status=... latency_ms=...`

### Per-request debug log file (mandatory)
Write sequential log file under a local logs directory:
- filename: `requested-[repo]-[timestamp]-[request-id].log`
- include:
  1. request metadata
  2. github fetch outcomes + partial failure warnings
  3. processor stats / overflow fallback note
  4. llm call metadata (no secrets)
  5. final status and latency

Never log API keys or Authorization headers.

## Testing Requirements (Phase 5)
Add one API-level integration test in `tests/` that:
1. Monkeypatches github-gate, repo-processor, and llm-gate boundaries.
2. Calls `POST /summarize`.
3. Asserts:
   - status code `200`
   - response has exactly `summary`, `technologies`, `structure`
   - orchestration call order is correct
4. Add one error-path test for HTTP mapping (for example: `InvalidGithubUrlError -> 400`).

Keep this phase focused; broader integration matrix stays in v2.

## Acceptance Criteria
1. `POST /summarize` is fully wired and returns real LLM output for valid public repos.
2. Service path fetches the same entity set as github-gate CLI `all`.
3. Partial github optional-category failures are logged and tolerated.
4. Repo-processor overflow no longer fails request in this milestone.
5. Error mapping is explicit and matches this spec.
6. Startup fails fast with clear messages when config/env is invalid.
7. Console and per-request file logging are present and usable.
8. Added tests pass locally.
