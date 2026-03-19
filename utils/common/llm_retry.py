"""Chunk-level LLM retry with exponential backoff.

Wraps ``llm_tools.llm_call()`` to transparently retry on transient errors
such as HTTP 429 (rate-limit), timeouts, and 5xx server failures.

Configuration is read from ``global_config.yaml`` under the ``llm`` section:

.. code-block:: yaml

   llm:
     chunk_retry_max: 3          # max retry attempts per chunk (0 = disable)
     chunk_retry_backoff_sec: 5  # initial backoff in seconds (doubles each retry)

Usage
-----
All CARE agents (LLM, Patch, Fixer, Chat) import and use
``llm_call_with_retry`` instead of calling ``llm_tools.llm_call()`` directly.

.. code-block:: python

   from utils.common.llm_retry import llm_call_with_retry

   response = llm_call_with_retry(
       self.llm_tools, prompt,
       max_retries=self.chunk_retry_max,
       backoff_sec=self.chunk_retry_backoff,
       chunk_label=f"{rel_path} chunk {idx+1}",
   )
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Patterns that indicate transient / retryable failures in the error string
# returned by ``llm_tools.llm_call()`` when the underlying SDK raises.
# ---------------------------------------------------------------------------
_RETRYABLE_PATTERNS = re.compile(
    r"429|rate.?limit|too many requests"
    r"|timeout|timed?\s*out"
    r"|50[0-4]|server.?error|service.?unavailable|bad.?gateway"
    r"|internal_server_error"
    r"|overloaded|capacity"
    r"|connection.?(?:reset|refused|aborted|closed)"
    r"|broken.?pipe"
    r"|request.?error.*sending.?request",
    re.IGNORECASE,
)


def is_retryable_error(response_or_error: str) -> bool:
    """Return True if the response text looks like a transient LLM error."""
    if not isinstance(response_or_error, str):
        return False
    return bool(_RETRYABLE_PATTERNS.search(response_or_error))


def llm_call_with_retry(
    llm_tools: Any,
    prompt: str,
    *,
    max_retries: int = 3,
    backoff_sec: float = 5.0,
    chunk_label: str = "",
    log: Optional[logging.Logger] = None,
    model: Optional[str] = None,
) -> str:
    """Call ``llm_tools.llm_call(prompt)`` with exponential-backoff retries.

    Parameters
    ----------
    llm_tools:
        Object exposing ``.llm_call(prompt, ...) -> str``.
    prompt:
        The full LLM prompt string.
    max_retries:
        Maximum number of retry attempts (0 = no retries, call once).
    backoff_sec:
        Initial backoff in seconds; doubles after each failed attempt.
    chunk_label:
        Human-readable label for log messages (e.g. ``"file.v chunk 3"``).
    log:
        Logger instance.  Falls back to module-level logger if *None*.
    model:
        Optional model override passed to ``llm_call(prompt, model=model)``.
        Used by the fixer agent which may use a different coding model.

    Returns
    -------
    str
        The LLM response text.  On final failure the last error string is
        returned so the caller can handle it (or let it flow into parsing
        which will produce zero issues).

    Raises
    ------
    Exception
        Re-raises the last exception if all retries are exhausted AND the
        failure was an actual exception (not an error-string return).
    """
    _log = log or logger
    attempts = 1 + max(0, max_retries)
    wait = backoff_sec
    last_exc: Optional[Exception] = None
    last_response: str = ""

    for attempt in range(1, attempts + 1):
        try:
            # Some agents pass model= (e.g. fixer uses coding_model)
            if model is not None:
                response = llm_tools.llm_call(prompt, model=model)
            else:
                response = llm_tools.llm_call(prompt)

            # ── Error-string detection ─────────────────────────────────
            # llm_tools_anthropic and llm_tools_qgenie return an error
            # *string* (e.g. "LLM invocation failed: ...") rather than
            # raising on failure.  Detect and retry those too.
            if isinstance(response, str) and response.startswith("LLM invocation failed:"):
                if is_retryable_error(response) and attempt < attempts:
                    _log.warning(
                        f"[LLM Retry] {chunk_label} attempt {attempt}/{attempts} "
                        f"got retryable error: {response[:160]}… — "
                        f"retrying in {wait:.0f}s"
                    )
                    time.sleep(wait)
                    wait *= 2
                    last_response = response
                    continue
                # Non-retryable error or final attempt — return as-is
                if attempt > 1:
                    _log.warning(
                        f"[LLM Retry] {chunk_label} giving up after "
                        f"{attempt} attempt(s): {response[:160]}"
                    )
                return response

            # ── Success ────────────────────────────────────────────────
            if attempt > 1:
                _log.info(
                    f"[LLM Retry] {chunk_label} succeeded on attempt "
                    f"{attempt}/{attempts}"
                )
            return response

        except Exception as exc:
            last_exc = exc
            err_str = str(exc)
            if is_retryable_error(err_str) and attempt < attempts:
                _log.warning(
                    f"[LLM Retry] {chunk_label} attempt {attempt}/{attempts} "
                    f"raised {type(exc).__name__}: {err_str[:160]}… — "
                    f"retrying in {wait:.0f}s"
                )
                time.sleep(wait)
                wait *= 2
                continue
            # Non-retryable or final attempt
            if attempt > 1:
                _log.warning(
                    f"[LLM Retry] {chunk_label} giving up after "
                    f"{attempt} attempt(s): {err_str[:160]}"
                )
            raise

    # Should not reach here, but just in case
    if last_exc:
        raise last_exc
    return last_response
