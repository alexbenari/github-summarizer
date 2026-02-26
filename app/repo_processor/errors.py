from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from .models import ProcessedRepoMarkdown


@dataclass
class RepoProcessorError(Exception):
    code: str
    message: str
    context: Optional[Any] = None

    def __str__(self) -> str:
        if self.context is None:
            return f"{self.code}: {self.message}"
        return f"{self.code}: {self.message} [{self.context}]"


class RepoProcessorConfigError(RepoProcessorError):
    def __init__(self, message: str, context: Optional[Any] = None) -> None:
        super().__init__("repo_processor_config_error", message, context)


class RepoProcessorParseError(RepoProcessorError):
    def __init__(self, message: str, context: Optional[Any] = None) -> None:
        super().__init__("repo_processor_parse_error", message, context)


class RepoProcessorBudgetError(RepoProcessorError):
    def __init__(
        self,
        message: str,
        context: Optional[Any] = None,
        processed: Optional["ProcessedRepoMarkdown"] = None,
    ) -> None:
        super().__init__("repo_processor_budget_error", message, context)
        self.processed = processed


class RepoProcessorOutputError(RepoProcessorError):
    def __init__(self, message: str, context: Optional[Any] = None) -> None:
        super().__init__("repo_processor_output_error", message, context)
