from __future__ import annotations

import fnmatch
import json
import re
from pathlib import Path
from typing import Iterable

from .models import TreeEntry


TEXT_EXTENSIONS = {
    ".md",
    ".txt",
    ".rst",
    ".adoc",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".swift",
    ".rb",
    ".php",
    ".cs",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".sh",
    ".bash",
    ".zsh",
    ".ps1",
    ".sql",
    ".xml",
    ".html",
    ".css",
    ".scss",
    ".less",
    ".dockerfile",
    ".env",
}


ENTRYPOINT_NAMES = {
    "main",
    "app",
    "server",
    "cli",
    "__main__",
    "manage",
    "run",
}


class IgnoreRules:
    def __init__(
        self,
        ignored_directories: list[str],
        ignored_extensions: list[str],
        ignored_filenames: list[str],
        ignored_globs: list[str],
        ignored_path_contains: list[str],
    ) -> None:
        self.ignored_directories = {x.lower() for x in ignored_directories}
        self.ignored_extensions = {x.lower() for x in ignored_extensions}
        self.ignored_filenames = {x.lower() for x in ignored_filenames}
        self.ignored_globs = ignored_globs
        self.ignored_path_contains = [x.lower().replace("\\", "/") for x in ignored_path_contains]

    @classmethod
    def from_file(cls, path: str = "config/non-informative-files.json") -> "IgnoreRules":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            ignored_directories=list(data.get("ignored_directories", [])),
            ignored_extensions=list(data.get("ignored_extensions", [])),
            ignored_filenames=list(data.get("ignored_filenames", [])),
            ignored_globs=list(data.get("ignored_globs", [])),
            ignored_path_contains=list(data.get("ignored_path_contains", [])),
        )

    def should_ignore_path(self, path: str) -> bool:
        normalized = path.replace("\\", "/")
        lower_path = normalized.lower()
        filename = lower_path.split("/")[-1]
        extension = _suffix(filename)

        if filename in self.ignored_filenames:
            return True
        if extension in self.ignored_extensions:
            return True
        if any(fnmatch.fnmatch(filename, pattern.lower()) for pattern in self.ignored_globs):
            return True
        if any(token in lower_path for token in self.ignored_path_contains):
            return True

        segments = [segment.lower() for segment in normalized.split("/")[:-1]]
        return any(segment in self.ignored_directories for segment in segments)


def is_likely_text_path(path: str) -> bool:
    filename = path.split("/")[-1]
    if filename.lower() == "dockerfile":
        return True
    extension = _suffix(filename)
    if extension in TEXT_EXTENSIONS:
        return True
    # No extension often means executable script or config.
    return "." not in filename


def sorted_bfs(entries: Iterable[TreeEntry]) -> list[TreeEntry]:
    return sorted(entries, key=lambda e: (path_depth(e.path), e.path.lower()))


def looks_like_test_path(path: str) -> bool:
    lower = path.lower()
    filename = lower.split("/")[-1]
    if lower.startswith("tests/") or lower.startswith("test/"):
        return True
    return bool(re.match(r".*_test\.[^/]+$", filename) or re.match(r"test_.*\.[^/]+$", filename))


def looks_like_doc_path(path: str) -> bool:
    lower = path.lower()
    if lower.startswith("docs/") or lower.startswith("documentation/"):
        return True
    filename = lower.split("/")[-1]
    return filename.startswith("readme") or filename in {
        "contributing.md",
        "contributing.rst",
        "setup.md",
        "installation.md",
        "install.md",
    }


def looks_like_entrypoint(path: str) -> bool:
    filename = path.split("/")[-1]
    stem = filename.split(".")[0].lower()
    return stem in ENTRYPOINT_NAMES


def looks_like_build_package_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    lower = normalized.lower()
    filename = lower.split("/")[-1]

    exact_names = {
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "requirements.txt",
        "pipfile",
        "package.json",
        "tsconfig.json",
        "pnpm-workspace.yaml",
        "go.mod",
        "cargo.toml",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "composer.json",
        "gemfile",
        "makefile",
        "dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
        ".gitlab-ci.yml",
    }
    if filename in exact_names:
        return True

    if fnmatch.fnmatch(filename, "requirements-*.txt"):
        return True

    return False


def path_depth(path: str) -> int:
    return path.count("/")


def _suffix(filename: str) -> str:
    if "." not in filename:
        return ""
    return f".{filename.split('.')[-1].lower()}"
