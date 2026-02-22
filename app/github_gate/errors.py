from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class GithubGateError(Exception):
    code: str
    message: str
    upstream_status: Optional[int] = None
    context: Optional[str] = None

    def __str__(self) -> str:
        suffix = ""
        if self.upstream_status is not None:
            suffix += f" (status={self.upstream_status})"
        if self.context:
            suffix += f" [{self.context}]"
        return f"{self.code}: {self.message}{suffix}"


class InvalidGithubUrlError(GithubGateError):
    def __init__(self, message: str, context: Optional[str] = None) -> None:
        super().__init__(code="invalid_github_url", message=message, context=context)


class RepositoryInaccessibleError(GithubGateError):
    def __init__(self, message: str, upstream_status: Optional[int] = None, context: Optional[str] = None) -> None:
        super().__init__(
            code="repository_inaccessible",
            message=message,
            upstream_status=upstream_status,
            context=context,
        )


class GithubRateLimitError(GithubGateError):
    def __init__(self, message: str, upstream_status: Optional[int] = None, context: Optional[str] = None) -> None:
        super().__init__(
            code="github_rate_limited",
            message=message,
            upstream_status=upstream_status,
            context=context,
        )


class GithubUpstreamError(GithubGateError):
    def __init__(self, message: str, upstream_status: Optional[int] = None, context: Optional[str] = None) -> None:
        super().__init__(
            code="github_upstream_error",
            message=message,
            upstream_status=upstream_status,
            context=context,
        )


class GithubTimeoutError(GithubGateError):
    def __init__(self, message: str, context: Optional[str] = None) -> None:
        super().__init__(
            code="github_timeout",
            message=message,
            upstream_status=504,
            context=context,
        )


class GithubResponseShapeError(GithubGateError):
    def __init__(self, message: str, context: Optional[str] = None) -> None:
        super().__init__(
            code="github_response_shape_error",
            message=message,
            context=context,
        )
