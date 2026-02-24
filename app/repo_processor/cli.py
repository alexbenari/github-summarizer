from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .errors import RepoProcessorError
from .models import RepoProcessorConfig
from .parser import render_processed_markdown
from .processor import process_markdown


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Process github-gate markdown into prompt-ready markdown.")
    parser.add_argument("--input", required=True, help="Path to full extraction markdown.")
    parser.add_argument("--output", required=False, default=None, help="Output markdown path.")
    parser.add_argument("--max-repo-data-ratio-in-prompt", type=float, default=None)
    parser.add_argument("--bytes-per-token-estimate", type=float, default=None)
    parser.add_argument("--documentation-weight", type=float, default=None)
    parser.add_argument("--tests-weight", type=float, default=None)
    parser.add_argument("--build-package-weight", type=float, default=None)
    parser.add_argument("--code-weight", type=float, default=None)
    parser.add_argument("--model-context-window-tokens", type=int, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        input_path = Path(args.input).expanduser().resolve()
        if not input_path.exists():
            raise RepoProcessorError("repo_processor_cli_error", "Input file does not exist.", str(input_path))
        output_path = _resolve_output_path(input_path=input_path, raw_output=args.output)

        markdown_text = input_path.read_text(encoding="utf-8")
        config = _build_config_from_args(args)
        processed = process_markdown(markdown_text, config=config)
        rendered = render_processed_markdown(processed)
        output_path.write_text(rendered, encoding="utf-8")
        print(f"Wrote processed markdown to {output_path}")
        print(
            "Processor stats: "
            f"input_bytes={processed.input_total_utf8_bytes}, "
            f"output_bytes={processed.output_total_utf8_bytes}, "
            f"max_repo_data_bytes={processed.max_repo_data_size_for_prompt_bytes}, "
            f"input_tokens={processed.estimated_input_tokens}, "
            f"output_tokens={processed.estimated_output_tokens}"
        )
        return 0
    except RepoProcessorError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"repo_processor_cli_error: {exc}", file=sys.stderr)
        return 1


def _resolve_output_path(input_path: Path, raw_output: str | None) -> Path:
    if raw_output and raw_output.strip():
        return Path(raw_output).expanduser().resolve()
    return input_path.with_name(f"{input_path.stem}-for-llm.md")


def _build_config_from_args(args: argparse.Namespace) -> RepoProcessorConfig:
    base = RepoProcessorConfig.from_runtime_file()
    cfg = RepoProcessorConfig(
        model_context_window_tokens=args.model_context_window_tokens or base.model_context_window_tokens,
        max_repo_data_ratio_in_prompt=(
            args.max_repo_data_ratio_in_prompt
            if args.max_repo_data_ratio_in_prompt is not None
            else base.max_repo_data_ratio_in_prompt
        ),
        bytes_per_token_estimate=(
            args.bytes_per_token_estimate
            if args.bytes_per_token_estimate is not None
            else base.bytes_per_token_estimate
        ),
        documentation_weight=(
            args.documentation_weight if args.documentation_weight is not None else base.documentation_weight
        ),
        tests_weight=args.tests_weight if args.tests_weight is not None else base.tests_weight,
        build_package_weight=(
            args.build_package_weight if args.build_package_weight is not None else base.build_package_weight
        ),
        code_weight=args.code_weight if args.code_weight is not None else base.code_weight,
    )
    cfg.validate()
    return cfg


if __name__ == "__main__":
    raise SystemExit(main())
