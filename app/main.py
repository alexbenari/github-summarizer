from __future__ import annotations

import math
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from starlette.responses import JSONResponse

from app.config_validator import ConfigValidator
from app.github_gate.client import GithubGate
from app.github_gate.errors import (
    GithubRateLimitError,
    GithubResponseShapeError,
    GithubTimeoutError,
    GithubUpstreamError,
    InvalidGithubUrlError,
    RepositoryInaccessibleError,
)
from app.github_gate.markdown_renderer import render_full_extraction_markdown
from app.github_gate.models import RepoRef
from app.llm_gate import LlmGate
from app.llm_gate.errors import (
    LlmConfigError,
    LlmDigestParseError,
    LlmGateError,
    LlmOutputValidationError,
    LlmRateLimitError,
    LlmTimeoutError,
    LlmUpstreamError,
)
from app.repo_processor.errors import (
    RepoProcessorBudgetError,
    RepoProcessorConfigError,
    RepoProcessorOutputError,
    RepoProcessorParseError,
)
from app.repo_processor.models import RepoProcessorConfig
from app.repo_processor.parser import render_processed_markdown
from app.repo_processor.processor import process_markdown


class SummarizeRequest(BaseModel):
    github_url: str


@dataclass
class RequestDebugLog:
    request_id: str
    repo_name: str
    start_ms: float
    lines: list[str]

    def add(self, line: str) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        self.lines.append(f"{timestamp} {line}")

    def write(self) -> None:
        logs_dir = Path("logs")
        logs_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        filename = f"requested-{self.repo_name}-{ts}-{self.request_id}.log"
        (logs_dir / filename).write_text("\n".join(self.lines) + "\n", encoding="utf-8")


@asynccontextmanager
async def lifespan(_: FastAPI):
    ConfigValidator().validate_startup()
    yield


