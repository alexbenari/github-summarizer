# Phase 4 - Implement `llm-gate` Core + CLI (Kickoff Prompt)

Implement the `llm-gate` module according to `docs/architecture-and-design.md`.
This phase focuses on model invocation, strict output validation, and a manual CLI runner.

## Objective
Build a production-ready v1 `llm-gate` adapter that:
- builds deterministic model input from processed repository markdown
- invokes Nebius with structured JSON schema output constraints
- validates and normalizes model output to API response shape
- applies adapter-owned timeout/retry/error mapping policy
- provides a CLI to run summarization from a digest markdown file

Note: input markdown for this phase is the processed output from `repo-processor`, not raw `github-gate` output.

## Scope (In)
1. Add `llm-gate` implementation, internal DTOs, and typed exceptions.
2. Add runtime config support for model and llm-gate operational defaults.
3. Reuse prompt contract from `app/llm_gate/prompt.md` as source of truth.
4. Add CLI command for manual end-to-end LLM invocation from digest markdown input.
5. Update `requirements.txt` for llm-gate dependencies.
6. Update `impl-process/RESUME-CODING.md` after implementation.

## Scope (Out)
- Do not integrate `llm-gate` into `/summarize` endpoint in this phase (endpoint behavior remains unchanged).
- Do not add private repository support.
- Do not add automated test expansion in this phase (moved to v2).
- Do not implement `repo-processor` in this phase.

## Required Interfaces (Must Exist)
Public API (single required entrypoint):
- `summarize(markdown_text: str, options: LlmRequestOptions | None = None) -> SummaryResult`

Helper contracts (recommended explicit boundaries; may be private methods if preferred):
- `parse_repo_digest_markdown(markdown_text: str) -> RepoDigest`
- `render_user_prompt(digest: RepoDigest, template_path: str = "app/llm_gate/prompt.md") -> str`

## DTOs / Data Contracts
Define explicit dataclasses or pydantic models (your choice) for:
- `RepoDigest`:
  - `repository_metadata: str`
  - `language_stats: str`
  - `tree_summary: str`
  - `readme_text: str`
  - `documentation_text: str`
  - `build_package_text: str`
  - `test_snippets: str`
  - `code_snippets: str`
- `SummaryResult(summary: str, technologies: list[str], structure: str)`
- `LlmGateConfig(...)`
- `LlmRequestOptions(...)` (optional per-call overrides)

## Markdown Input Contract (for CLI + parser)
The parser must support markdown produced by `repo-processor` and map sections as:
- `# Repository Metadata` -> `repository_metadata`
- `# Language Stats` -> `language_stats`
- `# Directory Tree` -> `tree_summary`
- `# README` -> `readme_text`
- `# Documentation` -> `documentation_text`
- `# Build and Package Data` -> `build_package_text`
- `# Tests` -> `test_snippets`
- `# Code` -> `code_snippets`

Parsing rules:
- Missing section -> empty string for that field.
- Exact section text `Not requested` or `Not found` -> empty string for that field.
- Preserve section body text as-is otherwise.
- Ignore unknown extra sections if present.

## Prompt Contract Requirements
- Use `app/llm_gate/prompt.md` as prompt source of truth.
- Preserve system instructions from that file.
- Render user prompt placeholders from `RepoDigest` fields.
- Model call must request structured output using JSON schema response format.

## Model Invocation Requirements
- Use Nebius API with API key from environment:
  - required: `NEBIUS_API_KEY`
  - optional override: `NEBIUS_MODEL_ID`
  - optional override: `NEBIUS_BASE_URL`
- Read model settings from `config/runtime.json` `llm_gate` section.
- Mandatory runtime config entries:
  - `model_id`
  - `model_context_window_tokens`
- If mandatory config entries are missing, raise `LlmConfigError`.
- Default model id in checked-in config:
  - `Qwen/Qwen3-30B-A3B-Thinking-2507`
- Default model context window in checked-in config:
  - `262000` tokens
- Runtime config values can be overridden by env/CLI.
- Deterministic defaults:
  - `temperature`: `0.1`
  - `top_p`: `1.0`
  - `max_output_tokens`: `2000`
- No streaming in v1.

## Timeout/Retry Policy (adapter-owned)
Default llm-gate policy:
- connect timeout: `2s`
- read timeout: `45s`
- total attempt cap: `50s`
- max retries: `2` (3 attempts total)
- backoff: `0.5s`, then `1.0s` (+ small jitter optional)

