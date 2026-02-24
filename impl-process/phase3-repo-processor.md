# Phase 3 - Implement `repo-processor` Core + CLI (Kickoff Prompt)

Implement the `repo-processor` module according to `docs/architecture-and-design.md`.
This phase converts full repo extraction markdown into prompt-ready markdown constrained by model context limits.

## Objective
Build a production-ready v1 `repo-processor` that:
- reads full markdown output from `github-gate`
- computes max repo-data budget for prompt from model context window
- applies deterministic selection/truncation rules
- outputs smaller (or unchanged) markdown for LLM input
- provides a CLI for manual processing
- introduces a reusable context-window budget bookkeeper utility

## Scope (In)
1. Add `repo-processor` implementation and typed exceptions.
2. Add `ContextWindowLimitBookkeeper` utility for shared byte/token budget calculations.
3. Add runtime config support for processor budget ratios and category weights.
4. Add CLI for processing markdown input and writing markdown output.
5. Update `requirements.txt` if new runtime deps are required.
6. Update `impl-process/RESUME-CODING.md` after implementation.

## Scope (Out)
- Do not modify `github-gate` retrieval behavior in this phase.
- Do not integrate `repo-processor` into `/summarize` endpoint yet.
- Do not implement `llm-gate` in this phase.
- Do not add automated test expansion in this phase (moved to v2).

## Required Interfaces (Must Exist)
Public API (single required entrypoint):
- `process_markdown(markdown_text: str, config: RepoProcessorConfig | None = None) -> ProcessedRepoMarkdown`

Helper contracts (recommended to keep explicit for testability/reuse; may be private methods if preferred):
- `parse_extraction_markdown(markdown_text: str) -> ExtractedRepoMarkdown`
- `render_processed_markdown(data: ProcessedRepoMarkdown) -> str`

Bookkeeper:
- `ContextWindowLimitBookkeeper(model_context_window_tokens: int, bytes_per_token_estimate: float = 4.0)`
- `tokens_to_bytes(tokens: int) -> int`
- `bytes_to_tokens(num_bytes: int) -> int`
- `max_repo_data_bytes(max_repo_data_ratio_in_prompt: float) -> int`
- `remaining_bytes(current_repo_data_bytes: int, max_repo_data_ratio_in_prompt: float) -> int`

## DTOs / Data Contracts
Define explicit dataclasses or pydantic models (your choice):
- `ExtractedRepoMarkdown` with section bodies:
  - `repository_metadata`
  - `language_stats`
  - `directory_tree`
  - `readme`
  - `documentation`
  - `build_and_package_data`
  - `tests`
  - `code`
  - optional passthrough sections: `extraction_stats`, `warnings`
- `ProcessedRepoMarkdown`:
  - same core section fields (post-truncation)
  - processor stats (for logs/debugging; not emitted as markdown sections):
    - `input_total_utf8_bytes`
    - `output_total_utf8_bytes`
    - `max_repo_data_size_for_prompt_bytes`
    - `estimated_input_tokens`
    - `estimated_output_tokens`
    - per-category byte usage
    - truncation notes
- `RepoProcessorConfig`

## Runtime Config Requirements
Add `repo_processor` section in `config/runtime.json`:
- `max_repo_data_ratio_in_prompt` (default `0.65`)
- `bytes_per_token_estimate` (default `4`)
- `documentation_weight` (default `0.40`)
- `tests_weight` (default `0.20`)
- `build_package_weight` (default `0.20`)
- `code_weight` (default `0.20`)

Required model config used by processor:
- `llm_gate.model_context_window_tokens` (mandatory input for budget computation)

Validation:
- weights must be non-negative
- at least one weight must be > 0
- `max_repo_data_ratio_in_prompt` must be in `(0, 1)`
- raise typed config error on invalid values

## Budget Computation Rules
- `max_repo_data_size_for_prompt_bytes = floor(model_context_window_tokens * max_repo_data_ratio_in_prompt * bytes_per_token_estimate)`
- byte accounting always uses UTF-8 encoded length
- token estimate uses conservative conversion:
  - `estimated_tokens = ceil(utf8_bytes / bytes_per_token_estimate)`

## Processing Algorithm (Mandatory)
Given full extracted markdown:

