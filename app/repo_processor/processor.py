from __future__ import annotations

import math
import re
from dataclasses import replace
from typing import Optional

from .bookkeeper import ContextWindowLimitBookkeeper
from .errors import RepoProcessorBudgetError
from .models import ExtractedRepoMarkdown, ProcessedRepoMarkdown, RepoProcessorConfig
from .parser import parse_extraction_markdown, render_processed_markdown

CORE_FIELDS = [
    "repository_metadata",
    "language_stats",
    "directory_tree",
    "readme",
    "documentation",
    "build_and_package_data",
    "tests",
    "code",
]
BASELINE_FIELDS = ["repository_metadata", "language_stats", "directory_tree", "readme"]
OPTIONAL_FIELDS = ["documentation", "build_and_package_data", "tests", "code"]
BLOCK_TRUNCATED_FIELDS = set(OPTIONAL_FIELDS)


def process_markdown(markdown_text: str, config: RepoProcessorConfig | None = None) -> ProcessedRepoMarkdown:
    parsed = parse_extraction_markdown(markdown_text)
    cfg = config or RepoProcessorConfig.from_runtime_file()
    cfg.validate()

    bookkeeper = ContextWindowLimitBookkeeper(
        model_context_window_tokens=cfg.model_context_window_tokens,
        bytes_per_token_estimate=cfg.bytes_per_token_estimate,
    )
    max_repo_bytes = bookkeeper.max_repo_data_bytes(cfg.max_repo_data_ratio_in_prompt)
    input_bytes = _utf8_len(markdown_text)
    input_tokens = bookkeeper.bytes_to_tokens(input_bytes)

    full_candidate = _build_initial_sections(parsed)
    full_processed = _build_processed(
        sections=full_candidate,
        input_bytes=input_bytes,
        max_repo_bytes=max_repo_bytes,
        bytes_per_token_estimate=cfg.bytes_per_token_estimate,
        truncation_notes=[],
    )
    if full_processed.output_total_utf8_bytes <= max_repo_bytes:
        return full_processed

    sections = _build_initial_sections(parsed)
    truncation_notes: list[str] = []

    body_budget = _body_budget(max_repo_bytes)
    baseline_sizes = {field: _utf8_len(sections[field]) for field in BASELINE_FIELDS}
    baseline_total = sum(baseline_sizes.values())

    if baseline_total > body_budget:
        readme_other = baseline_total - baseline_sizes["readme"]
        readme_allowance = max(0, body_budget - readme_other)
        sections["readme"], readme_truncated = _truncate_for_field(
            field_name="readme",
            content=sections["readme"],
            max_bytes=readme_allowance,
        )
        if readme_truncated:
            truncation_notes.append("README truncated to fit baseline budget.")

        baseline_sizes = {field: _utf8_len(sections[field]) for field in BASELINE_FIELDS}
        baseline_total = sum(baseline_sizes.values())
        if baseline_total > body_budget:
            tree_other = baseline_total - baseline_sizes["directory_tree"]
            tree_allowance = max(0, body_budget - tree_other)
            sections["directory_tree"], tree_truncated = _truncate_for_field(
                field_name="directory_tree",
                content=sections["directory_tree"],
                max_bytes=tree_allowance,
            )
            if tree_truncated:
                truncation_notes.append("Directory tree truncated from end to fit baseline budget.")

        baseline_sizes = {field: _utf8_len(sections[field]) for field in BASELINE_FIELDS}
        baseline_total = sum(baseline_sizes.values())
        if baseline_total > body_budget:
            raise RepoProcessorBudgetError(
                "Baseline sections cannot fit in configured prompt budget.",
                context={"body_budget": body_budget, "baseline_total": baseline_total},
            )

    remaining_budget = max(0, body_budget - baseline_total)
    alloc = _allocate_optional_bytes(
        available_bytes=remaining_budget,
        category_sizes={field: _utf8_len(sections[field]) for field in OPTIONAL_FIELDS},
        weights=cfg.weight_map(),
    )

    for field in OPTIONAL_FIELDS:
        target = alloc.get(field, 0)
        sections[field], was_truncated = _truncate_for_field(field, sections[field], target)
        if was_truncated:
            if target == 0:
                truncation_notes.append(f"{field} truncated to zero due to budget.")
            else:
                truncation_notes.append(f"{field} truncated to allocated budget ({target} bytes).")

    processed = _build_processed(
        sections=sections,
        input_bytes=input_bytes,
        max_repo_bytes=max_repo_bytes,
        bytes_per_token_estimate=cfg.bytes_per_token_estimate,
        truncation_notes=truncation_notes,
    )
    if processed.output_total_utf8_bytes > max_repo_bytes:
        raise RepoProcessorBudgetError(
            "Processed markdown still exceeds max repo-data budget.",
            context={
                "output_total_utf8_bytes": processed.output_total_utf8_bytes,
                "max_repo_data_size_for_prompt_bytes": max_repo_bytes,
            },
        )
    return processed


