from __future__ import annotations

from typing import Optional

from .client import estimated_tokens_for_bytes
from .entities import ALL_ENTITIES_SET
from .models import DocumentationData, FileContent, ReadmeData, RepoRef


def render_extraction_markdown(
    repo: RepoRef,
    requested: set[str],
    results: dict[str, object],
    warnings: list[str],
) -> str:
    lines: list[str] = []

    lines.append("# Repository Metadata")
    if "metadata" not in requested:
        lines.append("Not requested")
    elif results.get("metadata") is None:
        lines.append("Not found")
    else:
        metadata = results["metadata"]
        lines.append(f"- Owner: {metadata.owner}")
        lines.append(f"- Repo: {metadata.repo}")
        lines.append(f"- Default Branch: {metadata.default_branch}")
        lines.append(f"- Description: {metadata.description or 'n/a'}")
        lines.append(f"- Topics: {', '.join(metadata.topics) if metadata.topics else 'n/a'}")
        lines.append(f"- Homepage: {metadata.homepage or 'n/a'}")

    lines.append("")
    lines.append("# Language Stats")
    if "languages" not in requested:
        lines.append("Not requested")
    elif not results.get("languages"):
        lines.append("Not found")
    else:
        languages: dict[str, int] = results["languages"]  # type: ignore[assignment]
        for language, count in sorted(languages.items(), key=lambda item: item[1], reverse=True):
            lines.append(f"- {language}: {count}")

    lines.append("")
    lines.append("# Directory Tree")
    if "tree" not in requested:
        lines.append("Not requested")
    elif not results.get("tree"):
        lines.append("Not found")
    else:
        for entry in results["tree"]:  # type: ignore[index]
            lines.append(f"- {entry.path} ({entry.type}, {entry.size})")

    lines.append("")
    lines.append("# README")
    if "readme" not in requested:
        lines.append("Not requested")
    else:
        readme = results.get("readme")
        if readme is None:
            lines.append("Not found")
        else:
            _render_file_block(lines, path_or_label="README", source=readme.source_url, content=readme.content_text)

    lines.append("")
    lines.append("# Documentation")
    if "documentation" not in requested:
        lines.append("Not requested")
    else:
        doc_data: Optional[DocumentationData] = results.get("documentation")  # type: ignore[assignment]
        if doc_data is None or not doc_data.files:
            lines.append("Not found")
        else:
            for file_data in doc_data.files:
                _render_file_block(
                    lines,
                    path_or_label=file_data.path,
                    source=file_data.source_url,
                    content=file_data.content_text,
                    byte_size=file_data.byte_size,
                )

    lines.append("")
    lines.append("# Build and Package Data")
    if "build_package" not in requested:
        lines.append("Not requested")
    else:
        build_files: list[FileContent] = results.get("build_package", [])  # type: ignore[assignment]
        if not build_files:
            lines.append("Not found")
        else:
            for file_data in build_files:
                _render_file_block(
                    lines,
                    path_or_label=file_data.path,
                    source=file_data.source_url,
                    content=file_data.content_text,
                    byte_size=file_data.byte_size,
                )

    lines.append("")
    lines.append("# Tests")
    if "tests" not in requested:
        lines.append("Not requested")
    else:
        tests: list[FileContent] = results.get("tests", [])  # type: ignore[assignment]
        if not tests:
            lines.append("Not found")
        else:
            for file_data in tests:
                _render_file_block(
                    lines,
                    path_or_label=file_data.path,
                    source=file_data.source_url,
                    content=file_data.content_text,
                    byte_size=file_data.byte_size,
                )

    lines.append("")
    lines.append("# Code")
    if "code" not in requested:
        lines.append("Not requested")
    else:
        code_files: list[FileContent] = results.get("code", [])  # type: ignore[assignment]
        if not code_files:
            lines.append("Not found")
        else:
            for file_data in code_files:
                _render_file_block(
                    lines,
                    path_or_label=file_data.path,
                    source=file_data.source_url,
                    content=file_data.content_text,
                    byte_size=file_data.byte_size,
                )

    lines.append("")
    lines.append("# Extraction Stats")
    _render_stats(lines=lines, results=results)

    lines.append("")
    lines.append("# Warnings")
    if not warnings:
        lines.append("None")
    else:
        for item in warnings:
            lines.append(item)
    lines.append("")
    return "\n".join(lines)


def render_full_extraction_markdown(
    repo: RepoRef,
    results: dict[str, object],
    warnings: list[str],
) -> str:
    return render_extraction_markdown(
        repo=repo,
        requested=set(ALL_ENTITIES_SET),
        results=results,
        warnings=warnings,
    )


def _render_file_block(
    lines: list[str],
    path_or_label: str,
    source: str,
    content: str,
    byte_size: Optional[int] = None,
) -> None:
    content_bytes = byte_size if byte_size is not None else len(content.encode("utf-8"))
    lines.append(f"## File: {path_or_label}")
    lines.append(f"- Source: {source or 'n/a'}")
    lines.append(f"- UTF8 Bytes: {content_bytes}")
    lines.append(f"- Estimated Tokens: {estimated_tokens_for_bytes(content_bytes)}")
    lines.append("```text")
    lines.append(content)
    lines.append("```")


def _render_stats(lines: list[str], results: dict[str, object]) -> None:
    totals = {
        "readme_bytes": 0,
        "documentation_bytes": 0,
        "tests_bytes": 0,
        "code_bytes": 0,
        "build_package_bytes": 0,
    }
    readme: Optional[ReadmeData] = results.get("readme")  # type: ignore[assignment]
    if readme is not None:
        totals["readme_bytes"] = readme.byte_size

    docs: Optional[DocumentationData] = results.get("documentation")  # type: ignore[assignment]
    if docs is not None:
        totals["documentation_bytes"] = docs.total_bytes

    tests: list[FileContent] = results.get("tests", [])  # type: ignore[assignment]
    totals["tests_bytes"] = sum(item.byte_size for item in tests)
    code_files: list[FileContent] = results.get("code", [])  # type: ignore[assignment]
    totals["code_bytes"] = sum(item.byte_size for item in code_files)
    build_files: list[FileContent] = results.get("build_package", [])  # type: ignore[assignment]
    totals["build_package_bytes"] = sum(item.byte_size for item in build_files)

    grand_total = sum(totals.values())
    for key in ("readme_bytes", "documentation_bytes", "tests_bytes", "code_bytes", "build_package_bytes"):
        lines.append(f"- {key}: {totals[key]}")
        lines.append(f"- {key.replace('_bytes', '_estimated_tokens')}: {estimated_tokens_for_bytes(totals[key])}")
    lines.append(f"- total_utf8_bytes: {grand_total}")
    lines.append(f"- total_estimated_tokens: {estimated_tokens_for_bytes(grand_total)}")
