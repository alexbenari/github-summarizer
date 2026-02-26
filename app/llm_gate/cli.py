from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from .client import LlmGate
from .errors import LlmGateError
from .markdown_parser import parse_repo_digest_markdown
from .models import LlmRequestOptions
from .prompt_loader import load_prompt_contract, render_user_prompt


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run llm-gate on processed repository markdown.")
    parser.add_argument("--input", required=True, help="Digest markdown file path.")
    parser.add_argument(
        "--output",
        required=False,
        default=None,
        help="Output file or directory path. Default: outputs/llm-result-[repo]-[model].json",
    )
    parser.add_argument("--model-id", default=None)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--max-output-tokens", type=int, default=None)
    parser.add_argument("--timeout-seconds", type=float, default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    input_path = Path(args.input).expanduser().resolve()
    output_arg_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else (Path.cwd() / "outputs").resolve()
    )
    try:
        _log(f"reading repo digest: {input_path}")
        markdown_text = input_path.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        print(f"llm_cli_error: failed to read input file [{exc}]", file=sys.stderr)
        return 1

    if args.dry_run:
        try:
            digest = parse_repo_digest_markdown(markdown_text)
            system_prompt, schema, _ = load_prompt_contract()
            user_prompt = render_user_prompt(digest=digest)
        except LlmGateError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        payload_preview = {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "repo_summary", "schema": schema, "strict": True},
            },
        }
        print(json.dumps(payload_preview, indent=2, ensure_ascii=True))
        return 0

    try:
        gate = LlmGate()
        digest = parse_repo_digest_markdown(markdown_text)
        options = LlmRequestOptions(
            model_id=args.model_id,
            temperature=args.temperature,
            max_output_tokens=args.max_output_tokens,
            attempt_timeout_seconds=args.timeout_seconds,
        )
        effective_model_id = options.model_id or gate.config.model_id
        _log(f"calling llm: {effective_model_id}")
        result = gate.summarize(markdown_text=markdown_text, options=options)
        repo_name = _extract_repo_name(digest.repository_metadata)
        output_path = _build_output_path(
            base_path=output_arg_path,
            repo_name=repo_name,
            model_id=effective_model_id,
        )
        output_payload = {
            "summary": result.summary,
            "technologies": result.technologies,
            "structure": result.structure,
        }
        _log(f"the output from the llm: {json.dumps(output_payload, ensure_ascii=True)}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(output_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return 0
    except LlmGateError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"llm_cli_error: {exc}", file=sys.stderr)
        return 1


def _log(message: str) -> None:
    print(f"[llm-gate-cli] {message}")


def _extract_repo_name(repository_metadata: str) -> str:
    match = re.search(r"(?mi)^-+\s*Repo:\s*(.+?)\s*$", repository_metadata or "")
    if match:
        return _sanitize_filename_token(match.group(1))
    return "unknown-repo"


def _build_output_path(base_path: Path, repo_name: str, model_id: str) -> Path:
    parent = base_path if base_path.is_dir() else base_path.parent
    safe_model = _sanitize_filename_token(model_id)
    filename = f"llm-result-{repo_name}-{safe_model}.json"
    return parent / filename


def _sanitize_filename_token(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-._")
    return cleaned or "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
