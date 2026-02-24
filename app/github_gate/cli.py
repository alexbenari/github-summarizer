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

ENTITY_NAMES = {"metadata", "languages", "tree", "readme", "documentation", "build_package", "tests", "code"}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manual github-gate extraction runner.")
    parser.add_argument("--github-url", required=True, help="Repository URL.")
    parser.add_argument(
        "--entities",
        required=True,
        help="Comma-separated subset of metadata,languages,tree,readme,documentation,build_package,tests,code or all",
    )
    parser.add_argument(
        "--output",
        required=False,
        default=None,
        help="Markdown output path. Default: outputs/<owner>-<repo>.md",
    )
    parser.add_argument("--max-docs-total-bytes", type=int, default=None)
    parser.add_argument("--max-tests-total-bytes", type=int, default=None)
    parser.add_argument("--max-code-total-bytes", type=int, default=None)
    parser.add_argument("--max-build-package-total-bytes", type=int, default=None)
    parser.add_argument("--max-single-file-bytes", type=int, default=None)
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    client = GithubGate()

    try:
        _log("Parsing repository URL")
        repo = client.parse_repo_url(args.github_url)
        _log(f"Verifying repository access: {repo.owner}/{repo.repo}")
        client.verify_repo_access(repo)
    except GithubGateError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    requested = _parse_entities(args.entities)
    limits = _effective_limits(client.limits, args)

    results: dict[str, object] = {}
    warnings: list[str] = []

    metadata = None
    if "metadata" in requested or "tree" in requested or "readme" in requested or "documentation" in requested:
        _log("Fetching repository metadata")
        metadata = _best_effort_call(
            call=lambda: client.get_repo_metadata(repo),
            warnings=warnings,
            label="metadata",
            default=None,
        )
    if "metadata" in requested:
        results["metadata"] = metadata

    if "languages" in requested:
        _log("Fetching language stats")
        results["languages"] = _best_effort_call(
            call=lambda: client.get_languages(repo),
            warnings=warnings,
            label="languages",
            default={},
        )

    tree = None
    if any(name in requested for name in {"tree", "documentation", "build_package", "tests", "code"}):
        _log("Fetching repository tree")
        tree = _best_effort_call(
            call=lambda: client.get_tree(repo),
            warnings=warnings,
            label="tree",
            default=None,
        )
    if "tree" in requested:
        results["tree"] = tree

    readme = None
    if "readme" in requested:
        _log("Fetching README")
        readme = _best_effort_call(
            call=lambda: client.get_readme(repo),
            warnings=warnings,
            label="readme",
            default=None,
        )
    if "readme" in requested:
        results["readme"] = readme

    if "documentation" in requested:
        _log("Extracting documentation files")
        if tree is None:
            warnings.append("documentation: skipped because tree is unavailable")
            results["documentation"] = None
        elif metadata is None:
            warnings.append("documentation: skipped because metadata is unavailable")
            results["documentation"] = None
        else:
            results["documentation"] = _best_effort_call(
                call=lambda: client.get_documentation(tree=tree, metadata=metadata, limits=limits),
                warnings=warnings,
                label="documentation",
                default=None,
            )

    if "build_package" in requested:
        _log("Extracting build/package files")
        if tree is None:
            warnings.append("build_package: skipped because tree is unavailable")
            results["build_package"] = []
        else:
            results["build_package"] = _best_effort_call(
                call=lambda: client.get_build_and_package_data(tree=tree, limits=limits),
                warnings=warnings,
                label="build_package",
                default=[],
            )

    if "tests" in requested:
        _log("Extracting test files")
        if tree is None:
            warnings.append("tests: skipped because tree is unavailable")
            results["tests"] = []
        else:
            results["tests"] = _best_effort_call(
                call=lambda: client.get_tests(tree=tree, limits=limits),
                warnings=warnings,
                label="tests",
                default=[],
            )

    if "code" in requested:
        _log("Extracting code files")
        if tree is None:
            warnings.append("code: skipped because tree is unavailable")
            results["code"] = []
        else:
            results["code"] = _best_effort_call(
                call=lambda: client.get_code(tree=tree, limits=limits),
                warnings=warnings,
                label="code",
                default=[],
            )

    warnings.extend(client.warnings)
    _log("Rendering markdown output")
    markdown = _render_markdown(repo=repo, requested=requested, results=results, warnings=warnings)
    output_path = _resolve_output_path(repo=repo, raw_output=args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    print(f"Wrote extraction output to {output_path}")
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
        max_docs_total_bytes=args.max_docs_total_bytes or base.max_docs_total_bytes,
        max_tests_total_bytes=args.max_tests_total_bytes or base.max_tests_total_bytes,
        max_code_total_bytes=args.max_code_total_bytes or base.max_code_total_bytes,
        max_build_package_total_bytes=args.max_build_package_total_bytes or base.max_build_package_total_bytes,
        max_single_file_bytes=args.max_single_file_bytes or base.max_single_file_bytes,
    )


def _resolve_output_path(repo: RepoRef, raw_output: Optional[str]) -> Path:
    if raw_output and raw_output.strip():
        return Path(raw_output).expanduser().resolve()
    filename = f"{repo.owner.lower()}-{repo.repo.lower()}.md"
    return (Path.cwd() / "outputs" / filename).resolve()


def _log(message: str) -> None:
    print(f"[github-gate-cli] {message}")


def _best_effort_call(call, warnings: list[str], label: str, default):
    try:
        return call()
    except GithubGateError as exc:
        warnings.append(f"{label}: {exc}")
        return default
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"{label}: unexpected error: {exc}")
        return default


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


if __name__ == "__main__":
    raise SystemExit(main())
