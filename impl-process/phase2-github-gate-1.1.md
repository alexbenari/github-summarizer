# Phase 2.1 - `github-gate` Addendum: Build and Package Data Extraction

This addendum extends `impl-process/phase2-github-gate.md` with one new extraction capability:
- `get_build_and_package_data`

## Goal
Improve repository understanding by extracting build/package/tooling configuration files, which are high-signal for:
- technologies/dependencies
- project layout and module boundaries
- runtime/build/test tooling

## New Required Interface Method
- `get_build_and_package_data(tree: list[TreeEntry], limits: GithubGateLimits) -> list[FileContent]`

## Method Behavior

### Purpose
Extract files that define dependencies, build system, packaging, and major tooling config.

### Retrieval Order
- Deterministic ordering required.
- Priority stage 1: candidate files in repo root.
- Priority stage 2: breadth-first by directory depth.
- Tie-breaker within same depth: lexicographic path order.

### Candidate File Patterns (Priority Order)
1. Python:
- `pyproject.toml`
- `setup.py`
- `setup.cfg`
- `requirements.txt`
- `requirements-*.txt`
- `Pipfile`

2. JavaScript/TypeScript:
- `package.json`
- `tsconfig.json`
- `pnpm-workspace.yaml`

3. Go/Rust/Java/Other:
- `go.mod`
- `Cargo.toml`
- `pom.xml`
- `build.gradle`
- `build.gradle.kts`
- `composer.json`
- `Gemfile`

4. Build/runtime orchestration:
- `Makefile`
- `Dockerfile`
- `docker-compose.yml`
- `docker-compose.yaml`

### Filters
- Apply ignore rules from `config/non-informative-files.json`.
- Skip binary/non-text files.
- Skip files exceeding `max_single_file_bytes`.

### Limits
- Stop when `max_build_package_total_bytes` is reached.
- Byte accounting uses UTF-8 text bytes:
  - `utf8_bytes = len(content_text.encode("utf-8"))`
- Token estimate:
  - `estimated_tokens = ceil(utf8_bytes / 4)`

### Failure Policy
- Best-effort:
  - continue on per-file fetch failure
  - record warning entries
  - only fail on fatal repo-level errors

## Contract Updates

### `GithubGateLimits`
Add:
- `max_build_package_total_bytes`

### `RepoSnapshot`
Add:
- `build_and_package_files: list[FileContent]`

### CLI
Add new entity selector:
- `build_package`

Updated examples:
- `--entities metadata,languages,tree,readme,build_package,tests,code`
- `--entities all`

### CLI Output
Add section:
- `# Build and Package Data`

Per-file block format stays identical to phase 2:
- `## File: <path>`
- `- Source: <url-or-n/a>`
- `- UTF8 Bytes: <int>`
- `- Estimated Tokens: <int>`
- fenced text content block

## Priority Guidance Update (Extraction Semantics)
Within overall phase-2 extraction planning, use this updated conceptual priority:
1. README and top-level docs
2. Tests
3. Entry points and code
4. Build/package/tooling files (`get_build_and_package_data`)

Note:
- Tests remain highly informative and should stay high-priority.
- Build/package data is now explicitly extracted because it quickly identifies stack, modules, and execution model.

## Acceptance Criteria (for this addendum)
- `get_build_and_package_data` exists and is callable.
- Byte limits for build/package extraction are enforced.
- CLI supports `build_package` entity and emits `# Build and Package Data`.
- `RepoSnapshot` includes `build_and_package_files`.
- Best-effort warning behavior applies to this method as well.
