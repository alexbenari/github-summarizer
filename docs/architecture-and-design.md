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
3. `github-gate` fetches baseline signals: repository metadata, language stats, directory tree (with sizes and file URLs), and README (if present).
4. `repo-processor` estimates baseline token usage and computes remaining budget.
5. `repo-processor` ranks additional candidates and requests them incrementally from `github-gate` (highest score first), stopping when budget/time limits are near.
6. `repo-processor` finalizes a truncated/normalized repo digest.
7. `llm-gate` sends structured prompt + selected repo digest.
8. `llm-gate` validates/parses model output into response schema.
9. `service` returns normalized API response.

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
  - if README has a direct documentation link, fetch only that single linked page
  - also inspect `docs/` or `documentation/` directories and fetch contents within configured limits
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
- `readme` (optional; includes actual content text and source URL)
- `documentation` (optional; includes source URL and fetched text/content when present)

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
- `get_documentation(tree: list[TreeEntry], readme: ReadmeData | None, limits: GithubGateLimits) -> DocumentationData | None`
  - Fetches one direct README documentation link if present.
  - Also scans for `docs/` or `documentation/` directories and fetches contents within configured limits.
- `get_tests(tree: list[TreeEntry], limits: GithubGateLimits) -> list[FileContent]`
  - Finds likely test folders/files and returns test contents up to configured limits.
- `get_code(tree: list[TreeEntry], limits: GithubGateLimits) -> list[FileContent]`
  - Returns likely main code files up to configured limits.
  - Attempts to include entry points first (`main.*`, `app.*`, `server.*`, common CLI entry files), then high-value core files.

#### C) `repo-processor` (selection + budget manager)
Responsibilities:
- Determine what content is most informative
- Exclude non-informative/binary/generated artifacts
- Fit selected content into model input budget

Input:
- `RepoSnapshot`
- config (`non-informative-files.json`, token policy)
- target context size

Output (`RepoDigest`):
- normalized repository profile
- compact directory tree summary
- selected file snippets with paths
- selection rationale metadata (for logging)

Selection strategy (ordered priority):
1. README and top-level docs (`README*`, `docs/index*`, contribution/setup docs)
2. Package/build metadata (`pyproject.toml`, `package.json`, `go.mod`, `Cargo.toml`, etc.)
3. Entrypoints (`main.*`, `app.*`, `server.*`, CLI entry files)
4. Core source files in dominant language directories
5. Test and CI config (small representative subset)

Exclusion defaults:
- lock/vendor/build artifacts (`node_modules`, `dist`, `build`, `.venv`, `vendor`, `.git`)
- binary/media archives
- very large generated files and minified bundles
- known cache/temp directories

Token budgeting:
- Use 70% of model context for repository digest
- Reserve 30% for system instructions, output schema guidance, and model response
- Character-to-token estimate: `tokens ~= chars / 4` (conservative)
- Hard caps:
  - max files selected
  - max chars per file
  - max total chars

Truncation policy:
- Prefer keeping headers, module docstrings, and exported API sections
- Preserve path + line-range metadata for each snippet
- Drop lowest-priority items first when budget is exceeded

#### D) `llm-gate` (model adapter)
Responsibilities:
- Build deterministic prompt payload
  - Use response_format parameter with {"type": "json_schema"} to get structured JSON output
- Invoke Nebius model endpoint
- Parse and validate structured output

Input:
- `RepoDigest`
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
- token budget ratios
- max files / max file chars / timeout / retries
- github-gate extraction limits:
  - max README-linked documentation pages fetched (v1 default: `1`)
  - max docs directory files fetched
  - max test files fetched
  - max code files fetched
  - large upper bound for per-document size cap (safety only; not expected to bind in normal use)

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
1. Exact Nebius model id for v1 (quality/latency/cost tradeoff)
2. Whether to add optional GitHub token support in v1.1 for higher limits
3. Whether to return optional confidence notes in API response (currently omitted)