app = FastAPI(title="GitHub Summarizer API", version="0.1.0", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def request_validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return _error_response(400, "Invalid request body.")


@app.exception_handler(InvalidGithubUrlError)
async def invalid_url_handler(request: Request, exc: InvalidGithubUrlError) -> JSONResponse:
    return _error_response(400, exc.message)


@app.exception_handler(RepositoryInaccessibleError)
async def repo_inaccessible_handler(request: Request, exc: RepositoryInaccessibleError) -> JSONResponse:
    return _error_response(404, exc.message)


@app.exception_handler(GithubRateLimitError)
async def gh_rate_handler(request: Request, exc: GithubRateLimitError) -> JSONResponse:
    return _error_response(429, exc.message)


@app.exception_handler(GithubTimeoutError)
async def gh_timeout_handler(request: Request, exc: GithubTimeoutError) -> JSONResponse:
    return _error_response(504, exc.message)


@app.exception_handler(GithubResponseShapeError)
async def gh_shape_handler(request: Request, exc: GithubResponseShapeError) -> JSONResponse:
    return _error_response(502, exc.message)


@app.exception_handler(GithubUpstreamError)
async def gh_upstream_handler(request: Request, exc: GithubUpstreamError) -> JSONResponse:
    if exc.upstream_status == 429:
        return _error_response(429, exc.message)
    if exc.upstream_status == 504:
        return _error_response(504, exc.message)
    return _error_response(503, exc.message)


@app.exception_handler(RepoProcessorParseError)
async def rp_parse_handler(request: Request, exc: RepoProcessorParseError) -> JSONResponse:
    return _error_response(422, exc.message)


@app.exception_handler(RepoProcessorConfigError)
async def rp_cfg_handler(request: Request, exc: RepoProcessorConfigError) -> JSONResponse:
    return _error_response(500, exc.message)


@app.exception_handler(RepoProcessorOutputError)
async def rp_out_handler(request: Request, exc: RepoProcessorOutputError) -> JSONResponse:
    return _error_response(500, exc.message)


@app.exception_handler(LlmDigestParseError)
async def llm_digest_handler(request: Request, exc: LlmDigestParseError) -> JSONResponse:
    return _error_response(422, exc.message)


@app.exception_handler(LlmOutputValidationError)
async def llm_output_handler(request: Request, exc: LlmOutputValidationError) -> JSONResponse:
    return _error_response(502, exc.message)


@app.exception_handler(LlmRateLimitError)
async def llm_rate_handler(request: Request, exc: LlmRateLimitError) -> JSONResponse:
    return _error_response(429, exc.message)


@app.exception_handler(LlmTimeoutError)
async def llm_timeout_handler(request: Request, exc: LlmTimeoutError) -> JSONResponse:
    return _error_response(504, exc.message)


@app.exception_handler(LlmUpstreamError)
async def llm_upstream_handler(request: Request, exc: LlmUpstreamError) -> JSONResponse:
    if exc.upstream_status == 429:
        return _error_response(429, exc.message)
    if exc.upstream_status == 504:
        return _error_response(504, exc.message)
    return _error_response(503, exc.message)


@app.exception_handler(LlmConfigError)
async def llm_config_handler(request: Request, exc: LlmConfigError) -> JSONResponse:
    return _error_response(500, exc.message)


@app.exception_handler(Exception)
async def fallback_handler(request: Request, exc: Exception) -> JSONResponse:
    return _error_response(500, "Internal server error.")


@app.post("/summarize")
def summarize(payload: SummarizeRequest) -> JSONResponse:
    result = summarize_service(payload.github_url)
    return JSONResponse(status_code=200, content=result)


def summarize_service(github_url: str) -> dict[str, object]:
    start_ms = time.time() * 1000
    request_id = _make_request_id()
    repo_for_log = _repo_name_from_url(github_url)
    debug = RequestDebugLog(request_id=request_id, repo_name=repo_for_log, start_ms=start_ms, lines=[])
    debug.add("section=request_metadata")
    debug.add(f"request_start request_id={request_id} repo_url={github_url}")
    print(f"[service] request_start request_id={request_id} repo_url={github_url}")

    github_gate = GithubGate()
    llm_gate = LlmGate()
    status_code = 200
    try:
        repo = github_gate.parse_repo_url(github_url)
        repo_for_log = repo.repo
        debug.repo_name = repo.repo
        github_gate.verify_repo_access(repo)

        print(f"[service] github_fetch_start request_id={request_id}")
        debug.add("section=github_fetch")
        debug.add("github_fetch_start")
        fetch_started = time.time() * 1000
        results, selector_warnings = _fetch_all_entities(github_gate, repo, request_id=request_id, debug=debug)
        fetch_duration_ms = int((time.time() * 1000) - fetch_started)
        full_markdown = render_full_extraction_markdown(
            repo=repo,
            results=results,
            warnings=selector_warnings + github_gate.warnings,
        )
        full_bytes = len(full_markdown.encode("utf-8"))
        print(
            f"[service] github_fetch_done request_id={request_id} bytes={full_bytes} "
            f"warnings={len(selector_warnings) + len(github_gate.warnings)} "
            f"duration_ms={fetch_duration_ms}"
        )
        debug.add(
            f"github_fetch_done bytes={full_bytes} warnings={len(selector_warnings) + len(github_gate.warnings)} "
            f"duration_ms={fetch_duration_ms}"
        )
        for warn in selector_warnings + github_gate.warnings:
            debug.add(f"github_warning {warn}")

        print(f"[service] repo_process_start request_id={request_id}")
        debug.add("section=repo_processor")
        debug.add("repo_process_start")
        rp_cfg = RepoProcessorConfig.from_runtime_file()
        llm_input_markdown = full_markdown
        processed = None
        try:
            processed = process_markdown(full_markdown)
            llm_input_markdown = render_processed_markdown(processed)
            print(
                f"[service] repo_process_done request_id={request_id} "
                f"output_bytes={processed.output_total_utf8_bytes}"
            )
            debug.add(
                f"repo_process_done output_bytes={processed.output_total_utf8_bytes} "
                f"max_repo_data_bytes={processed.max_repo_data_size_for_prompt_bytes}"
            )
            truncation_notes = getattr(processed, "truncation_notes", []) or []
            for note in truncation_notes:
                print(f"[service] repo_process_truncation request_id={request_id} {note}")
                debug.add(f"repo_process_truncation {note}")
        except RepoProcessorBudgetError as exc:
            processed = exc.processed
            if processed is not None:
                llm_input_markdown = render_processed_markdown(processed)
                overflow_bytes = 0
                if isinstance(exc.context, dict):
                    overflow_bytes = int(exc.context.get("overflow_bytes", 0) or 0)
                print(
                    f"[service] repo_process_done request_id={request_id} "
                    f"output_bytes={processed.output_total_utf8_bytes} "
                    f"max_repo_data_bytes={processed.max_repo_data_size_for_prompt_bytes} "
                    f"overflow_bytes={overflow_bytes} fallback=processed_overflow"
                )
                debug.add(
                    f"repo_process_budget_warning fallback_processed_overflow "
                    f"reason={exc.message} "
                    f"output_bytes={processed.output_total_utf8_bytes} "
                    f"max_repo_data_bytes={processed.max_repo_data_size_for_prompt_bytes} "
                    f"overflow_bytes={overflow_bytes}"
                )
                truncation_notes = getattr(processed, "truncation_notes", []) or []
                for note in truncation_notes:
                    print(f"[service] repo_process_truncation request_id={request_id} {note}")
                    debug.add(f"repo_process_truncation {note}")
            else:
                print(f"[service] repo_process_done request_id={request_id} output_bytes={full_bytes} fallback=full_markdown")
                debug.add(f"repo_process_budget_warning fallback_full_markdown reason={exc.message}")

        max_repo_data_bytes = "unknown"
        if processed is not None:
            max_repo_data_bytes = getattr(processed, "max_repo_data_size_for_prompt_bytes", "unknown")
        llm_input_bytes = len(llm_input_markdown.encode("utf-8"))
        llm_input_estimated_tokens = _estimate_tokens_from_bytes(llm_input_bytes, rp_cfg.bytes_per_token_estimate)
        model_context_tokens = getattr(llm_gate.config, "model_context_window_tokens", None)
        coarse_bpt = float(getattr(rp_cfg, "bytes_per_token_estimate", 4.0) or 4.0)
        model_context_estimated_bytes = (
            int(model_context_tokens * coarse_bpt)
            if isinstance(model_context_tokens, int) and model_context_tokens > 0
            else "unknown"
        )
        print(
            f"[service] llm_input request_id={request_id} "
            f"bytes={llm_input_bytes} estimated_tokens_coarse={llm_input_estimated_tokens} "
            f"model_context_tokens={model_context_tokens if model_context_tokens is not None else 'unknown'} "
            f"model_context_estimated_bytes={model_context_estimated_bytes} "
            f"max_repo_data_bytes={max_repo_data_bytes}"
        )
        debug.add(
            f"llm_input bytes={llm_input_bytes} estimated_tokens_coarse={llm_input_estimated_tokens} "
            f"model_context_tokens={model_context_tokens if model_context_tokens is not None else 'unknown'} "
            f"model_context_estimated_bytes={model_context_estimated_bytes} "
            f"max_repo_data_bytes={max_repo_data_bytes}"
        )

        model_name = llm_gate.config.model_id
        print(f"[service] llm_start request_id={request_id} model={model_name}")
        debug.add("section=llm_call")
        debug.add(f"llm_start model={model_name}")
        try:
            llm_result = llm_gate.summarize(markdown_text=llm_input_markdown)
        except LlmUpstreamError as exc:
            overflow = _parse_context_window_overflow(exc)
            if overflow is None:
                raise
            max_tokens, request_tokens = overflow
            if request_tokens <= 0:
                raise
            current_ratio = rp_cfg.max_repo_data_ratio_in_prompt
            # Keep margin below hard limit and enforce at least a 10% ratio drop on retry.
            shrink_factor = (max_tokens * 0.90) / request_tokens
            target_ratio = current_ratio * shrink_factor
            target_ratio = min(target_ratio, current_ratio * 0.90)
            target_ratio = max(0.05, target_ratio)

            retry_cfg = replace(rp_cfg, max_repo_data_ratio_in_prompt=target_ratio)
            print(
                f"[service] llm_retry_context_overflow request_id={request_id} "
                f"provider_max_tokens={max_tokens} provider_input_tokens={request_tokens} "
                f"current_ratio={current_ratio:.4f} retry_ratio={target_ratio:.4f}"
            )
            debug.add(
                f"llm_retry_context_overflow provider_max_tokens={max_tokens} provider_input_tokens={request_tokens} "
                f"current_ratio={current_ratio:.4f} retry_ratio={target_ratio:.4f}"
            )

            retry_processed = None
            try:
                retry_processed = process_markdown(full_markdown, config=retry_cfg)
                llm_input_markdown = render_processed_markdown(retry_processed)
            except RepoProcessorBudgetError as retry_exc:
                retry_processed = retry_exc.processed
                if retry_processed is not None:
                    llm_input_markdown = render_processed_markdown(retry_processed)
                else:
                    llm_input_markdown = full_markdown

            retry_input_bytes = len(llm_input_markdown.encode("utf-8"))
            retry_input_tokens = _estimate_tokens_from_bytes(retry_input_bytes, retry_cfg.bytes_per_token_estimate)
            print(
                f"[service] llm_input_retry request_id={request_id} "
                f"bytes={retry_input_bytes} estimated_tokens_coarse={retry_input_tokens}"
            )
            debug.add(
                f"llm_input_retry bytes={retry_input_bytes} estimated_tokens_coarse={retry_input_tokens}"
            )
            llm_result = llm_gate.summarize(markdown_text=llm_input_markdown)
        print(f"[service] llm_done request_id={request_id}")
        debug.add("llm_done")

        return {
            "summary": llm_result.summary,
            "technologies": llm_result.technologies,
            "structure": llm_result.structure,
        }
    except InvalidGithubUrlError:
        status_code = 400
        raise
    except RepositoryInaccessibleError:
        status_code = 404
        raise
    except GithubRateLimitError:
        status_code = 429
        raise
    except GithubTimeoutError:
        status_code = 504
        raise
    except GithubResponseShapeError:
        status_code = 502
        raise
    except GithubUpstreamError as exc:
        status_code = 429 if exc.upstream_status == 429 else 504 if exc.upstream_status == 504 else 503
        raise
    except RepoProcessorParseError:
        status_code = 422
        raise
    except RepoProcessorConfigError:
        status_code = 500
        raise
    except RepoProcessorOutputError:
        status_code = 500
        raise
    except LlmDigestParseError as exc:
        status_code = 422
        _log_llm_exception(request_id, debug, exc)
        raise
    except LlmOutputValidationError as exc:
        status_code = 502
        _log_llm_exception(request_id, debug, exc)
        raise
    except LlmRateLimitError as exc:
        status_code = 429
        _log_llm_exception(request_id, debug, exc)
        raise
    except LlmTimeoutError as exc:
        status_code = 504
        _log_llm_exception(request_id, debug, exc)
        raise
    except LlmUpstreamError as exc:
        status_code = 429 if exc.upstream_status == 429 else 504 if exc.upstream_status == 504 else 503
        _log_llm_exception(request_id, debug, exc)
        raise
    except LlmConfigError as exc:
        status_code = 500
        _log_llm_exception(request_id, debug, exc)
        raise
    except Exception:
        status_code = 500
        raise
    finally:
        latency_ms = int((time.time() * 1000) - start_ms)
        print(f"[service] request_end request_id={request_id} status={status_code} latency_ms={latency_ms}")
        debug.add("section=final_status")
        debug.add(f"request_end status={status_code} latency_ms={latency_ms}")
        debug.write()


def _fetch_all_entities(
    github_gate: GithubGate,
    repo: RepoRef,
    request_id: str,
    debug: RequestDebugLog,
) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    results: dict[str, Any] = {}
    fetch_started_ms = time.time() * 1000
    max_total_fetch_ms = int(float(github_gate.limits.max_total_fetch_duration_seconds) * 1000)

    def _stage_start(name: str) -> float:
        start = time.time() * 1000
        print(f"[service] github_fetch_stage_start request_id={request_id} stage={name}")
        debug.add(f"github_fetch_stage_start stage={name}")
        return start

    def _stage_done(name: str, started_ms: float, extra: str = "") -> None:
        duration_ms = int((time.time() * 1000) - started_ms)
        suffix = f" {extra}" if extra else ""
        print(f"[service] github_fetch_stage_done request_id={request_id} stage={name} duration_ms={duration_ms}{suffix}")
        debug.add(f"github_fetch_stage_done stage={name} duration_ms={duration_ms}{suffix}")

    def _time_budget_exhausted(next_stage: str) -> bool:
        elapsed_ms = int((time.time() * 1000) - fetch_started_ms)
        if elapsed_ms < max_total_fetch_ms:
            return False
        warning = (
            f"{next_stage}: stop_reason=max_total_fetch_duration_reached "
            f"(elapsed_ms={elapsed_ms}, max_ms={max_total_fetch_ms})"
        )
        warnings.append(warning)
        print(
            f"[service] github_fetch_stage_skipped request_id={request_id} stage={next_stage} "
            f"stop_reason=max_total_fetch_duration_reached elapsed_ms={elapsed_ms} max_ms={max_total_fetch_ms}"
        )
        debug.add(
            f"github_fetch_stage_skipped stage={next_stage} "
            f"stop_reason=max_total_fetch_duration_reached elapsed_ms={elapsed_ms} max_ms={max_total_fetch_ms}"
        )
        return True

    metadata_start = _stage_start("metadata")
    metadata = github_gate.get_repo_metadata(repo)
    results["metadata"] = metadata
    _stage_done("metadata", metadata_start)

    tree_start = _stage_start("tree")
    tree = github_gate.get_tree(repo)
    results["tree"] = tree
    _stage_done("tree", tree_start, extra=f"entries={len(tree)}")

    languages_start = _stage_start("languages")
    results["languages"] = github_gate.get_languages(repo)
    _stage_done("languages", languages_start, extra=f"count={len(results['languages'])}")

    readme_start = _stage_start("readme")
    results["readme"] = github_gate.get_readme(repo)
    readme_bytes = 0
    if results["readme"] is not None:
        readme_bytes = int(getattr(results["readme"], "byte_size", 0) or 0)
    _stage_done("readme", readme_start, extra=f"bytes={readme_bytes}")

    docs_start = _stage_start("documentation")
    if _time_budget_exhausted("documentation"):
        results["documentation"] = None
    else:
        try:
            results["documentation"] = github_gate.get_documentation(tree=tree, metadata=metadata, limits=github_gate.limits)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"documentation selector failed: {exc}")
            results["documentation"] = None
    docs_files = 0
    docs_bytes = 0
    if results["documentation"] is not None:
        docs_files = len(getattr(results["documentation"], "files", []) or [])
        docs_bytes = int(getattr(results["documentation"], "total_bytes", 0) or 0)
    _stage_done("documentation", docs_start, extra=f"files={docs_files} bytes={docs_bytes}")

    build_start = _stage_start("build_package")
    if _time_budget_exhausted("build_package"):
        results["build_package"] = []
    else:
        try:
            results["build_package"] = github_gate.get_build_and_package_data(tree=tree, limits=github_gate.limits)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"build_package selector failed: {exc}")
            results["build_package"] = []
    build_files = len(results["build_package"])
    build_bytes = sum(int(getattr(item, "byte_size", 0) or 0) for item in results["build_package"])
    _stage_done("build_package", build_start, extra=f"files={build_files} bytes={build_bytes}")

    tests_start = _stage_start("tests")
    if _time_budget_exhausted("tests"):
        results["tests"] = []
    else:
        try:
            results["tests"] = github_gate.get_tests(tree=tree, limits=github_gate.limits)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"tests selector failed: {exc}")
            results["tests"] = []
    tests_files = len(results["tests"])
    tests_bytes = sum(int(getattr(item, "byte_size", 0) or 0) for item in results["tests"])
    _stage_done("tests", tests_start, extra=f"files={tests_files} bytes={tests_bytes}")

    code_start = _stage_start("code")
    if _time_budget_exhausted("code"):
        results["code"] = []
    else:
        try:
            results["code"] = github_gate.get_code(tree=tree, limits=github_gate.limits)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"code selector failed: {exc}")
            results["code"] = []
    code_files = len(results["code"])
    code_bytes = sum(int(getattr(item, "byte_size", 0) or 0) for item in results["code"])
    _stage_done("code", code_start, extra=f"files={code_files} bytes={code_bytes}")

    return results, warnings


