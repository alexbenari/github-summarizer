from __future__ import annotations

import json
from dataclasses import dataclass, field
from math import ceil
from pathlib import Path
from typing import Optional

from .errors import RepoProcessorConfigError


@dataclass(frozen=True)
class RepoProcessorConfig:
    model_context_window_tokens: int
    max_repo_data_ratio_in_prompt: float = 0.65
    bytes_per_token_estimate: float = 4.0
    documentation_weight: float = 0.40
    tests_weight: float = 0.20
    build_package_weight: float = 0.20
    code_weight: float = 0.20

    @classmethod
    def from_runtime_file(cls, path: str | Path = "config/runtime.json") -> "RepoProcessorConfig":
        runtime_path = Path(path)
        if not runtime_path.exists():
            raise RepoProcessorConfigError("Runtime config file not found.", context=str(runtime_path))

        data = json.loads(runtime_path.read_text(encoding="utf-8"))
        llm_gate = data.get("llm_gate", {})
        repo_proc = data.get("repo_processor", {})
        model_tokens = llm_gate.get("model_context_window_tokens")
        if model_tokens is None:
            raise RepoProcessorConfigError("Missing llm_gate.model_context_window_tokens in runtime config.")

        config = cls(
            model_context_window_tokens=int(model_tokens),
            max_repo_data_ratio_in_prompt=float(repo_proc.get("max_repo_data_ratio_in_prompt", 0.65)),
            bytes_per_token_estimate=float(repo_proc.get("bytes_per_token_estimate", 4.0)),
            documentation_weight=float(repo_proc.get("documentation_weight", 0.40)),
            tests_weight=float(repo_proc.get("tests_weight", 0.20)),
            build_package_weight=float(repo_proc.get("build_package_weight", 0.20)),
            code_weight=float(repo_proc.get("code_weight", 0.20)),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if self.model_context_window_tokens <= 0:
            raise RepoProcessorConfigError("model_context_window_tokens must be positive.")
        if not (0.0 < self.max_repo_data_ratio_in_prompt < 1.0):
            raise RepoProcessorConfigError("max_repo_data_ratio_in_prompt must be in (0,1).")
        if self.bytes_per_token_estimate <= 0:
            raise RepoProcessorConfigError("bytes_per_token_estimate must be > 0.")

        weights = {
            "documentation_weight": self.documentation_weight,
            "tests_weight": self.tests_weight,
            "build_package_weight": self.build_package_weight,
            "code_weight": self.code_weight,
        }
        if any(value < 0 for value in weights.values()):
            raise RepoProcessorConfigError("All category weights must be non-negative.", context=weights)
        if all(value == 0 for value in weights.values()):
            raise RepoProcessorConfigError("At least one category weight must be > 0.", context=weights)

    def weight_map(self) -> dict[str, float]:
        return {
            "documentation": self.documentation_weight,
            "tests": self.tests_weight,
            "build_and_package_data": self.build_package_weight,
            "code": self.code_weight,
        }


@dataclass(frozen=True)
class ExtractedRepoMarkdown:
    repository_metadata: Optional[str]
    language_stats: Optional[str]
    directory_tree: Optional[str]
    readme: Optional[str]
    documentation: Optional[str]
    build_and_package_data: Optional[str]
    tests: Optional[str]
    code: Optional[str]
    extraction_stats: Optional[str] = None
    warnings: Optional[str] = None


@dataclass(frozen=True)
class ProcessedRepoMarkdown:
    repository_metadata: str
    language_stats: str
    directory_tree: str
    readme: str
    documentation: str
    build_and_package_data: str
    tests: str
    code: str
    input_total_utf8_bytes: int
    output_total_utf8_bytes: int
    max_repo_data_size_for_prompt_bytes: int
    estimated_input_tokens: int
    estimated_output_tokens: int
    bytes_per_token_estimate: float
    per_category_bytes: dict[str, int]
    truncation_notes: list[str] = field(default_factory=list)

    @property
    def per_category_tokens(self) -> dict[str, int]:
        return {
            key: int(ceil(value / self.bytes_per_token_estimate))
            for key, value in self.per_category_bytes.items()
        }