1. If full markdown fits `max_repo_data_size_for_prompt_bytes`, return unchanged markdown.
2. Mandatory baseline categories are always prioritized:
   - `Repository Metadata`
   - `Language Stats`
   - `Directory Tree`
   - `README`
3. If mandatory baseline exceeds budget:
   - truncate README first to fit remaining budget.
   - if still over budget after README is fully removed/truncated, truncate directory tree deterministically from end.
4. Compute remaining byte budget after mandatory baseline.
5. Weighted allocation over optional categories:
   - Documentation
   - Build and Package Data
   - Tests
   - Code
6. Allocation method:
   - initial shares based on configured weights
   - if a category content is smaller than its share, include fully
   - redistribute leftover bytes among still-unsatisfied categories proportionally to their relative weights
   - repeat until no redistributable bytes remain or all categories satisfied
7. For categories larger than allocated bytes:
   - truncate to allocation limit.
8. Preserve section order and deterministic block order in output.

## Truncation Semantics
- For Documentation/Build/Tests/Code categories, treat each `## File: ...` block as a unit.
- Include full blocks while budget allows.
- If next block would exceed budget:
  - include block header lines:
    - `## File: ...`
    - `- Source: ...`
    - `- UTF8 Bytes: ...`
    - `- Estimated Tokens: ...`
  - then include truncated fenced content to fill remaining bytes.
- Truncation is from tail; keep beginning content.
- Maintain valid markdown fences and section headers.

## Output Markdown Contract
Output markdown must include sections in this exact order:
1. `# Repository Metadata`
2. `# Language Stats`
3. `# Directory Tree`
4. `# README`
5. `# Documentation`
6. `# Build and Package Data`
7. `# Tests`
8. `# Code`

For section values:
- If section absent in input, write `Not found`.
- If section present but dropped by budget, write `Truncated to zero`.
- Otherwise write processed content.

## Typed Exceptions
Create explicit exceptions:
- `RepoProcessorConfigError`
- `RepoProcessorParseError`
- `RepoProcessorBudgetError`
- `RepoProcessorOutputError`

Each exception should include:
- machine-readable code
- human-readable message
- optional context payload

## CLI Requirement
Add CLI entry point:
- `python -m app.repo_processor.cli --input <full.md> [--output <path>]`

CLI behavior:
- input: markdown from `github-gate` extraction
- default output path:
  - `[input-file-stem]-for-llm.md` in same directory
- optional flags:
  - `--max-repo-data-ratio-in-prompt`
  - `--bytes-per-token-estimate`
  - `--documentation-weight`
  - `--tests-weight`
  - `--build-package-weight`
  - `--code-weight`
  - `--model-context-window-tokens` (override for local experiments)
- exit code `0` on success, non-zero on fatal errors

## Suggested File Layout
- `app/repo_processor/__init__.py`
- `app/repo_processor/models.py`
- `app/repo_processor/errors.py`
- `app/repo_processor/bookkeeper.py`
- `app/repo_processor/parser.py`
- `app/repo_processor/processor.py`
- `app/repo_processor/cli.py`

## Manual Validation Checklist (Phase 3)
1. Process a small markdown that already fits budget; confirm unchanged output.
2. Process a large markdown; confirm deterministic truncation and section order.
3. Confirm README truncates first when baseline exceeds limit.
4. Confirm leftover redistribution works when one category is smaller than its share.
5. Confirm output filename default is `[input]-for-llm.md`.
6. Confirm processor reports bytes/tokens and truncation notes in returned metadata or logs.

## Acceptance Criteria
- `repo-processor` methods exist and conform to required interfaces.
- Budget is computed from `llm_gate.model_context_window_tokens` and processor config.
- Default ratio is `0.65` and is configurable.
- Mandatory baseline + weighted optional allocation algorithm is implemented as specified.
- Deterministic truncation behavior is implemented and stable.
- CLI input/output contract is implemented.
- `/summarize` endpoint behavior remains unchanged in this phase.
- `impl-process/RESUME-CODING.md` is updated with implementation summary and manual validation.

## Implementation Notes
- Keep logs structured and avoid secrets.
- Keep markdown parsing/truncation deterministic and simple.
- Prefer explicit section parsing over heuristic regex-only parsing.
- Keep this module reusable by both service orchestration and local CLI workflows.
