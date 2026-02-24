## Project Architecture and Design

### 1) Scope and Goals
Build a FastAPI service with one endpoint (`POST /summarize`) that accepts a public GitHub repository URL and returns:
- `summary`: what the project does
- `technologies`: main languages/frameworks/libraries
- `structure`: how the repository is organized

Primary design objective: maximize summary quality within LLM context-window limits.

### 2) Non-Goals (for v1)
- No support for private repositories
- No GitHub Enterprise hostnames
- No multi-repo comparison

### 3) API Contract

#### Request
- Method: `POST /summarize`
- Content-Type: `application/json`
- Body:
  - `github_url` (required, string)

Valid URL examples:
- `https://github.com/psf/requests`
- `https://github.com/psf/requests/`

Invalid for v1:
- Non-GitHub URLs
- URLs to user/org home pages without repo
- URLs with unsupported hosts

#### Success Response (HTTP 200)
```json
{
  "summary": "Requests is a popular Python HTTP client library...",
  "technologies": ["Python", "urllib3", "certifi"],
  "structure": "Main package under src/requests, tests under tests, docs under docs."
}
```

#### Error Response (non-200)
```json
{
  "status": "error",
  "message": "Description of what went wrong"
}
```

#### Error Mapping
- `400 Bad Request`: malformed body, invalid `github_url`, unsupported host/path
- `404 Not Found`: repository does not exist, is private, or is otherwise inaccessible in v1 unauthenticated mode
- `422 Unprocessable Entity`: repository is valid but content cannot be processed meaningfully
- `429 Too Many Requests`: GitHub API or upstream rate-limit reached
- `502 Bad Gateway`: invalid upstream response shape
- `503 Service Unavailable`: transient GitHub/LLM upstream outage
- `504 Gateway Timeout`: upstream timeout
- `500 Internal Server Error`: unexpected internal failures

### 4) End-to-End Flow
1. `service` validates request schema and normalizes the URL.
2. `github-gate` verifies repo identity and visibility.
3. `github-gate` fetches all configured repository entities in one pass (subject to github-gate byte limits) and emits a full extraction markdown payload.
4. `repo-processor` reads full extraction markdown and computes prompt repo-data budget from model context window.
5. `repo-processor` applies deterministic truncation/allocation rules to produce prompt-ready markdown within budget.
6. `llm-gate` sends structured prompt + processed repo markdown.
7. `llm-gate` validates/parses model output into response schema.
8. `service` returns normalized API response.

### 5) Module Design

#### A) `service` (FastAPI layer)
Responsibilities:
- Input validation and HTTP mapping
- Generate a unique request id for logging/tracing
- Orchestration across internal modules
- Error-to-status mapping

Internal interfaces:
- `summarize(github_url: str) -> SummaryResponse`

Suggested response model:
- `summary: str`
- `technologies: list[str]`
- `structure: str`

#### B) `github-gate` (GitHub adapter)
Responsibilities:
- Validate URL points to `github.com/{owner}/{repo}`
- Check public visibility
- Extract repository metadata and files without cloning the repo

Preferred upstream calls (GitHub REST API):
- repo metadata (`owner/repo`, default branch, visibility)
- languages stats
- recursive tree for default branch
- README content (if present)
- documentation:
  - if repository "About" section has a website link (`homepage` in repo metadata), fetch that single page content only
  - do not follow links from README for documentation crawling
  - do not follow links found on the fetched "About" page
  - inspect `docs/` or `documentation/` directories in the project tree and fetch contents within configured limits
- targeted file content fetches (only selected files)

Operational constraints:
- Use `ghapi` as the GitHub REST client in v1.
- Keep retry/backoff/error mapping logic inside `github-gate` (do not rely on library defaults for policy decisions).
- Map `ghapi` responses into internal DTOs (`RepoRef`, `RepoSnapshot`, `TreeEntry`, etc.) at the adapter boundary.
- Use unauthenticated mode in v1 (rate-limit aware)
- Strict per-call timeout defaults:
  - connect timeout: `2s`
  - read timeout: `8s`
  - total attempt timeout cap: `10s`
