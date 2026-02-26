from __future__ import annotations

import base64
import random
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from dataclasses import asdict
from math import ceil
from typing import Any, Callable, Optional
from urllib import error as urlerror
from urllib import request as urlrequest
from urllib.parse import urlparse

from ghapi.all import GhApi

from .errors import (
    GithubRateLimitError,
    GithubResponseShapeError,
    GithubTimeoutError,
    GithubUpstreamError,
    InvalidGithubUrlError,
    RepositoryInaccessibleError,
)
from .models import (
    DocumentationData,
    FileContent,
    GithubGateLimits,
    ReadmeData,
    RepoMetadata,
    RepoRef,
    RepoSnapshot,
    TreeEntry,
)
from .selectors import (
    IgnoreRules,
    is_likely_text_path,
    looks_like_build_package_path,
    looks_like_doc_path,
    looks_like_entrypoint,
    looks_like_test_path,
    path_depth,
    sorted_bfs,
)


RETRYABLE_STATUSES = {429, 502, 503, 504}
NON_RETRYABLE_STATUSES = {400, 401, 403, 404}


class GithubGate:
    def __init__(self, limits: Optional[GithubGateLimits] = None, ignore_rules: Optional[IgnoreRules] = None) -> None:
        self.limits = limits or GithubGateLimits.from_runtime_file()
        self.ignore_rules = ignore_rules or IgnoreRules.from_file()
        self.connect_timeout_seconds = 2.0
        self.read_timeout_seconds = 8.0
        self.attempt_timeout_seconds = 10.0
        self.max_retries = 2
        self.retry_backoff_seconds = [0.5, 1.0]
        self.warnings: list[str] = []
        self._metadata_cache: dict[tuple[str, str], RepoMetadata] = {}

    def parse_repo_url(self, github_url: str) -> RepoRef:
        raw = (github_url or "").strip()
        if not raw:
            raise InvalidGithubUrlError("GitHub URL is required.")

        parsed = urlparse(raw)
        if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
            raise InvalidGithubUrlError("Only https://github.com/{owner}/{repo} URLs are supported.", context=raw)

        path_parts = [part for part in parsed.path.split("/") if part]
        if len(path_parts) < 2:
            raise InvalidGithubUrlError("URL must include owner and repository.", context=raw)
        if len(path_parts) > 2:
            raise InvalidGithubUrlError("Only repository root URLs are supported in v1.", context=raw)

        owner = path_parts[0].strip()
        repo = path_parts[1].strip()
        if not owner or not repo:
            raise InvalidGithubUrlError("URL must include non-empty owner and repository.", context=raw)
        return RepoRef(owner=owner, repo=repo)

    def verify_repo_access(self, repo: RepoRef) -> None:
        def _op() -> Any:
            api = self._new_api()
            return api.repos.get(owner=repo.owner, repo=repo.repo)

        response = self._run_with_retry(_op, context=f"verify_repo_access:{repo.owner}/{repo.repo}")
        if not isinstance(response, dict):
            response = dict(response)
        private = bool(response.get("private", False))
        if private:
            raise RepositoryInaccessibleError(
                message="Repository is not publicly accessible in unauthenticated mode.",
                upstream_status=403,
                context=f"{repo.owner}/{repo.repo}",
            )

    def get_repo_metadata(self, repo: RepoRef) -> RepoMetadata:
        key = (repo.owner, repo.repo)
        if key in self._metadata_cache:
            return self._metadata_cache[key]

        def _op() -> Any:
            api = self._new_api()
            return api.repos.get(owner=repo.owner, repo=repo.repo)

        response = self._run_with_retry(_op, context=f"get_repo_metadata:{repo.owner}/{repo.repo}")
        payload = dict(response)
        try:
            metadata = RepoMetadata(
                owner=str(payload["owner"]["login"]),
                repo=str(payload["name"]),
                default_branch=str(payload["default_branch"]),
                description=str(payload.get("description") or ""),
                topics=[str(item) for item in payload.get("topics", [])],
                homepage=str(payload.get("homepage") or ""),
            )
        except Exception as exc:
            raise GithubResponseShapeError("Unexpected metadata response shape.", context=str(exc)) from exc

        self._metadata_cache[key] = metadata
        return metadata

    def get_languages(self, repo: RepoRef) -> dict[str, int]:
        def _op() -> Any:
            api = self._new_api()
            return api.repos.list_languages(owner=repo.owner, repo=repo.repo)

        response = self._run_with_retry(_op, context=f"get_languages:{repo.owner}/{repo.repo}")
        payload = dict(response)
        return {str(key): int(value) for key, value in payload.items()}

    def get_tree(self, repo: RepoRef) -> list[TreeEntry]:
        metadata = self.get_repo_metadata(repo)

        def _op() -> Any:
            api = self._new_api()
            return api.git.get_tree(
                owner=repo.owner,
                repo=repo.repo,
                tree_sha=metadata.default_branch,
                recursive="1",
            )

        response = self._run_with_retry(_op, context=f"get_tree:{repo.owner}/{repo.repo}")
        items = self._extract_tree_items(response)

        entries: list[TreeEntry] = []
        for item in items:
            row = self._to_mapping(item)
            path = str(row.get("path") or "")
            entry_type = str(row.get("type") or "")
            if not path or entry_type not in {"blob", "tree"}:
                continue
            size_value = int(row.get("size") or 0)
            api_url = str(row.get("url") or "")
            download_url = ""
            if entry_type == "blob":
                download_url = (
                    f"https://raw.githubusercontent.com/"
                    f"{repo.owner}/{repo.repo}/{metadata.default_branch}/{path}"
                )
            entries.append(
                TreeEntry(
                    path=path,
                    type=entry_type,
                    size=size_value,
                    api_url=api_url,
                    download_url=download_url,
                )
            )

        return sorted_bfs(entries)

    def get_readme(self, repo: RepoRef) -> Optional[ReadmeData]:
        def _op() -> Any:
            api = self._new_api()
            return api.repos.get_readme(owner=repo.owner, repo=repo.repo)

        try:
            response = self._run_with_retry(_op, context=f"get_readme:{repo.owner}/{repo.repo}")
        except RepositoryInaccessibleError as exc:
            if exc.upstream_status == 404:
                return None
            raise
        except GithubUpstreamError as exc:
            if exc.upstream_status == 404:
                return None
            raise

        payload = dict(response)
        encoded = payload.get("content")
        if not isinstance(encoded, str):
            raise GithubResponseShapeError("README response missing content.")
        content_text = self._decode_github_base64(encoded)
        byte_size = len(content_text.encode("utf-8"))
        source_url = str(payload.get("html_url") or payload.get("download_url") or "")
        return ReadmeData(source_url=source_url, content_text=content_text, byte_size=byte_size)

    def get_file_content(self, repo: RepoRef, path: str) -> FileContent:
        metadata = self.get_repo_metadata(repo)

        def _op() -> Any:
            api = self._new_api()
            return api.repos.get_content(
                owner=repo.owner,
                repo=repo.repo,
                path=path,
                ref=metadata.default_branch,
            )

        response = self._run_with_retry(_op, context=f"get_file_content:{repo.owner}/{repo.repo}:{path}")
        if isinstance(response, list):
            raise GithubResponseShapeError("Expected file content response, got directory listing.", context=path)
        payload = dict(response)
        encoded = payload.get("content")
        if not isinstance(encoded, str):
            raise GithubResponseShapeError("File response missing content.", context=path)
        content_text = self._decode_github_base64(encoded)
        byte_size = len(content_text.encode("utf-8"))
        source_url = str(payload.get("html_url") or payload.get("download_url") or "")
        return FileContent(path=path, source_url=source_url, content_text=content_text, byte_size=byte_size)

    def get_documentation(
        self,
        tree: list[TreeEntry],
        metadata: RepoMetadata,
        limits: GithubGateLimits,
    ) -> Optional[DocumentationData]:
        selected_files: list[FileContent] = []
        used_bytes = 0
        tree_map = {entry.path: entry for entry in tree if entry.type == "blob"}

        homepage_url = (metadata.homepage or "").strip()
        if homepage_url:
            try:
                homepage_file = self._download_external_page(homepage_url=homepage_url)
                homepage_budget = max(0, limits.max_docs_total_bytes - used_bytes)
                allowed_bytes = min(limits.max_single_file_bytes, homepage_budget)
                if allowed_bytes <= 0:
                    self.warnings.append(
                        f"Skipped homepage documentation page: no remaining docs byte budget ({homepage_url})."
                    )
                else:
                    homepage_file, was_truncated = self._truncate_file_to_max_bytes(homepage_file, allowed_bytes)
                    if homepage_file.byte_size <= 0:
                        self.warnings.append(
                            f"Skipped homepage documentation page: empty after truncation ({homepage_url})."
                        )
                    else:
                        if was_truncated:
                            self.warnings.append(
                                "Trimmed homepage documentation page from end to fit limits "
                                f"({homepage_url}, kept={homepage_file.byte_size} bytes)."
                            )
                        selected_files.append(homepage_file)
                        used_bytes += homepage_file.byte_size
            except Exception as exc:
                self.warnings.append(f"Failed to fetch homepage documentation page ({homepage_url}): {exc}")

        doc_candidates = [
            entry
            for entry in tree
            if entry.type == "blob"
            and looks_like_doc_path(entry.path)
            and not self.ignore_rules.should_ignore_path(entry.path)
            and is_likely_text_path(entry.path)
        ]
        ordered_paths = [entry.path for entry in sorted_bfs(doc_candidates)]
        remaining_limit = max(0, limits.max_docs_total_bytes - used_bytes)
        docs_from_tree = self._collect_files_from_tree_paths(
            tree_map=tree_map,
            ordered_paths=ordered_paths,
            total_limit=remaining_limit,
            single_limit=limits.max_single_file_bytes,
        )
        files = selected_files + docs_from_tree
        if not files:
            return None
        total_bytes = sum(item.byte_size for item in files)
        merged = "\n\n".join(item.content_text for item in files)
        return DocumentationData(
            source_url=files[0].source_url if files else "",
            content_text=merged,
            files=files,
            total_bytes=total_bytes,
        )

    def get_tests(self, tree: list[TreeEntry], limits: GithubGateLimits) -> list[FileContent]:
        candidates = [
            entry
            for entry in tree
            if entry.type == "blob"
            and looks_like_test_path(entry.path)
            and not self.ignore_rules.should_ignore_path(entry.path)
            and is_likely_text_path(entry.path)
        ]
        ordered = sorted_bfs(candidates)
        tree_map = {entry.path: entry for entry in ordered}
        return self._collect_files_from_tree_paths(
            tree_map=tree_map,
            ordered_paths=[entry.path for entry in ordered],
            total_limit=limits.max_tests_total_bytes,
            single_limit=limits.max_single_file_bytes,
            category="tests",
        )

    def get_code(self, tree: list[TreeEntry], limits: GithubGateLimits) -> list[FileContent]:
        candidates = [
            entry
            for entry in tree
            if entry.type == "blob"
            and not looks_like_test_path(entry.path)
            and not looks_like_doc_path(entry.path)
            and not self.ignore_rules.should_ignore_path(entry.path)
            and is_likely_text_path(entry.path)
            and path_depth(entry.path) <= limits.max_code_depth
        ]
        bfs = sorted_bfs(candidates)
        seed = [entry for entry in bfs if looks_like_entrypoint(entry.path)]
        seed_paths = {entry.path for entry in seed}
        ordered_paths = [entry.path for entry in seed] + [entry.path for entry in bfs if entry.path not in seed_paths]
        tree_map = {entry.path: entry for entry in bfs}
        return self._collect_files_from_tree_paths(
            tree_map=tree_map,
            ordered_paths=ordered_paths,
            total_limit=limits.max_code_total_bytes,
            single_limit=limits.max_single_file_bytes,
            max_files=limits.max_code_files,
            max_duration_seconds=limits.max_code_duration_seconds,
            category="code",
        )

    def get_build_and_package_data(self, tree: list[TreeEntry], limits: GithubGateLimits) -> list[FileContent]:
        high_signal_names = {
            "pyproject.toml",
            "requirements.txt",
            "setup.py",
            "setup.cfg",
            "package.json",
            "go.mod",
            "cargo.toml",
            "pom.xml",
            "build.gradle",
            "build.gradle.kts",
            "dockerfile",
            "docker-compose.yml",
            "docker-compose.yaml",
            ".gitlab-ci.yml",
        }

        def _keep_build_path(path: str) -> bool:
            depth = path_depth(path)
            if depth > limits.max_build_package_depth:
                return False
            filename = path.split("/")[-1].lower()
            # Keep Makefile only at root or one level down to avoid huge monorepo fan-out.
            if filename == "makefile" and depth > 1:
                return False
            return True

        candidates = [
            entry
            for entry in tree
            if entry.type == "blob"
            and looks_like_build_package_path(entry.path)
            and not self.ignore_rules.should_ignore_path(entry.path)
            and is_likely_text_path(entry.path)
            and _keep_build_path(entry.path)
        ]
        ordered = sorted(
            candidates,
            key=lambda entry: (
                path_depth(entry.path),
                0 if entry.path.split("/")[-1].lower() in high_signal_names else 1,
                entry.path.lower(),
            ),
        )
        tree_map = {entry.path: entry for entry in ordered}
        return self._collect_files_from_tree_paths(
            tree_map=tree_map,
            ordered_paths=[entry.path for entry in ordered],
            total_limit=limits.max_build_package_total_bytes,
            single_limit=limits.max_single_file_bytes,
            max_files=limits.max_build_package_files,
            max_duration_seconds=limits.max_build_package_duration_seconds,
            category="build_package",
        )

    def build_snapshot(
        self,
        repo: RepoRef,
        include_documentation: bool = False,
        include_build_and_package: bool = False,
    ) -> RepoSnapshot:
        metadata = self.get_repo_metadata(repo)
        languages = self.get_languages(repo)
        tree = self.get_tree(repo)
        readme = self.get_readme(repo)
        documentation = None
        build_and_package_files: list[FileContent] = []
        if include_documentation:
            documentation = self.get_documentation(tree=tree, metadata=metadata, limits=self.limits)
        if include_build_and_package:
            build_and_package_files = self.get_build_and_package_data(tree=tree, limits=self.limits)

        return RepoSnapshot(
            owner=metadata.owner,
            repo=metadata.repo,
            default_branch=metadata.default_branch,
            description=metadata.description,
            topics=metadata.topics,
            homepage=metadata.homepage,
            languages=languages,
            tree_entries=tree,
            readme=readme,
            documentation=documentation,
            build_and_package_files=build_and_package_files,
        )

    def to_plain_dict(self, snapshot: RepoSnapshot) -> dict[str, Any]:
        return asdict(snapshot)

    def _collect_files_from_tree_paths(
        self,
        tree_map: dict[str, TreeEntry],
        ordered_paths: list[str],
        total_limit: int,
        single_limit: int,
        max_files: Optional[int] = None,
        max_duration_seconds: Optional[float] = None,
        category: str = "selector",
    ) -> list[FileContent]:
        selected: list[FileContent] = []
        used = 0
        started_ms = time.time() * 1000
        for path in ordered_paths:
            if path not in tree_map:
                continue
            if used >= total_limit:
                break
            if max_files is not None and len(selected) >= max_files:
                self.warnings.append(f"{category}: stop_reason=max_files_reached ({max_files})")
                break
            if max_duration_seconds is not None:
                elapsed_seconds = (time.time() * 1000 - started_ms) / 1000.0
                if elapsed_seconds >= max_duration_seconds:
                    self.warnings.append(
                        f"{category}: stop_reason=max_duration_reached ({max_duration_seconds}s)"
                    )
                    break
            entry = tree_map[path]
            if not entry.download_url:
                continue
            if entry.size and entry.size > single_limit:
                self.warnings.append(f"Skipped {path}: exceeds max_single_file_bytes.")
                continue
            if entry.size and used + entry.size > total_limit:
                continue

            try:
                item = self._download_tree_file(path=entry.path, download_url=entry.download_url)
            except Exception as exc:
                self.warnings.append(f"Failed to fetch {path}: {exc}")
                continue

            if item.byte_size > single_limit:
                self.warnings.append(f"Skipped {path}: downloaded content exceeds max_single_file_bytes.")
                continue
            if used + item.byte_size > total_limit:
                continue
            selected.append(item)
            used += item.byte_size
        return selected

    def _download_tree_file(self, path: str, download_url: str) -> FileContent:
        body_bytes = self._run_with_retry(
            op=lambda: self._http_get_bytes(download_url),
            context=f"download:{path}",
        )
        if b"\x00" in body_bytes:
            raise GithubResponseShapeError("Likely binary content.")
        try:
            text = body_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise GithubResponseShapeError("Unable to decode file as UTF-8.", context=str(exc)) from exc
        byte_size = len(text.encode("utf-8"))
        return FileContent(path=path, source_url=download_url, content_text=text, byte_size=byte_size)

    def _download_external_page(self, homepage_url: str) -> FileContent:
        parsed = urlparse(homepage_url)
        if parsed.scheme not in {"http", "https"}:
            raise GithubResponseShapeError("Homepage URL must be http(s).", context=homepage_url)
        body_bytes = self._run_with_retry(
            op=lambda: self._http_get_bytes(homepage_url),
            context=f"download_homepage:{homepage_url}",
        )
        if b"\x00" in body_bytes:
            raise GithubResponseShapeError("Homepage appears to be binary.", context=homepage_url)
        try:
            content_text = body_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise GithubResponseShapeError("Unable to decode homepage as UTF-8.", context=str(exc)) from exc
        byte_size = len(content_text.encode("utf-8"))
        return FileContent(
            path="about-homepage",
            source_url=homepage_url,
            content_text=content_text,
            byte_size=byte_size,
        )

    def _truncate_file_to_max_bytes(self, item: FileContent, max_bytes: int) -> tuple[FileContent, bool]:
        if max_bytes <= 0:
            return FileContent(path=item.path, source_url=item.source_url, content_text="", byte_size=0), True
        if item.byte_size <= max_bytes:
            return item, False
        truncated_text = self._truncate_utf8_prefix(item.content_text, max_bytes)
        truncated_bytes = len(truncated_text.encode("utf-8"))
        return (
            FileContent(
                path=item.path,
                source_url=item.source_url,
                content_text=truncated_text,
                byte_size=truncated_bytes,
            ),
            True,
        )

    def _new_api(self) -> GhApi:
        return GhApi(timeout=(self.connect_timeout_seconds, self.read_timeout_seconds))

    def _run_with_retry(self, op: Callable[[], Any], context: str) -> Any:
        attempts = self.max_retries + 1
        last_exc: Optional[Exception] = None

        for attempt in range(1, attempts + 1):
            try:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(op)
                    return future.result(timeout=self.attempt_timeout_seconds)
            except FuturesTimeout as exc:
                last_exc = GithubTimeoutError("GitHub request timed out.", context=context)
                should_retry = attempt < attempts
            except Exception as exc:  # noqa: BLE001
                status = self._extract_status(exc)
                if status == 404:
                    raise RepositoryInaccessibleError(
                        message="Repository is not accessible.",
                        upstream_status=404,
                        context=context,
                    ) from exc
                if status == 403 and self._is_rate_limit_signal(exc):
                    mapped_exc = GithubRateLimitError(
                        message="GitHub rate limit reached.",
                        upstream_status=403,
                        context=context,
                    )
                    last_exc = mapped_exc
                    should_retry = attempt < attempts
                elif status in RETRYABLE_STATUSES:
                    mapped_exc = GithubUpstreamError(
                        message="Retryable GitHub upstream failure.",
                        upstream_status=status,
                        context=context,
                    )
                    last_exc = mapped_exc
                    should_retry = attempt < attempts
                elif status in NON_RETRYABLE_STATUSES:
                    if status == 403:
                        raise RepositoryInaccessibleError(
                            message="Repository is not accessible in unauthenticated mode.",
                            upstream_status=403,
                            context=context,
                        ) from exc
                    raise GithubUpstreamError(
                        message="Non-retryable GitHub failure.",
                        upstream_status=status,
                        context=context,
                    ) from exc
                elif isinstance(exc, (urlerror.URLError, OSError)):
                    last_exc = GithubUpstreamError("Network failure while talking to GitHub.", context=context)
                    should_retry = attempt < attempts
                elif isinstance(exc, GithubGateExceptionTypes()):
                    raise
                else:
                    raise GithubUpstreamError(
                        message="Unexpected GitHub client error.",
                        context=f"{context}: {exc}",
                    ) from exc

            if should_retry:
                sleep_seconds = self._retry_sleep(attempt)
                time.sleep(sleep_seconds)

        if last_exc is not None:
            raise last_exc
        raise GithubUpstreamError("Unknown GitHub adapter failure.", context=context)

    def _retry_sleep(self, attempt: int) -> float:
        index = min(attempt - 1, len(self.retry_backoff_seconds) - 1)
        base = self.retry_backoff_seconds[index]
        jitter = random.uniform(0.0, 0.15)
        return base + jitter

    def _extract_status(self, exc: Exception) -> Optional[int]:
        if isinstance(exc, urlerror.HTTPError):
            return int(exc.code)
        for attr in ("status", "code", "status_code"):
            value = getattr(exc, attr, None)
            if isinstance(value, int):
                return value
        response = getattr(exc, "response", None)
        if response is not None:
            for attr in ("status_code", "status"):
                value = getattr(response, attr, None)
                if isinstance(value, int):
                    return value
        return None

    def _is_rate_limit_signal(self, exc: Exception) -> bool:
        text = str(exc).lower()
        return "rate limit" in text or "secondary rate limit" in text

    def _decode_github_base64(self, content: str) -> str:
        compact = content.replace("\n", "")
        try:
            decoded_bytes = base64.b64decode(compact)
            return decoded_bytes.decode("utf-8")
        except Exception as exc:
            raise GithubResponseShapeError("Unable to decode GitHub content payload.", context=str(exc)) from exc

    def _http_get_bytes(self, url: str) -> bytes:
        req = urlrequest.Request(url=url, method="GET")
        with urlrequest.urlopen(req, timeout=self.read_timeout_seconds) as response:
            return response.read()

    def _truncate_utf8_prefix(self, text: str, max_bytes: int) -> str:
        if max_bytes <= 0:
            return ""
        encoded = text.encode("utf-8")
        if len(encoded) <= max_bytes:
            return text
        return encoded[:max_bytes].decode("utf-8", errors="ignore")

    def _to_mapping(self, obj: Any) -> dict[str, Any]:
        if isinstance(obj, dict):
            return obj
        if hasattr(obj, "items"):
            try:
                return {str(k): v for k, v in obj.items()}  # type: ignore[call-arg]
            except Exception:
                pass
        if hasattr(obj, "__dict__"):
            return dict(vars(obj))
        raise GithubResponseShapeError("Unable to convert response item to mapping.")

    def _extract_tree_items(self, response: Any) -> list[Any]:
        if isinstance(response, list):
            return list(response)

        candidates: list[Any] = []

        try:
            payload = self._to_mapping(response)
            candidates.append(payload.get("tree"))
            candidates.append(payload.get("items"))
            candidates.append(payload.get("data"))
        except GithubResponseShapeError:
            payload = None

        for attr_name in ("tree", "items", "data"):
            if hasattr(response, attr_name):
                candidates.append(getattr(response, attr_name))

        if payload and isinstance(payload.get("data"), dict):
            data_map = payload["data"]
            candidates.append(data_map.get("tree"))
            candidates.append(data_map.get("items"))
        elif payload and payload.get("data") is not None:
            data_obj = payload.get("data")
            for attr_name in ("tree", "items"):
                if hasattr(data_obj, attr_name):
                    candidates.append(getattr(data_obj, attr_name))

        for candidate in candidates:
            if candidate is None:
                continue
            if isinstance(candidate, list):
                return candidate
            if isinstance(candidate, tuple):
                return list(candidate)
            if hasattr(candidate, "__iter__") and not isinstance(candidate, (str, bytes, dict)):
                try:
                    return list(candidate)
                except Exception:
                    pass

        shape = type(response).__name__
        raise GithubResponseShapeError(
            "Unexpected tree response shape.",
            context=f"type={shape}",
        )


def GithubGateExceptionTypes() -> tuple[type[Exception], ...]:
    return (
        InvalidGithubUrlError,
        RepositoryInaccessibleError,
        GithubRateLimitError,
        GithubUpstreamError,
        GithubTimeoutError,
        GithubResponseShapeError,
    )


def estimated_tokens_for_bytes(byte_count: int) -> int:
    return ceil(byte_count / 4)
