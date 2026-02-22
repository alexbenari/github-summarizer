from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from .client import GithubGate, estimated_tokens_for_bytes
from .errors import GithubGateError
from .models import DocumentationData, FileContent, GithubGateLimits, ReadmeData, RepoRef

SECTION_ORDER = [
    "metadata",
    "languages",
    "tree",
    "readme",
    "documentation",
    "tests",
    "code",
    "stats",
    "warnings",
]

ENTITY_NAMES = {"metadata", "languages", "tree", "readme", "documentation", "tests", "code"}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manual github-gate extraction runner.")
    parser.add_argument("--github-url", required=True, help="Repository URL.")
    parser.add_argument(
        "--entities",
        required=True,
        help="Comma-separated subset of metadata,languages,tree,readme,documentation,tests,code or all",
    )
    parser.add_argument("--output", required=True, help="Markdown output path.")
    parser.add_argument("--max-docs-total-bytes", type=int, default=None)
    parser.add_argument("--max-tests-total-bytes", type=int, default=None)
    parser.add_argument("--max-code-total-bytes", type=int, default=None)
    parser.add_argument("--max-single-file-bytes", type=int, default=None)
    parser.add_argument("--max-readme-doc-links", type=int, default=None)
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    client = GithubGate()

    try:
        repo = client.parse_repo_url(args.github_url)
        client.verify_repo_access(repo)
    except GithubGateError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    requested = _parse_entities(args.entities)
    limits = _effective_limits(client.limits, args)

    results: dict[str, object] = {}
    warnings: list[str] = []

    try:
        metadata = None
        if "metadata" in requested or "tree" in requested or "readme" in requested:
            metadata = client.get_repo_metadata(repo)
        if "metadata" in requested:
            results["metadata"] = metadata

        if "languages" in requested:
            results["languages"] = client.get_languages(repo)

        tree = None
        if any(name in requested for name in {"tree", "documentation", "tests", "code"}):
            tree = client.get_tree(repo)
        if "tree" in requested:
            results["tree"] = tree

        readme = None
        if "readme" in requested or "documentation" in requested:
            readme = client.get_readme(repo)
        if "readme" in requested:
            results["readme"] = readme

        if "documentation" in requested:
            results["documentation"] = client.get_documentation(tree=tree or [], readme=readme, limits=limits)
        if "tests" in requested:
            results["tests"] = client.get_tests(tree=tree or [], limits=limits)
        if "code" in requested:
            results["code"] = client.get_code(tree=tree or [], limits=limits)
    except GithubGateError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    warnings.extend(client.warnings)
    markdown = _render_markdown(repo=repo, requested=requested, results=results, warnings=warnings)
    Path(args.output).write_text(markdown, encoding="utf-8")
    return 0


def _parse_entities(raw: str) -> set[str]:
    cleaned = raw.strip().lower()
    if cleaned == "all":
        return set(ENTITY_NAMES)
    parsed = {item.strip() for item in cleaned.split(",") if item.strip()}
    invalid = parsed - ENTITY_NAMES
    if invalid:
        raise SystemExit(f"Invalid --entities value(s): {', '.join(sorted(invalid))}")
    return parsed


def _effective_limits(base: GithubGateLimits, args: argparse.Namespace) -> GithubGateLimits:
    return GithubGateLimits(
        max_readme_doc_links=args.max_readme_doc_links or base.max_readme_doc_links,
        max_docs_total_bytes=args.max_docs_total_bytes or base.max_docs_total_bytes,
        max_tests_total_bytes=args.max_tests_total_bytes or base.max_tests_total_bytes,
        max_code_total_bytes=args.max_code_total_bytes or base.max_code_total_bytes,
        max_single_file_bytes=args.max_single_file_bytes or base.max_single_file_bytes,
    )


def _render_markdown(repo: RepoRef, requested: set[str], results: dict[str, object], warnings: list[str]) -> str:
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

    grand_total = sum(totals.values())
    for key in ("readme_bytes", "documentation_bytes", "tests_bytes", "code_bytes"):
        lines.append(f"- {key}: {totals[key]}")
        lines.append(f"- {key.replace('_bytes', '_estimated_tokens')}: {estimated_tokens_for_bytes(totals[key])}")
    lines.append(f"- total_utf8_bytes: {grand_total}")
    lines.append(f"- total_estimated_tokens: {estimated_tokens_for_bytes(grand_total)}")


if __name__ == "__main__":
    raise SystemExit(main())