- Bounded retries for transient failures only:
  - retryable: network timeouts/errors, `429`, `502`, `503`, `504`
  - retryable `403` only when GitHub response indicates rate-limit behavior
  - non-retryable: `400`, `401`, `403` (non-rate-limit), `404`, schema/validation failures
  - max retries: `2` (up to 3 attempts total)
  - backoff: `0.5s`, then `1.0s` (with small jitter)
  - stop retries early if end-to-end request budget is almost exhausted

`github-gate` output type (`RepoSnapshot`):
- `owner`, `repo`, `default_branch`
- `description`, `topics`, `homepage`
- `languages` (actual language-by-bytes payload from GitHub)
- `tree_entries` (path, type, size, api_url, download_url when applicable)
- `readme` (optional; includes actual content text)
- `documentation` (optional; includes source URL and actual fetched text/content when present)

Explicit `github-gate` interface (v1):
- `parse_repo_url(github_url: str) -> RepoRef`
  - Accepts GitHub repository URLs and normalizes to `{owner, repo}`.
- `verify_repo_access(repo: RepoRef) -> None`
  - Confirms repository exists and is reachable in v1 unauthenticated mode.
- `get_repo_metadata(repo: RepoRef) -> RepoMetadata`
- `get_languages(repo: RepoRef) -> dict[str, int]`
- `get_tree(repo: RepoRef) -> list[TreeEntry]`
- `get_readme(repo: RepoRef) -> ReadmeData | None`
- `get_file_content(repo: RepoRef, path: str) -> FileContent`
- `get_documentation(tree: list[TreeEntry], metadata: RepoMetadata, limits: GithubGateLimits) -> DocumentationData | None`
  - If repository "About" section has a website link (`homepage`), fetch and extract that single page.
  - Do not follow links from README for documentation crawling.
  - Do not follow links on the fetched "About" page.
  - Also scan for `docs/` or `documentation/` directories and fetch contents within configured limits.
- `get_tests(tree: list[TreeEntry], limits: GithubGateLimits) -> list[FileContent]`
  - Finds likely test folders/files and returns test contents up to configured limits.
- `get_code(tree: list[TreeEntry], limits: GithubGateLimits) -> list[FileContent]`
  - Returns likely main code files up to configured limits.
  - Attempts to include entry points first (`main.*`, `app.*`, `server.*`, common CLI entry files), then high-value core files.

#### C) `repo-processor` (markdown budget manager)
Responsibilities:
- Parse full extraction markdown from `github-gate`
- Fit repository data into a strict prompt budget derived from model context
- Preserve high-signal sections and apply deterministic truncation rules

Input:
- full extraction markdown from `github-gate` CLI/adapter output
- runtime config (`repo_processor` + model context settings)

Output (`RepoDigest`):
- prompt-ready markdown with same core sections:
  - `# Repository Metadata`
  - `# Language Stats`
  - `# Directory Tree`
  - `# README`
  - `# Documentation`
  - `# Build and Package Data`
  - `# Tests`
  - `# Code`
- processor stats may be captured internally for logging/debugging, not as markdown sections

Budgeting model:
- compute `max_repo_data_size_for_prompt_bytes` as:
  - `floor(model_context_window_tokens * max_repo_data_ratio_in_prompt * bytes_per_token_estimate)`
- defaults:
  - `max_repo_data_ratio_in_prompt = 0.65`
  - `bytes_per_token_estimate = 4`
- `max_repo_data_ratio_in_prompt` and category weights are configurable

Selection/truncation algorithm (v1):
1. If full extraction markdown fits budget, pass it through unchanged.
2. Otherwise always include `metadata`, `languages`, `tree`, `readme` first.
3. If mandatory baseline exceeds budget:
  - truncate README first to fit.
  - if still over budget, truncate tree section deterministically from the end to fit.
4. For remaining budget, allocate capacity by weighted categories (default):
  - documentation `0.40`
  - tests `0.20`
  - build/package `0.20`
  - code `0.20`