Retryable conditions:
- network timeout/errors
- upstream `429`, `502`, `503`, `504`

Non-retryable conditions:
- `400`, `401`, `403`, `404`
- local output schema validation failures
- malformed input digest parse errors

## Output Validation and Normalization
The returned result must always conform to:
```json
{
  "summary": "string",
  "technologies": ["string"],
  "structure": "string"
}
```

Validation rules:
- required keys: `summary`, `technologies`, `structure`
- `summary` and `structure` are non-empty strings
- `technologies` is array of non-empty strings, max `20` items, max `80` chars/item
- no additional top-level keys

Normalization rules:
- trim surrounding whitespace on all strings
- dedupe `technologies` case-insensitively while preserving first-seen order
- remove empty technology items after trimming
- if output still invalid after normalization, raise typed validation error

## Typed Exceptions
Create explicit exceptions such as:
- `LlmConfigError`
- `LlmDigestParseError`
- `LlmRateLimitError`
- `LlmTimeoutError`
- `LlmUpstreamError`
- `LlmOutputValidationError`

Each exception should carry:
- machine-readable code
- human-readable message
- optional upstream status/context

## CLI Requirement (Manual Validation Tool)
Add a CLI entry point to run llm-gate against the real LLM API (except `--dry-run` mode).

Suggested command:
- `python -m app.llm_gate.cli --input <digest.md> --output <result.json>`

CLI arguments:
- `--input` (required): path to digest markdown (typically from repo-processor output)
- `--output` (required): output JSON path
- `--model-id` (optional): overrides runtime/env model id
- `--temperature` (optional): overrides runtime temperature
- `--max-output-tokens` (optional): overrides runtime max output tokens
- `--timeout-seconds` (optional): overrides attempt timeout cap
- `--dry-run` (optional): render and print prompt payload, do not call model

CLI output behavior:
- On success, write exact JSON object with keys:
  - `summary`
  - `technologies`
  - `structure`
- Exit code `0` on success.
- Non-zero exit on fatal failures, with clear stderr message.

## Runtime Config Updates
Extend `config/runtime.json` with `llm_gate` section entries:
- `model_id` (mandatory, default `Qwen/Qwen3-30B-A3B-Thinking-2507`)
- `model_context_window_tokens` (mandatory, default `262000`)
- `temperature`
- `top_p`
- `max_output_tokens` (default `2000`)
- `connect_timeout_seconds`
- `read_timeout_seconds`
- `attempt_timeout_seconds`
- `max_retries`
- `retry_backoff_seconds` (array; default `[0.5, 1.0]`)

## Suggested File Layout
- `app/llm_gate/__init__.py`
- `app/llm_gate/models.py`
- `app/llm_gate/errors.py`
- `app/llm_gate/client.py`
- `app/llm_gate/prompt_loader.py` (optional)
- `app/llm_gate/markdown_parser.py` (optional)
- `app/llm_gate/cli.py`
- `app/llm_gate/prompt.md`

## Manual Validation Checklist (Phase 4)
1. Run CLI in dry-run mode and confirm prompt rendering with no API call.
2. Run CLI with valid `NEBIUS_API_KEY` and digest markdown; confirm JSON file output.
3. Confirm output contains only `summary`, `technologies`, `structure`.
4. Confirm malformed markdown input produces clear parse/config error.
5. Confirm missing API key produces clear configuration error.
6. Confirm retry behavior on transient failures is visible in logs/messages.

## Acceptance Criteria
- `llm-gate` public `summarize(...)` method exists and conforms to required interface.
- parsing/prompt-rendering helper boundaries are implemented (public or private).
- Prompt is rendered from `app/llm_gate/prompt.md`.
- JSON schema-constrained output is requested from model API.
- Response validation + normalization rules are implemented exactly.
- Timeout/retry policy is implemented and adapter-owned.
- CLI works for both dry-run and live call paths.
- `requirements.txt` includes needed llm-gate runtime dependencies.
- `/summarize` endpoint behavior remains unchanged in this phase.
- `impl-process/RESUME-CODING.md` is updated with:
  - what was implemented
  - files touched
  - manual validation results
  - known limitations

## Implementation Notes
- Keep logs structured and avoid logging secrets.
- Keep external API specifics inside adapter boundary.
- Keep code straightforward and deterministic over cleverness.
- Do not log `NEBIUS_API_KEY` or raw authorization headers.
- Automated test expansion is deferred to phase-4 v2.
