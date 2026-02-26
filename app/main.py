from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
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
        results, selector_warnings = _fetch_all_entities(github_gate, repo)
        full_markdown = render_full_extraction_markdown(
            repo=repo,
            results=results,
            warnings=selector_warnings + github_gate.warnings,
        )
        full_bytes = len(full_markdown.encode("utf-8"))
        print(
            f"[service] github_fetch_done request_id={request_id} bytes={full_bytes} "
            f"warnings={len(selector_warnings) + len(github_gate.warnings)}"
        )
        debug.add(f"github_fetch_done bytes={full_bytes} warnings={len(selector_warnings) + len(github_gate.warnings)}")
        for warn in selector_warnings + github_gate.warnings:
            debug.add(f"github_warning {warn}")

        print(f"[service] repo_process_start request_id={request_id}")
        debug.add("section=repo_processor")
        debug.add("repo_process_start")
        llm_input_markdown = full_markdown
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
        except RepoProcessorBudgetError as exc:
            print(f"[service] repo_process_done request_id={request_id} output_bytes={full_bytes} fallback=full_markdown")
            debug.add(f"repo_process_budget_warning fallback_full_markdown reason={exc.message}")

        model_name = llm_gate.config.model_id
        print(f"[service] llm_start request_id={request_id} model={model_name}")
        debug.add("section=llm_call")
        debug.add(f"llm_start model={model_name}")
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
    except LlmDigestParseError:
        status_code = 422
        raise
    except LlmOutputValidationError:
        status_code = 502
        raise
    except LlmRateLimitError:
        status_code = 429
        raise
    except LlmTimeoutError:
        status_code = 504
        raise
    except LlmUpstreamError as exc:
        status_code = 429 if exc.upstream_status == 429 else 504 if exc.upstream_status == 504 else 503
        raise
    except LlmConfigError:
        status_code = 500
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


def _fetch_all_entities(github_gate: GithubGate, repo: RepoRef) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    results: dict[str, Any] = {}

    metadata = github_gate.get_repo_metadata(repo)
    results["metadata"] = metadata
    tree = github_gate.get_tree(repo)
    results["tree"] = tree
    results["languages"] = github_gate.get_languages(repo)
    results["readme"] = github_gate.get_readme(repo)

    try:
        results["documentation"] = github_gate.get_documentation(tree=tree, metadata=metadata, limits=github_gate.limits)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"documentation selector failed: {exc}")
        results["documentation"] = None

    try:
        results["build_package"] = github_gate.get_build_and_package_data(tree=tree, limits=github_gate.limits)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"build_package selector failed: {exc}")
        results["build_package"] = []

    try:
        results["tests"] = github_gate.get_tests(tree=tree, limits=github_gate.limits)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"tests selector failed: {exc}")
        results["tests"] = []

    try:
        results["code"] = github_gate.get_code(tree=tree, limits=github_gate.limits)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"code selector failed: {exc}")
        results["code"] = []

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