def _build_initial_sections(parsed: ExtractedRepoMarkdown) -> dict[str, str]:
    sections: dict[str, str] = {}
    for field in CORE_FIELDS:
        value = getattr(parsed, field)
        sections[field] = value if value is not None else "Not found"
    return sections


def _build_processed(
    sections: dict[str, str],
    input_bytes: int,
    max_repo_bytes: int,
    bytes_per_token_estimate: float,
    truncation_notes: list[str],
) -> ProcessedRepoMarkdown:
    data = ProcessedRepoMarkdown(
        repository_metadata=sections["repository_metadata"],
        language_stats=sections["language_stats"],
        directory_tree=sections["directory_tree"],
        readme=sections["readme"],
        documentation=sections["documentation"],
        build_and_package_data=sections["build_and_package_data"],
        tests=sections["tests"],
        code=sections["code"],
        input_total_utf8_bytes=input_bytes,
        output_total_utf8_bytes=0,
        max_repo_data_size_for_prompt_bytes=max_repo_bytes,
        estimated_input_tokens=int(math.ceil(input_bytes / bytes_per_token_estimate)),
        estimated_output_tokens=0,
        bytes_per_token_estimate=bytes_per_token_estimate,
        per_category_bytes={key: _utf8_len(value) for key, value in sections.items()},
        truncation_notes=truncation_notes,
    )
    rendered = render_processed_markdown(data)
    output_bytes = _utf8_len(rendered)
    output_tokens = int(math.ceil(output_bytes / bytes_per_token_estimate))
    return replace(data, output_total_utf8_bytes=output_bytes, estimated_output_tokens=output_tokens)


def _body_budget(max_repo_bytes: int) -> int:
    empty_markdown = (
        "# Repository Metadata\n\n\n"
        "# Language Stats\n\n\n"
        "# Directory Tree\n\n\n"
        "# README\n\n\n"
        "# Documentation\n\n\n"
        "# Build and Package Data\n\n\n"
        "# Tests\n\n\n"
        "# Code\n"
    )
    return max(0, max_repo_bytes - _utf8_len(empty_markdown))


def _truncate_for_field(field_name: str, content: str, max_bytes: int) -> tuple[str, bool]:
    if max_bytes <= 0:
        return "Truncated to zero", True
    if _utf8_len(content) <= max_bytes:
        return content, False
    if field_name in BLOCK_TRUNCATED_FIELDS:
        return _truncate_file_blocks(content, max_bytes), True
    return _truncate_text(content, max_bytes), True


def _truncate_text(content: str, max_bytes: int) -> str:
    if max_bytes <= 0:
        return "Truncated to zero"
    truncated = _truncate_utf8_prefix(content, max_bytes)
    return truncated if truncated.strip() else "Truncated to zero"