5. If a category is smaller than its share, include it fully and redistribute leftover bytes to remaining categories proportionally to their relative weights.
6. If a category is larger than its current share, truncate it to fit its allocated bytes.
7. Preserve deterministic ordering from source markdown when trimming blocks.

Block-level truncation:
- treat each `## File: ...` block as atomic until final partial block is needed
- when partial truncation is required, trim from the end of content text, keep file header/source/byte metadata lines
- always keep valid markdown structure

#### D) `llm-gate` (model adapter)
Responsibilities:
- Build deterministic prompt payload
  - Use response_format parameter with {"type": "json_schema"} to get structured JSON output
- Invoke Nebius model endpoint
- Parse and validate structured output

Input:
- processed repo markdown from `repo-processor`
- prompt template
- model/runtime options

Output:
- `summary`, `technologies`, `structure`

Prompt contract:
- Instruct model to return strict JSON with only required fields
- Require factual grounding from provided digest only
- Require concise, non-marketing language

Runtime defaults (v1):
- low temperature (e.g., `0.1-0.2`) for consistency
- request timeout with bounded retries on retryable upstream failures

Validation:
- Parse JSON
- Enforce required keys and types
- Normalize `technologies` (dedupe, trim)

### 6) Prompt Design (v1)
System goals:
- Summarize project purpose
- Identify technologies from explicit evidence
- Describe structure from tree + selected files

Prompt payload sections:
- repository metadata
- language stats
- compact tree
- selected snippets
- output schema reminder

Guardrails:
- "If evidence is weak, say uncertain" behavior allowed in prose
- No invention of frameworks/libraries not present in digest

### 7) Configuration

`config/non-informative-files.json`:
- ignored directory names
- ignored extensions
- ignored exact filenames/patterns

`config/runtime.json` (or env-driven equivalent):
- model id
- model context window size
- default checked-in values:
  - `llm_gate.model_id = Qwen/Qwen3-30B-A3B-Thinking-2507`
  - `llm_gate.model_context_window_tokens = 262000`
- repo-processor budget settings:
  - `max_repo_data_ratio_in_prompt` (default `0.65`)
  - `bytes_per_token_estimate` (default `4`)
  - category weights:
    - `documentation_weight` (default `0.40`)
    - `tests_weight` (default `0.20`)
    - `build_package_weight` (default `0.20`)
    - `code_weight` (default `0.20`)
- llm/runtime settings:
  - `max_output_tokens`
  - timeouts / retries
- github-gate extraction limits:
  - `max_docs_total_bytes`
  - `max_tests_total_bytes`
  - `max_code_total_bytes`
  - `max_build_package_total_bytes`
  - `max_single_file_bytes` (safety cap)

Environment variables:
- `NEBIUS_API_KEY` (required)
- optional runtime overrides (timeouts, model id)

### 8) Logging and Observability
Requirement: one sequential debug log file per summarize request.

Filename format:
- `requested-[repo-name]-[timestamp]-[request-id].log`

Recommended content order:
1. request metadata (request id, repo url, timestamps)
2. GitHub upstream calls + status + latency
3. selection decisions (kept/skipped paths + reasons)
4. LLM upstream call metadata + latency
5. parsed output + normalization notes
6. final HTTP status

Security in logs:
- never log `NEBIUS_API_KEY`
- redact sensitive headers/tokens
- cap logged snippet lengths

### 9) Reliability and Limits
- Validate and normalize URL before any upstream call
- Apply strict request and upstream timeouts
- Fail fast on inaccessible repos (not found/private/inaccessible in v1 mode)
- Return actionable error messages
- Respect unauthenticated GitHub rate limits with clear 429/503 behavior

### 10) Testing Strategy (design-level)
- Unit tests:
  - URL parsing/validation
  - file scoring and exclusion rules
  - token budget trimming behavior
  - response schema validation from LLM output
- Integration tests:
  - happy-path public repos
  - non-public/non-existent repos
  - large repo with aggressive truncation
  - upstream failure simulation

### 11) Open Decisions to Finalize
1. Whether to add optional GitHub token support in v1.1 for higher limits
2. Whether to return optional confidence notes in API response (currently omitted)
