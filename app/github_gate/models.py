from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class RepoRef:
    owner: str
    repo: str


@dataclass(frozen=True)
class RepoMetadata:
    owner: str
    repo: str
    default_branch: str
    description: str
    topics: list[str]
    homepage: str


@dataclass(frozen=True)
class TreeEntry:
    path: str
    type: str
    size: int
    api_url: str
    download_url: str


@dataclass(frozen=True)
class ReadmeData:
    source_url: str
    content_text: str
    byte_size: int

    @property
    def estimated_tokens(self) -> int:
        return ceil(self.byte_size / 4)


@dataclass(frozen=True)
class FileContent:
    path: str
    source_url: str
    content_text: str
    byte_size: int

    @property
    def estimated_tokens(self) -> int:
        return ceil(self.byte_size / 4)


@dataclass(frozen=True)
class DocumentationData:
    source_url: str
    content_text: str
    files: list[FileContent]
    total_bytes: int

    @property
    def estimated_tokens(self) -> int:
        return ceil(self.total_bytes / 4)


@dataclass(frozen=True)
class RepoSnapshot:
    owner: str
    repo: str
    default_branch: str
    description: str
    topics: list[str]
    homepage: str
    languages: dict[str, int]
    tree_entries: list[TreeEntry]
    readme: Optional[ReadmeData] = None
    documentation: Optional[DocumentationData] = None
    build_and_package_files: list[FileContent] = field(default_factory=list)


@dataclass(frozen=True)
class GithubGateLimits:
    max_docs_total_bytes: int = 250_000
    max_tests_total_bytes: int = 250_000
    max_code_total_bytes: int = 400_000
    max_build_package_total_bytes: int = 200_000
    max_single_file_bytes: int = 100_000
    max_build_package_files: int = 80
    max_code_files: int = 120
    max_build_package_depth: int = 2
    max_code_depth: int = 4
    max_build_package_duration_seconds: float = 30.0
    max_code_duration_seconds: float = 45.0
    max_total_fetch_duration_seconds: float = 120.0

    @classmethod
    def from_runtime_file(cls, path: str | Path = "config/runtime.json") -> "GithubGateLimits":
        import json

        runtime_path = Path(path)
        if not runtime_path.exists():
            return cls()

        data = json.loads(runtime_path.read_text(encoding="utf-8"))
        section = data.get("github_gate", {})
        return cls(
            max_docs_total_bytes=int(section.get("max_docs_total_bytes", cls.max_docs_total_bytes)),
            max_tests_total_bytes=int(section.get("max_tests_total_bytes", cls.max_tests_total_bytes)),
            max_code_total_bytes=int(section.get("max_code_total_bytes", cls.max_code_total_bytes)),
            max_build_package_total_bytes=int(
                section.get("max_build_package_total_bytes", cls.max_build_package_total_bytes)
            ),
            max_single_file_bytes=int(section.get("max_single_file_bytes", cls.max_single_file_bytes)),
            max_build_package_files=int(section.get("max_build_package_files", cls.max_build_package_files)),
            max_code_files=int(section.get("max_code_files", cls.max_code_files)),
            max_build_package_depth=int(section.get("max_build_package_depth", cls.max_build_package_depth)),
            max_code_depth=int(section.get("max_code_depth", cls.max_code_depth)),
            max_build_package_duration_seconds=float(
                section.get("max_build_package_duration_seconds", cls.max_build_package_duration_seconds)
            ),
            max_code_duration_seconds=float(section.get("max_code_duration_seconds", cls.max_code_duration_seconds)),
            max_total_fetch_duration_seconds=float(
                section.get("max_total_fetch_duration_seconds", cls.max_total_fetch_duration_seconds)
            ),
        )
