from __future__ import annotations

from math import ceil, floor


class ContextWindowLimitBookkeeper:
    def __init__(self, model_context_window_tokens: int, bytes_per_token_estimate: float = 4.0) -> None:
        self.model_context_window_tokens = int(model_context_window_tokens)
        self.bytes_per_token_estimate = float(bytes_per_token_estimate)

    def tokens_to_bytes(self, tokens: int) -> int:
        return int(floor(max(0, tokens) * self.bytes_per_token_estimate))

    def bytes_to_tokens(self, num_bytes: int) -> int:
        return int(ceil(max(0, num_bytes) / self.bytes_per_token_estimate))

    def max_repo_data_bytes(self, max_repo_data_ratio_in_prompt: float) -> int:
        return int(
            floor(
                self.model_context_window_tokens
                * float(max_repo_data_ratio_in_prompt)
                * self.bytes_per_token_estimate
            )
        )

    def remaining_bytes(self, current_repo_data_bytes: int, max_repo_data_ratio_in_prompt: float) -> int:
        return max(0, self.max_repo_data_bytes(max_repo_data_ratio_in_prompt) - int(current_repo_data_bytes))
