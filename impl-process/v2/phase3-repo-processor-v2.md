# Phase 3 v2 - `repo-processor` Hardening and Test Plan

This document captures deferred hardening work after Phase 3 core implementation.

## Goals
- Guarantee strict budget compliance for processor output markdown.
- Make budgeting token-aware first (with safety margin), not byte-only first.
- Add focused tests for parser correctness and truncation edge cases.
- Improve deterministic behavior under very tight budgets.

## Priority Fixes
1. Fix zero-allocation sentinel accounting:
   - Current behavior can exceed budget when optional sections are set to `Truncated to zero` because this sentinel text still consumes bytes.
   - Ensure allocation and final rendering account for sentinel bytes (or use truly empty output for dropped sections) so final output never exceeds configured budget.
2. Add parser robustness coverage:
   - Verify section parsing when section bodies contain `# ...` lines inside fenced code/markdown blocks.
3. Add strict budget regression tests:
   - Assert `output_total_utf8_bytes <= max_repo_data_size_for_prompt_bytes` for tight-budget scenarios and real-like samples.
4. Add non-default token-estimate tests:
   - Validate token/byte stats with custom `bytes_per_token_estimate`.
5. Move to token-first budgeting with byte fallback guard:
   - Use section-aware token estimation as the primary planner for truncation/allocation.
   - Apply a conservative safety margin for prompt budget (configurable).
   - Keep a final byte-cap guard after render; if output still exceeds byte cap, truncate again.
   - Log both estimated tokens and final bytes for each processed output.

## Test Matrix

### Parser
- README containing markdown headings inside fenced block.
- Documentation/test/code blocks containing `#` lines.

### Budget Compliance
- Optional categories fully dropped.
- Mixed case: one optional section partially included, others dropped.
- Baseline nearly full budget.
- Token-first planned fit that still misses; byte fallback guard must enforce final cap.

### Allocation/Redistribution
- One category undersized vs allocated share; redistribute remainder proportionally.
- Deterministic tie behavior with equal weights.

## Deliverables
- New tests under `tests/repo_processor/`.
- Updated processor logic with strict post-render budget guarantee.
- Updated `impl-process/RESUME-CODING.md` with validation output.

## Exit Criteria
- No scenario where rendered processor output exceeds max budget.
- Token-first planner is active, with byte guard as mandatory final hard stop.
- Parser tests pass for fenced-content heading edge cases.
- Allocation and truncation behavior remains deterministic.
