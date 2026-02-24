# Phase 2 - Implement `github-gate` Core + CLI (Kickoff Prompt)

Implement the `github-gate` module according to `docs/architecture-and-design.md`.
This phase is focused on core GitHub extraction behavior and a manual CLI runner.

## Objective
Build a production-ready v1 `github-gate` adapter that:
- validates and normalizes GitHub repo URLs
- verifies repository accessibility
- fetches baseline repo signals
- exposes explicit extraction helpers for documentation, tests, and main code
- uses `ghapi` for GitHub API access
- enforces adapter-owned timeout/retry/error mapping policy
- provides a CLI to fetch selected entities and export a structured Markdown payload for LLM input

## Scope (In)
1. Add `github-gate` implementation and internal DTOs.
2. Add typed exceptions for adapter failures.
3. Add configuration support for github-gate extraction limits (with defaults), expressed primarily in bytes.
4. Add and use `config/non-informative-files.json` to skip non-informative/binary/noisy artifacts.
5. Add CLI command to run github-gate manually and export selected entities to Markdown.
6. Update `requirements.txt` for phase-2 runtime dependencies.
7. Update `impl-process/RESUME-CODING.md` after implementation.

## Scope (Out)
- Do not implement `repo-processor`.
- Do not implement `llm-gate`.
- Do not change `/summarize` behavior away from current phase-1 `501` stub.
- Do not add private repo support for v1.
- Do not implement commit-title retrieval in this phase.
- Do not add new automated test suites in this phase (moved to v2).

## Required Interface (Must Exist)
Implement these methods in `github-gate`:
- `parse_repo_url(github_url: str) -> RepoRef`
- `verify_repo_access(repo: RepoRef) -> None`
- `get_repo_metadata(repo: RepoRef) -> RepoMetadata`
- `get_languages(repo: RepoRef) -> dict[str, int]`
- `get_tree(repo: RepoRef) -> list[TreeEntry]`
- `get_readme(repo: RepoRef) -> ReadmeData | None`
- `get_file_content(repo: RepoRef, path: str) -> FileContent`
- `get_documentation(tree: list[TreeEntry], metadata: RepoMetadata, limits: GithubGateLimits) -> DocumentationData | None`
- `get_tests(tree: list[TreeEntry], limits: GithubGateLimits) -> list[FileContent]`
- `get_code(tree: list[TreeEntry], limits: GithubGateLimits) -> list[FileContent]`

## DTOs / Data Contracts
Define explicit dataclasses or pydantic models (your choice) for:
- `RepoRef(owner: str, repo: str)`
- `RepoMetadata(owner, repo, default_branch, description, topics, homepage)`
- `TreeEntry(path, type, size, api_url, download_url)`
- `ReadmeData(source_url, content_text, byte_size)`
- `FileContent(path, source_url, content_text, byte_size)`
- `DocumentationData(source_url, content_text, files: list[FileContent], total_bytes)`
- `GithubGateLimits(...)`
- `RepoSnapshot` containing:
  - owner, repo, default_branch
  - description, topics, homepage
  - languages (language -> bytes)
  - tree_entries (with file URLs when available)
  - readme (optional, actual content)
  - documentation (optional, actual content)

## Behavioral Requirements

### URL Parsing
- Accept `https://github.com/{owner}/{repo}` with optional trailing slash.
- Reject non-GitHub URLs.
- Reject URLs that do not resolve to a repo path.
- Normalize to canonical owner/repo.

### Access Verification (v1 unauthenticated mode)
- Use GitHub REST via `ghapi`.
- If inaccessible/not-found/private under unauthenticated mode, raise typed exception mapped later to HTTP `404`.

### Retry and Timeout Policy (adapter-owned)
- Use `ghapi` as transport client, but implement policy in adapter code.
- Per-call timeout defaults:
  - connect: `2s`
  - read: `8s`
  - attempt cap: `10s`
- Retryable:
  - network timeout/error
  - HTTP `429`, `502`, `503`, `504`
  - HTTP `403` only when rate-limit behavior is indicated
- Non-retryable:
  - `400`, `401`, `403` (non-rate-limit), `404`, response schema errors
- Max retries: `2` (3 attempts total)
- Backoff: `0.5s`, `1.0s` (+ small jitter optional)

### Retrieval Order (Mandatory)
- Deterministic ordering is required.
- `get_documentation` and `get_tests`:
  - pure breadth-first traversal (top-level directory first, then deeper levels)
  - within the same depth level, sort lexicographically
- `get_code`:
  - Step A: seed likely entry points first (`main.*`, `app.*`, `server.*`, common CLI entry files)
  - Step B: retrieve remaining candidates in breadth-first order
  - within the same depth level, sort lexicographically

### Extraction Rules
- `get_documentation`:
  - if repository "About" section has a link (`homepage` from repo metadata), fetch that single page content
  - do not follow links from README for documentation crawling
  - do not follow links found on the fetched "About" page
  - inspect `docs/` and `documentation/` directories and fetch contents within limits
- `get_tests`:
  - locate likely test paths (`tests/`, `test/`, `*_test.*`, `test_*.*`)
