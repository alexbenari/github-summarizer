from __future__ import annotations

import os

from app.github_gate.models import GithubGateLimits
from app.llm_gate.models import LlmGateConfig
from app.repo_processor.models import RepoProcessorConfig


class ConfigValidator:
    def validate_startup(self) -> None:
        llm_cfg = LlmGateConfig.from_runtime_file().with_env_overrides()
        llm_cfg.validate()

        rp_cfg = RepoProcessorConfig.from_runtime_file()
        rp_cfg.validate()

        gh_limits = GithubGateLimits.from_runtime_file()
        self._validate_limits(gh_limits)

        api_key = os.getenv("NEBIUS_API_KEY", "").strip()
        if not api_key:
            raise ValueError("NEBIUS_API_KEY is required and must be non-empty.")

    def _validate_limits(self, limits: GithubGateLimits) -> None:
        int_values = {
            "max_docs_total_bytes": limits.max_docs_total_bytes,
            "max_tests_total_bytes": limits.max_tests_total_bytes,
            "max_code_total_bytes": limits.max_code_total_bytes,
            "max_build_package_total_bytes": limits.max_build_package_total_bytes,
            "max_single_file_bytes": limits.max_single_file_bytes,
            "max_build_package_files": limits.max_build_package_files,
            "max_code_files": limits.max_code_files,
            "max_build_package_depth": limits.max_build_package_depth,
            "max_code_depth": limits.max_code_depth,
        }
        for key, value in int_values.items():
            if int(value) <= 0:
                raise ValueError(f"{key} must be a positive integer.")

        float_values = {
            "max_build_package_duration_seconds": limits.max_build_package_duration_seconds,
            "max_code_duration_seconds": limits.max_code_duration_seconds,
            "max_total_fetch_duration_seconds": limits.max_total_fetch_duration_seconds,
        }
        for key, value in float_values.items():
            if float(value) <= 0:
                raise ValueError(f"{key} must be a positive number.")
