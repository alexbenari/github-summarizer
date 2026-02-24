from __future__ import annotations

from typing import Optional

from .errors import RepoProcessorParseError
from .models import ExtractedRepoMarkdown, ProcessedRepoMarkdown

INPUT_HEADER_TO_FIELD = {
    "# Repository Metadata": "repository_metadata",
    "# Language Stats": "language_stats",
    "# Directory Tree": "directory_tree",
    "# README": "readme",
    "# Documentation": "documentation",
    "# Build and Package Data": "build_and_package_data",
    "# Tests": "tests",
    "# Code": "code",
    "# Extraction Stats": "extraction_stats",
    "# Warnings": "warnings",
}

OUTPUT_SECTIONS = [
    ("# Repository Metadata", "repository_metadata"),
    ("# Language Stats", "language_stats"),
    ("# Directory Tree", "directory_tree"),
    ("# README", "readme"),
    ("# Documentation", "documentation"),
    ("# Build and Package Data", "build_and_package_data"),
    ("# Tests", "tests"),
    ("# Code", "code"),
]


def parse_extraction_markdown(markdown_text: str) -> ExtractedRepoMarkdown:
    if not markdown_text or not markdown_text.strip():
        raise RepoProcessorParseError("Input markdown is empty.")

    sections = _extract_top_level_sections(markdown_text)
    return ExtractedRepoMarkdown(
        repository_metadata=sections.get("repository_metadata"),
        language_stats=sections.get("language_stats"),
        directory_tree=sections.get("directory_tree"),
        readme=sections.get("readme"),
        documentation=sections.get("documentation"),
        build_and_package_data=sections.get("build_and_package_data"),
        tests=sections.get("tests"),
        code=sections.get("code"),
        extraction_stats=sections.get("extraction_stats"),
        warnings=sections.get("warnings"),
    )


def render_processed_markdown(data: ProcessedRepoMarkdown) -> str:
    parts: list[str] = []
    for header, field_name in OUTPUT_SECTIONS:
        value = getattr(data, field_name)
        if value is None:
            value = "Not found"
        parts.append(f"{header}\n{value.strip()}")
    return "\n\n".join(parts) + "\n"


def _extract_top_level_sections(markdown_text: str) -> dict[str, Optional[str]]:
    results: dict[str, Optional[str]] = {field: None for field in INPUT_HEADER_TO_FIELD.values()}
    lines = _lines_with_ends(markdown_text)
    boundaries = _known_section_boundaries(lines)
    if not boundaries:
        return results

    for index, (heading, start_line_index, start_offset) in enumerate(boundaries):
        field = INPUT_HEADER_TO_FIELD[heading]
        line = lines[start_line_index]
        start = start_offset + len(line)
        end = boundaries[index + 1][2] if index + 1 < len(boundaries) else len(markdown_text)
        body = markdown_text[start:end].strip()
        results[field] = body if body else None
    return results


def _known_section_boundaries(lines: list[str]) -> list[tuple[str, int, int]]:
    boundaries: list[tuple[str, int, int]] = []
    offset = 0
    in_fence = False

    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
        if not in_fence and stripped in INPUT_HEADER_TO_FIELD:
            boundaries.append((stripped, index, offset))
        offset += len(line)

    return boundaries


def _lines_with_ends(text: str) -> list[str]:
    return text.splitlines(keepends=True)
