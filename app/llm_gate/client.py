from __future__ import annotations

import json
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any, Callable, Optional

import httpx

from .errors import (
    LlmConfigError,
    LlmOutputValidationError,
    LlmRateLimitError,
    LlmTimeoutError,
    LlmUpstreamError,
)
from .markdown_parser import parse_repo_digest_markdown
from .models import LlmGateConfig, LlmRequestOptions, SummaryResult
from .prompt_loader import load_prompt_contract, render_user_prompt

RETRYABLE_STATUSES = {429, 502, 503, 504}
NON_RETRYABLE_STATUSES = {400, 401, 403, 404}


class LlmGate:
    def __init__(self, config: Optional[LlmGateConfig] = None) -> None:
        self.config = (config or LlmGateConfig.from_runtime_file()).with_env_overrides()

    def summarize(self, markdown_text: str, options: LlmRequestOptions | None = None) -> SummaryResult:
        api_key = os.getenv("NEBIUS_API_KEY", "").strip()
        if not api_key:
            raise LlmConfigError("NEBIUS_API_KEY is required.")

        effective = self.config.apply_options(options)
        digest = parse_repo_digest_markdown(markdown_text)
        system_prompt, schema, _ = load_prompt_contract()
        user_prompt = render_user_prompt(digest=digest)

        payload = {
            "model": effective.model_id,
            "temperature": effective.temperature,
            "top_p": effective.top_p,
            "max_tokens": effective.max_output_tokens,
            "stream": False,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "repo_summary",
                    "schema": schema,
                    "strict": True,
                },
            },
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        completion = self._call_with_retry(
            op=lambda: self._post_chat_completions(effective=effective, api_key=api_key, payload=payload),
            cfg=effective,
            context="chat_completions",
        )
        parsed = self._extract_output_json(completion)
        normalized = self._normalize_and_validate(parsed)
        return SummaryResult(
            summary=normalized["summary"],
            technologies=normalized["technologies"],
            structure=normalized["structure"],
        )

    def _call_with_retry(self, op: Callable[[], dict[str, Any]], cfg: LlmGateConfig, context: str) -> dict[str, Any]:
        attempts = cfg.max_retries + 1
        last_exc: Optional[Exception] = None
        for attempt in range(1, attempts + 1):
            executor = ThreadPoolExecutor(max_workers=1)
            future = executor.submit(op)
            try:
                result = future.result(timeout=cfg.attempt_timeout_seconds)
                executor.shutdown(wait=False, cancel_futures=True)
                return result
            except FuturesTimeout:
                future.cancel()
                executor.shutdown(wait=False, cancel_futures=True)
                last_exc = LlmTimeoutError("LLM request timed out.", context=context)
                should_retry = attempt < attempts
            except Exception as exc:  # noqa: BLE001
                executor.shutdown(wait=False, cancel_futures=True)
                status = _extract_status(exc)
                if status == 429:
                    last_exc = LlmRateLimitError("LLM rate limit reached.", upstream_status=status, context=context)
                    should_retry = attempt < attempts
                elif status in {502, 503, 504}:
                    last_exc = LlmUpstreamError(
                        "Retryable LLM upstream failure.",
                        upstream_status=status,
                        context=context,
                    )
                    should_retry = attempt < attempts
                elif status in NON_RETRYABLE_STATUSES:
                    raise LlmUpstreamError("LLM upstream non-retryable failure.", upstream_status=status) from exc
                elif isinstance(exc, (httpx.TimeoutException, httpx.NetworkError, OSError)):
                    last_exc = LlmUpstreamError(
                        "Network failure while calling LLM.",
                        context=f"{context}: {exc}",
                    )
                    should_retry = attempt < attempts
                elif isinstance(exc, LlmOutputValidationError):
                    raise
                elif isinstance(exc, LlmConfigError):
                    raise
                else:
                    raise LlmUpstreamError(
                        "Unexpected LLM adapter error.",
                        context=f"{context}: {exc}",
                    ) from exc

            if should_retry:
                backoff_idx = min(attempt - 1, len(cfg.retry_backoff_seconds) - 1)
                time.sleep(cfg.retry_backoff_seconds[backoff_idx] + random.uniform(0.0, 0.15))

        if last_exc:
            raise last_exc
        raise LlmUpstreamError("LLM call failed for unknown reason.")

    def _post_chat_completions(
        self,
        effective: LlmGateConfig,
        api_key: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        url = effective.base_url.rstrip("/") + "/chat/completions"
        timeout = httpx.Timeout(
            timeout=None,
            connect=effective.connect_timeout_seconds,
            read=effective.read_timeout_seconds,
            write=effective.read_timeout_seconds,
            pool=effective.connect_timeout_seconds,
        )
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                url,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    def _extract_output_json(self, completion: dict[str, Any]) -> dict[str, Any]:
        try:
            choices = completion["choices"]
            first = choices[0]
            message = first["message"]
            content = message["content"]
        except Exception as exc:  # noqa: BLE001
            raise LlmOutputValidationError("Malformed completion response shape.", context=str(exc)) from exc

        if isinstance(content, str):
            try:
                return json.loads(content)
            except Exception as exc:  # noqa: BLE001
                raise LlmOutputValidationError("Model response is not valid JSON.", context=str(exc)) from exc

        if isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "output_text":
                    text_parts.append(str(part.get("text", "")))
                elif isinstance(part, dict) and "text" in part:
                    text_parts.append(str(part["text"]))
            merged = "".join(text_parts).strip()
            try:
                return json.loads(merged)
            except Exception as exc:  # noqa: BLE001
                raise LlmOutputValidationError("Model content blocks are not valid JSON.", context=str(exc)) from exc

        raise LlmOutputValidationError("Unsupported model content format.")

    def _normalize_and_validate(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise LlmOutputValidationError("Output payload must be a JSON object.")
        expected_keys = {"summary", "technologies", "structure"}
        if set(payload.keys()) != expected_keys:
            raise LlmOutputValidationError("Output must contain exactly summary/technologies/structure keys.")

        summary_raw = payload.get("summary")
        structure_raw = payload.get("structure")
        technologies_raw = payload.get("technologies")
        if not isinstance(summary_raw, str) or not isinstance(structure_raw, str):
            raise LlmOutputValidationError("summary and structure must be strings.")
        summary = summary_raw.strip()
        structure = structure_raw.strip()
        if not summary or not structure:
            raise LlmOutputValidationError("summary and structure must be non-empty strings.")
        if not isinstance(technologies_raw, list):
            raise LlmOutputValidationError("technologies must be an array.")

        seen: set[str] = set()
        normalized_techs: list[str] = []
        for item in technologies_raw:
            if not isinstance(item, str):
                raise LlmOutputValidationError("technologies must contain only strings.")
            text = item.strip()
            if not text:
                continue
            if len(text) > 80:
                text = text[:80].rstrip()
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            normalized_techs.append(text)
        if len(normalized_techs) > 20:
            normalized_techs = normalized_techs[:20]
        return {
            "summary": summary,
            "technologies": normalized_techs,
            "structure": structure,
        }


def _extract_status(exc: Exception) -> Optional[int]:
    if isinstance(exc, httpx.HTTPStatusError):
        return int(exc.response.status_code)
    for attr in ("status", "status_code", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    if response is not None:
        for attr in ("status", "status_code"):
            value = getattr(response, attr, None)
            if isinstance(value, int):
                return value
    return None


def summarize(markdown_text: str, options: LlmRequestOptions | None = None) -> SummaryResult:
    return LlmGate().summarize(markdown_text=markdown_text, options=options)