def _error_response(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"status": "error", "message": message})


def _make_request_id() -> str:
    return uuid.uuid4().hex[:12]


def _repo_name_from_url(url: str) -> str:
    cleaned = (url or "").rstrip("/")
    parts = cleaned.split("/")
    if len(parts) >= 2:
        return parts[-1] or "unknown"
    return "unknown"


def _log_llm_exception(request_id: str, debug: RequestDebugLog, exc: LlmGateError) -> None:
    upstream_status = exc.upstream_status if exc.upstream_status is not None else "none"
    context = exc.context if exc.context is not None else "none"
    provider_extra = ""
    if isinstance(exc, LlmUpstreamError):
        parsed = _parse_context_window_overflow(exc)
        if parsed is not None:
            provider_max_tokens, provider_input_tokens = parsed
            provider_extra = (
                f" provider_max_tokens={provider_max_tokens} "
                f"provider_input_tokens={provider_input_tokens}"
            )
    print(
        f"[service] llm_error request_id={request_id} "
        f"code={exc.code} upstream_status={upstream_status} "
        f"message={exc.message} context={context}{provider_extra}"
    )
    debug.add(
        f"llm_error code={exc.code} upstream_status={upstream_status} "
        f"message={exc.message} context={context}{provider_extra}"
    )


def _parse_context_window_overflow(exc: LlmUpstreamError) -> tuple[int, int] | None:
    if exc.upstream_status != 400:
        return None
    context = str(exc.context or "")
    if not context:
        return None
    patterns = [
        r"maximum context length is\s+(\d+)\s+tokens.*?request has\s+(\d+)\s+input tokens",
        r"maximum context length is\s+(\d+).*?your request has\s+(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, context, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            continue
        max_tokens = int(match.group(1))
        request_tokens = int(match.group(2))
        return max_tokens, request_tokens
    return None


def _estimate_tokens_from_bytes(byte_count: int, bytes_per_token_estimate: float) -> int:
    if byte_count <= 0:
        return 0
    if bytes_per_token_estimate <= 0:
        return byte_count
    return int(math.ceil(byte_count / bytes_per_token_estimate))