- `get_code`:
  - apply entrypoint seeding first, then BFS for remaining files
- For all extraction methods:
  - apply ignore rules from `config/non-informative-files.json`
  - skip binary/non-text files
  - stop when byte budget is exhausted

### Limits (Byte-Based)
Support config values (with defaults):
- `max_docs_total_bytes`
- `max_tests_total_bytes`
- `max_code_total_bytes`
- `max_single_file_bytes` (large safety cap)

Byte accounting and token estimation:
- Use UTF-8 encoded text byte length for all size accounting:
  - `utf8_bytes = len(content_text.encode("utf-8"))`
- Use estimated token conversion for context planning:
  - `estimated_tokens = ceil(utf8_bytes / 4)`
- Optional conservative char estimate may be tracked as:
  - `estimated_chars ~= utf8_bytes`
- Include byte totals and estimated token totals in CLI output summary.

### Partial Failure Policy (Best-Effort)
- Continue on partial failures for individual entities/files/links.
- Record each warning and continue extracting remaining requested data.
- Only fail hard on fatal conditions (e.g., invalid URL, repository inaccessible).

## Error Types (Typed Exceptions)
Create explicit exceptions such as:
- `InvalidGithubUrlError`
- `RepositoryInaccessibleError`
- `GithubRateLimitError`
- `GithubUpstreamError`
- `GithubTimeoutError`
- `GithubResponseShapeError`

Each exception should carry:
- machine-readable code
- human-readable message
- optional upstream status/context

## CLI Requirement (Manual Validation Tool)
Add a CLI entry point to test github-gate end-to-end without invoking the API endpoint.

Suggested command:
- `python -m app.github_gate.cli --github-url <url> --entities <list|all> --output <path.md>`

CLI arguments:
- `--github-url` (required)
- `--entities` (required): comma-separated list from:
  - `metadata,languages,tree,readme,documentation,tests,code`
  - or `all` (fetch all defined entities)
- `--output` (required): output Markdown path
- optional byte-limit overrides for docs/tests/code

CLI output requirements (strict structure):
- Generate one structured Markdown document representing the extracted payload intended for LLM input.
- Include these top-level sections in this exact order:
  1. `# Repository Metadata`
  2. `# Language Stats`
  3. `# Directory Tree`
  4. `# README`
  5. `# Documentation`
  6. `# Tests`
  7. `# Code`
  8. `# Extraction Stats`
  9. `# Warnings`
- For each extracted file block in README/Documentation/Tests/Code sections, use this exact template:
  - `## File: <path-or-label>`
  - `- Source: <url-or-n/a>`
  - `- UTF8 Bytes: <int>`
  - `- Estimated Tokens: <int>`
  - fenced block:
    ```text
    <content>
    ```
- For sections not requested, write exactly: `Not requested`.
- For missing-but-requested sections, write exactly: `Not found`.
- In `# Warnings`, list partial failures as one line each; write `None` when empty.

CLI exit behavior:
- Exit code `0` for successful best-effort extraction (including partial warnings).
- Non-zero exit only for fatal failures (invalid URL, inaccessible repository, unrecoverable startup/config errors).

## Suggested File Layout
Adjust if needed, but keep boundaries clear:
- `app/github_gate/__init__.py`
- `app/github_gate/models.py`
- `app/github_gate/errors.py`
- `app/github_gate/client.py`
- `app/github_gate/selectors.py` (optional; docs/tests/code selection helpers)
- `app/github_gate/cli.py`
- `config/non-informative-files.json`

## Manual Validation Checklist (Phase 2)
1. Run CLI with `--entities all` on a known public repo.
2. Confirm output Markdown contains all required sections in required order.
3. Confirm extraction stats show UTF-8 bytes and estimated tokens.
4. Confirm code ordering follows: entrypoint seeding first, then breadth-first for remaining files.
5. Confirm docs/tests ordering follows pure breadth-first traversal.
6. Confirm invalid URL produces clear typed error message and non-zero exit.
7. Confirm inaccessible/private repo produces repository-inaccessible error and non-zero exit.
8. Confirm partial failures are reported in `# Warnings` while extraction continues.

## Acceptance Criteria
- No breaking change to current `/summarize` stub behavior.
- `github-gate` methods are callable and conform to required interface.
- Byte-based limits are implemented and respected.
- Retrieval ordering rules are implemented exactly as defined.
- Ignore patterns from `config/non-informative-files.json` are applied.
- CLI works for both entity subsets and `all`, and writes structured Markdown payload.
- CLI warning/continue behavior is implemented.
- `requirements.txt` includes all required runtime dependencies for this phase.
- `impl-process/RESUME-CODING.md` is updated with:
  - what was implemented
  - files touched
  - manual validation results
  - known limitations

## Implementation Notes
- Keep logs structured and avoid logging secrets.
- Keep external API specifics inside adapter boundary.
- Keep code straightforward and deterministic over cleverness.
- Automated test expansion is deferred to Phase 2 v2 (`impl-process/v2/phase2-github-gate-v2.md`).
