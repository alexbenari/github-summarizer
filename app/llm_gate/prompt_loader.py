from __future__ import annotations

import json
import re
from pathlib import Path

from .errors import LlmConfigError
from .models import RepoDigest


def load_prompt_contract(template_path: str = "app/llm_gate/prompt.md") -> tuple[str, dict, str]:
    path = Path(template_path)
    if not path.exists():
        raise LlmConfigError("Prompt template file not found.", context=template_path)
    text = path.read_text(encoding="utf-8")

    system_prompt = _extract_fenced_block_after_heading(text, "## System Prompt")
    schema_raw = _extract_fenced_block_after_heading(text, "## JSON Schema")
    user_template = _extract_fenced_block_after_heading(text, "## User Prompt Template")

    try:
        schema = json.loads(schema_raw)
    except Exception as exc:  # noqa: BLE001
        raise LlmConfigError("Invalid JSON schema in prompt template.", context=str(exc)) from exc

    return system_prompt, schema, user_template


def render_user_prompt(digest: RepoDigest, template_path: str = "app/llm_gate/prompt.md") -> str:
    _, _, user_template = load_prompt_contract(template_path=template_path)
    return user_template.format(
        repo_metadata=digest.repository_metadata,
        language_stats=digest.language_stats,
        tree_summary=digest.tree_summary,
        readme_text=digest.readme_text,
        documentation_text=digest.documentation_text,
        build_package_text=digest.build_package_text,
        code_snippets=digest.code_snippets,
        test_snippets=digest.test_snippets,
    )


def _extract_fenced_block_after_heading(text: str, heading: str) -> str:
    heading_idx = text.find(heading)
    if heading_idx == -1:
        raise LlmConfigError("Prompt template is missing required heading.", context=heading)
    tail = text[heading_idx + len(heading) :]
    match = re.search(r"```(?:\w+)?\n([\s\S]*?)\n```", tail)
    if not match:
        raise LlmConfigError("Prompt template is missing fenced block.", context=heading)
    return match.group(1)
