from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .errors import LlmConfigError


@dataclass(frozen=True)
class RepoDigest:
    repository_metadata: str
    language_stats: str
    tree_summary: str
    readme_text: str
    documentation_text: str
    build_package_text: str
    test_snippets: str
    code_snippets: str


@dataclass(frozen=True)
class SummaryResult:
    summary: str
    technologies: list[str]
    structure: str


@dataclass(frozen=True)
class LlmRequestOptions:
    model_id: Optional[str] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_output_tokens: Optional[int] = None
    attempt_timeout_seconds: Optional[float] = None


@dataclass(frozen=True)
class LlmGateConfig:
    model_id: str
    model_context_window_tokens: int
    temperature: float = 0.1
    top_p: float = 1.0
    max_output_tokens: int = 2000
    connect_timeout_seconds: float = 2.0
    read_timeout_seconds: float = 45.0
    attempt_timeout_seconds: float = 50.0
    max_retries: int = 2
    retry_backoff_seconds: tuple[float, float] = (0.5, 1.0)
    base_url: str = "https://api.studio.nebius.ai/v1"

    @classmethod
    def from_runtime_file(cls, path: str | Path = "config/runtime.json") -> "LlmGateConfig":
        runtime_path = Path(path)
        if not runtime_path.exists():
            raise LlmConfigError("Runtime config file not found.", context=str(runtime_path))

        data = json.loads(runtime_path.read_text(encoding="utf-8"))
        section = data.get("llm_gate", {})
        model_id = section.get("model_id")
        context_window = section.get("model_context_window_tokens")
        if not model_id:
            raise LlmConfigError("Missing mandatory llm_gate.model_id in runtime config.")
        if context_window is None:
            raise LlmConfigError("Missing mandatory llm_gate.model_context_window_tokens in runtime config.")

        retry_values = section.get("retry_backoff_seconds", [0.5, 1.0])
        if not isinstance(retry_values, list) or len(retry_values) < 2:
            raise LlmConfigError("llm_gate.retry_backoff_seconds must be an array with at least 2 numbers.")

        cfg = cls(
            model_id=str(model_id),
            model_context_window_tokens=int(context_window),
            temperature=float(section.get("temperature", 0.1)),
            top_p=float(section.get("top_p", 1.0)),
            max_output_tokens=int(section.get("max_output_tokens", 2000)),
            connect_timeout_seconds=float(section.get("connect_timeout_seconds", 2.0)),
            read_timeout_seconds=float(section.get("read_timeout_seconds", 45.0)),
            attempt_timeout_seconds=float(section.get("attempt_timeout_seconds", 50.0)),
            max_retries=int(section.get("max_retries", 2)),
            retry_backoff_seconds=(float(retry_values[0]), float(retry_values[1])),
            base_url=str(section.get("base_url", "https://api.studio.nebius.ai/v1")),
        )
        cfg.validate()
        return cfg

    def with_env_overrides(self) -> "LlmGateConfig":
        model_id = os.getenv("NEBIUS_MODEL_ID", self.model_id)
        base_url = os.getenv("NEBIUS_BASE_URL", self.base_url)
        cfg = LlmGateConfig(
            model_id=model_id,
            model_context_window_tokens=self.model_context_window_tokens,
            temperature=self.temperature,
            top_p=self.top_p,
            max_output_tokens=self.max_output_tokens,
            connect_timeout_seconds=self.connect_timeout_seconds,
            read_timeout_seconds=self.read_timeout_seconds,
            attempt_timeout_seconds=self.attempt_timeout_seconds,
            max_retries=self.max_retries,
            retry_backoff_seconds=self.retry_backoff_seconds,
            base_url=base_url,
        )
        cfg.validate()
        return cfg

    def apply_options(self, options: Optional[LlmRequestOptions]) -> "LlmGateConfig":
        if options is None:
            return self
        cfg = LlmGateConfig(
            model_id=options.model_id or self.model_id,
            model_context_window_tokens=self.model_context_window_tokens,
            temperature=self.temperature if options.temperature is None else float(options.temperature),
            top_p=self.top_p if options.top_p is None else float(options.top_p),
            max_output_tokens=self.max_output_tokens
            if options.max_output_tokens is None
            else int(options.max_output_tokens),
            connect_timeout_seconds=self.connect_timeout_seconds,
            read_timeout_seconds=self.read_timeout_seconds,
            attempt_timeout_seconds=self.attempt_timeout_seconds
            if options.attempt_timeout_seconds is None
            else float(options.attempt_timeout_seconds),
            max_retries=self.max_retries,
            retry_backoff_seconds=self.retry_backoff_seconds,
            base_url=self.base_url,
        )
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if not self.model_id.strip():
            raise LlmConfigError("model_id must be non-empty.")
        if self.model_context_window_tokens <= 0:
            raise LlmConfigError("model_context_window_tokens must be > 0.")
        if self.max_output_tokens <= 0:
            raise LlmConfigError("max_output_tokens must be > 0.")
        if self.connect_timeout_seconds <= 0 or self.read_timeout_seconds <= 0 or self.attempt_timeout_seconds <= 0:
            raise LlmConfigError("Timeout values must be > 0.")
        if self.max_retries < 0:
            raise LlmConfigError("max_retries must be >= 0.")
        if self.retry_backoff_seconds[0] < 0 or self.retry_backoff_seconds[1] < 0:
            raise LlmConfigError("retry_backoff_seconds values must be >= 0.")
