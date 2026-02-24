from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class LlmGateError(Exception):
    code: str
    message: str
    upstream_status: Optional[int] = None
    context: Optional[Any] = None

    def __str__(self) -> str:
        suffix = ""
        if self.upstream_status is not None:
            suffix += f" (status={self.upstream_status})"
        if self.context is not None:
            suffix += f" [{self.context}]"
        return f"{self.code}: {self.message}{suffix}"


class LlmConfigError(LlmGateError):
    def __init__(self, message: str, context: Optional[Any] = None) -> None:
        super().__init__(code="llm_config_error", message=message, context=context)


class LlmDigestParseError(LlmGateError):
    def __init__(self, message: str, context: Optional[Any] = None) -> None:
        super().__init__(code="llm_digest_parse_error", message=message, context=context)


class LlmRateLimitError(LlmGateError):
    def __init__(self, message: str, upstream_status: Optional[int] = None, context: Optional[Any] = None) -> None:
        super().__init__(code="llm_rate_limit_error", message=message, upstream_status=upstream_status, context=context)


class LlmTimeoutError(LlmGateError):
    def __init__(self, message: str, context: Optional[Any] = None) -> None:
        super().__init__(code="llm_timeout_error", message=message, upstream_status=504, context=context)


class LlmUpstreamError(LlmGateError):
    def __init__(self, message: str, upstream_status: Optional[int] = None, context: Optional[Any] = None) -> None:
        super().__init__(code="llm_upstream_error", message=message, upstream_status=upstream_status, context=context)


class LlmOutputValidationError(LlmGateError):
    def __init__(self, message: str, context: Optional[Any] = None) -> None:
        super().__init__(code="llm_output_validation_error", message=message, context=context)
