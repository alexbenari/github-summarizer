from __future__ import annotations

import argparse
import json
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
    parser.add_argument("--output", required=True, help="Output JSON path.")
    parser.add_argument("--model-id", default=None)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--max-output-tokens", type=int, default=None)
    parser.add_argument("--timeout-seconds", type=float, default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    try:
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
        options = LlmRequestOptions(
            model_id=args.model_id,
            temperature=args.temperature,
            max_output_tokens=args.max_output_tokens,
            attempt_timeout_seconds=args.timeout_seconds,
        )
        result = gate.summarize(markdown_text=markdown_text, options=options)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(
                {
                    "summary": result.summary,
                    "technologies": result.technologies,
                    "structure": result.structure,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return 0
    except LlmGateError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"llm_cli_error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
