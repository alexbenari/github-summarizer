from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from .client import GithubGate
from .entities import ALL_ENTITIES, ALL_ENTITIES_SET
from .errors import GithubGateError
from .markdown_renderer import render_extraction_markdown
from .models import GithubGateLimits, RepoRef

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


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manual github-gate extraction runner.")
    parser.add_argument("--github-url", required=True, help="Repository URL.")
    parser.add_argument(
        "--entities",
        required=True,
        help=f"Comma-separated subset of {','.join(ALL_ENTITIES)} or all",
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
    markdown = render_extraction_markdown(repo=repo, requested=requested, results=results, warnings=warnings)
    output_path = _resolve_output_path(repo=repo, raw_output=args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    print(f"Wrote extraction output to {output_path}")
    return 0


def _parse_entities(raw: str) -> set[str]:
    cleaned = raw.strip().lower()
    if cleaned == "all":
        return set(ALL_ENTITIES_SET)
    parsed = {item.strip() for item in cleaned.split(",") if item.strip()}
    invalid = parsed - ALL_ENTITIES_SET
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


if __name__ == "__main__":
    raise SystemExit(main())
