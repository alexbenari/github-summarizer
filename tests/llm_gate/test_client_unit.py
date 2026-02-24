import os
import time

import httpx

from app.llm_gate.client import LlmGate
from app.llm_gate.errors import (
    LlmDigestParseError,
    LlmOutputValidationError,
    LlmRateLimitError,
    LlmTimeoutError,
    LlmUpstreamError,
)
from app.llm_gate.models import LlmGateConfig


def _make_gate() -> LlmGate:
    config = LlmGateConfig(
        model_id="test-model",
        model_context_window_tokens=1024,
        connect_timeout_seconds=0.1,
        read_timeout_seconds=0.1,
        attempt_timeout_seconds=0.2,
        max_retries=0,
    )
    return LlmGate(config=config)


def test_call_with_retry_timeout_is_wall_clock_capped() -> None:
    gate = _make_gate()

    def slow_op():
        time.sleep(1.0)
        return {}

    start = time.time()
    try:
        gate._call_with_retry(slow_op, gate.config, "unit")
    except LlmTimeoutError:
        elapsed = time.time() - start
        assert elapsed < 0.6
        return
    raise AssertionError("Expected LlmTimeoutError.")


def test_call_with_retry_maps_429_to_rate_limit_error() -> None:
    gate = _make_gate()
    request = httpx.Request("POST", "https://example.com")
    response = httpx.Response(429, request=request)

    def op():
        raise httpx.HTTPStatusError("rate limited", request=request, response=response)

    try:
        gate._call_with_retry(op, gate.config, "unit")
    except LlmRateLimitError as exc:
        assert exc.upstream_status == 429
        return
    raise AssertionError("Expected LlmRateLimitError for HTTP 429.")


def test_call_with_retry_maps_503_to_upstream_error() -> None:
    gate = _make_gate()
    request = httpx.Request("POST", "https://example.com")
    response = httpx.Response(503, request=request)

    def op():
        raise httpx.HTTPStatusError("service unavailable", request=request, response=response)

    try:
        gate._call_with_retry(op, gate.config, "unit")
    except LlmUpstreamError as exc:
        assert exc.upstream_status == 503
        return
    raise AssertionError("Expected LlmUpstreamError for HTTP 503.")


def test_normalize_and_validate_rejects_non_string_fields() -> None:
    gate = _make_gate()
    invalid_payloads = [
        {"summary": 123, "technologies": ["Python"], "structure": "ok"},
        {"summary": "ok", "technologies": [123], "structure": "ok"},
        {"summary": "ok", "technologies": ["Python"], "structure": False},
    ]
    for payload in invalid_payloads:
        try:
            gate._normalize_and_validate(payload)
        except LlmOutputValidationError:
            continue
        raise AssertionError("Expected LlmOutputValidationError for invalid output payload types.")


def test_summarize_rejects_malformed_markdown() -> None:
    previous = os.environ.get("NEBIUS_API_KEY")
    os.environ["NEBIUS_API_KEY"] = "test"
    try:
        gate = _make_gate()
        try:
            gate.summarize("not a digest markdown")
        except LlmDigestParseError:
            return
        raise AssertionError("Expected LlmDigestParseError for malformed digest markdown.")
    finally:
        if previous is None:
            os.environ.pop("NEBIUS_API_KEY", None)
        else:
            os.environ["NEBIUS_API_KEY"] = previous
