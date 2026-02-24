from __future__ import annotations

from .errors import LlmDigestParseError
from .models import RepoDigest

HEADER_TO_FIELD = {
    "# Repository Metadata": "repository_metadata",
    "# Language Stats": "language_stats",
    "# Directory Tree": "tree_summary",
    "# README": "readme_text",
    "# Documentation": "documentation_text",
    "# Build and Package Data": "build_package_text",
    "# Tests": "test_snippets",
    "# Code": "code_snippets",
}


def parse_repo_digest_markdown(markdown_text: str) -> RepoDigest:
    if markdown_text is None:
        raise LlmDigestParseError("markdown_text cannot be None.")
    lines = markdown_text.splitlines(keepends=True)
    boundaries = _known_boundaries(lines)
    if not boundaries:
        raise LlmDigestParseError("Malformed digest markdown: no known top-level sections found.")
    values = {field: "" for field in HEADER_TO_FIELD.values()}
    for idx, (heading, line_idx, start_offset) in enumerate(boundaries):
        field = HEADER_TO_FIELD[heading]
        line = lines[line_idx]
        start = start_offset + len(line)
        end = boundaries[idx + 1][2] if idx + 1 < len(boundaries) else len(markdown_text)
        body = markdown_text[start:end].strip()
        if body in {"Not requested", "Not found"}:
            body = ""
        values[field] = body
    return RepoDigest(**values)


def _known_boundaries(lines: list[str]) -> list[tuple[str, int, int]]:
    boundaries: list[tuple[str, int, int]] = []
    offset = 0
    in_fence = False
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
        if not in_fence and stripped in HEADER_TO_FIELD:
            boundaries.append((stripped, idx, offset))
        offset += len(line)
    return boundaries