def _truncate_file_blocks(content: str, max_bytes: int) -> str:
    if max_bytes <= 0:
        return "Truncated to zero"
    blocks = _split_file_blocks(content)
    if not blocks:
        return _truncate_text(content, max_bytes)

    selected: list[str] = []
    used = 0
    for index, block in enumerate(blocks):
        block_bytes = _utf8_len(block)
        if used + block_bytes <= max_bytes:
            selected.append(block)
            used += block_bytes
            continue
        remaining = max_bytes - used
        partial = _partial_block(block, remaining)
        if partial:
            selected.append(partial)
        break

    if not selected:
        return "Truncated to zero"
    combined = "\n\n".join(selected).strip()
    return combined if combined else "Truncated to zero"


def _split_file_blocks(content: str) -> list[str]:
    starts = [match.start() for match in re.finditer(r"^## File: .+$", content, flags=re.MULTILINE)]
    if not starts:
        return []
    blocks: list[str] = []
    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else len(content)
        block = content[start:end].strip()
        if block:
            blocks.append(block)
    return blocks


def _partial_block(block: str, max_bytes: int) -> str:
    if max_bytes <= 0:
        return ""
    lines = block.splitlines()
    fence_index = None
    for idx, line in enumerate(lines):
        if line.strip().startswith("```"):
            fence_index = idx
            break
    if fence_index is None:
        return _truncate_utf8_prefix(block, max_bytes)

    header_lines = lines[: fence_index + 1]
    header = "\n".join(header_lines) + "\n"
    suffix = "\n```"
    header_bytes = _utf8_len(header)
    suffix_bytes = _utf8_len(suffix)
    if header_bytes + suffix_bytes > max_bytes:
        return _truncate_utf8_prefix("\n".join(lines[: fence_index]), max_bytes)

    content_lines = lines[fence_index + 1 :]
    close_index = len(content_lines)
    for idx, line in enumerate(content_lines):
        if line.strip().startswith("```"):
            close_index = idx
            break
    body = "\n".join(content_lines[:close_index])
    body_limit = max_bytes - header_bytes - suffix_bytes
    truncated_body = _truncate_utf8_prefix(body, body_limit)
    return f"{header}{truncated_body}{suffix}"


def _allocate_optional_bytes(
    available_bytes: int,
    category_sizes: dict[str, int],
    weights: dict[str, float],
) -> dict[str, int]:
    allocation = {key: 0 for key in category_sizes}
    unsatisfied = {
        key
        for key, size in category_sizes.items()
        if size > 0 and weights.get(key, 0.0) > 0
    }
    remaining = max(0, available_bytes)

    while remaining > 0 and unsatisfied:
        total_weight = sum(weights[name] for name in unsatisfied)
        if total_weight <= 0:
            break

        increments = {name: 0 for name in unsatisfied}
        fractions: list[tuple[float, str]] = []
        used = 0
        for name in unsatisfied:
            want = category_sizes[name] - allocation[name]
            share_float = remaining * weights[name] / total_weight
            share_int = min(want, int(math.floor(share_float)))
            if share_int > 0:
                increments[name] += share_int
                used += share_int
            fractions.append((share_float - math.floor(share_float), name))

        leftover = remaining - used
        fractions.sort(key=lambda item: (-item[0], item[1]))
        for _, name in fractions:
            if leftover <= 0:
                break
            want = category_sizes[name] - allocation[name] - increments[name]
            if want <= 0:
                continue
            increments[name] += 1
            leftover -= 1

        progress = 0
        for name, inc in increments.items():
            if inc <= 0:
                continue
            allocation[name] += inc
            progress += inc
        if progress == 0:
            break
        remaining -= progress
        unsatisfied = {name for name in unsatisfied if allocation[name] < category_sizes[name]}

    return allocation


def _truncate_utf8_prefix(text: str, max_bytes: int) -> str:
    if max_bytes <= 0:
        return ""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def _utf8_len(text: Optional[str]) -> int:
    if text is None:
        return 0
    return len(text.encode("utf-8"))
