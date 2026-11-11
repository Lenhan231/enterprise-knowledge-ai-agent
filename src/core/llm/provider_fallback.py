"""Retryable provider fallback shared by report and SQL generation."""

import logging
import os

from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

from core.llm.huggingface_provider import HuggingFaceProvider
from core.llm.llm_interface import EmptyLLMResponseError

logger = logging.getLogger(__name__)


_RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
_huggingface_fallback_disabled = False


def accumulate_token_usage(total: dict | None, provider) -> dict | None:
    """Add the provider's latest usage to a request-local token total."""
    usage = getattr(provider, "last_usage", None)
    if not isinstance(usage, dict):
        return total
    values = {key: usage.get(key) for key in ("input_tokens", "output_tokens", "total_tokens")}
    if not any(isinstance(value, int) for value in values.values()):
        return total
    result = dict(total or {})
    for key, value in values.items():
        if isinstance(value, int):
            result[key] = result.get(key, 0) + value
    return result


def sum_token_usage(*usages: dict | None) -> dict | None:
    total = None
    for usage in usages:
        if not isinstance(usage, dict):
            continue
        values = {key: usage.get(key) for key in ("input_tokens", "output_tokens", "total_tokens")}
        if not any(isinstance(value, int) for value in values.values()):
            continue
        total = dict(total or {})
        for key, value in values.items():
            if isinstance(value, int):
                total[key] = total.get(key, 0) + value
    return total


def is_retryable_provider_error(error: Exception) -> bool:
    """Return true only for transient provider failures, never auth or request errors."""
    if isinstance(error, (APIConnectionError, APITimeoutError, RateLimitError, EmptyLLMResponseError)):
        return True
    return isinstance(error, APIStatusError) and error.status_code in _RETRYABLE_STATUS_CODES


def generate_with_provider_fallback(llm, prompt: str, *, instructions: str | None = None) -> tuple[str, str]:
    global _huggingface_fallback_disabled
    kwargs = {"instructions": instructions} if instructions is not None else {}
    try:
        return llm.generate(prompt, **kwargs).strip(), "groq"
    except Exception as primary_error:
        if not is_retryable_provider_error(primary_error):
            raise
        response = getattr(primary_error, "response", None)
        headers = getattr(response, "headers", {})
        logger.warning(
            "Primary LLM request failed (status=%s, error_type=%s, retry_after=%s, "
            "request_limit=%s, remaining_requests=%s, reset_requests=%s, "
            "token_limit=%s, remaining_tokens=%s, reset_tokens=%s)",
            getattr(primary_error, "status_code", None), type(primary_error).__name__,
            headers.get("retry-after"), headers.get("x-ratelimit-limit-requests"),
            headers.get("x-ratelimit-remaining-requests"), headers.get("x-ratelimit-reset-requests"),
            headers.get("x-ratelimit-limit-tokens"), headers.get("x-ratelimit-remaining-tokens"),
            headers.get("x-ratelimit-reset-tokens"),
        )
        if (os.getenv("HUGGINGFACE_LLM_FALLBACK", "false").casefold() != "true"
                or not os.getenv("HUGGINGFACE_API_KEY")):
            raise
        if _huggingface_fallback_disabled:
            logger.info("Skipping Hugging Face fallback after it returned HTTP 402; restart after credits change")
            raise

        fallback = None
        try:
            fallback = HuggingFaceProvider()
            answer = fallback.generate(prompt, **kwargs).strip()
            llm.last_usage = getattr(fallback, "last_usage", None)
            return answer, "huggingface_inference"
        except Exception as fallback_error:
            if getattr(fallback_error, "status_code", None) == 402:
                _huggingface_fallback_disabled = True
            logger.warning(
                "Hugging Face fallback failed after retryable Groq error (status=%s, error_type=%s)",
                getattr(fallback_error, "status_code", None), type(fallback_error).__name__,
            )
            raise primary_error from fallback_error
        finally:
            if fallback is not None:
                fallback.close()
