"""Error classification hierarchy and retry policies for JalaAgent."""

import random

from agent_core.models import FailoverReason


# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------


class JalaAgentError(Exception):
    """Base error for all JalaAgent exceptions."""


class RateLimitError(JalaAgentError):
    """Rate limit exceeded — use jittered exponential backoff."""


class AuthError(JalaAgentError):
    """Authentication failure — rotate credential pool."""


class ContentPolicyError(JalaAgentError):
    """Content policy violation — try fallback provider once, never retry same prompt."""


class ContextTooLongError(JalaAgentError):
    """Context window exceeded — trigger compaction then retry."""


class TimeoutError(JalaAgentError):
    """TTFB watchdog timeout — kill and retry."""


class TransientError(JalaAgentError):
    """Transient server/network error — exponential backoff up to 3 attempts."""


class ToolLoopError(JalaAgentError):
    """Hard stop — tool was called too many times in a loop."""


# ---------------------------------------------------------------------------
# Error classifier
# ---------------------------------------------------------------------------


class APIErrorClassifier:
    """Classify provider API errors into :class:`FailoverReason` categories."""

    # HTTP status codes that map to specific reasons.
    _STATUS_MAP: dict[int, FailoverReason] = {
        429: FailoverReason.RATE_LIMIT,
        401: FailoverReason.AUTH_ERROR,
        403: FailoverReason.AUTH_ERROR,
        400: FailoverReason.CONTENT_POLICY,  # often content-policy related
        413: FailoverReason.CONTEXT_TOO_LONG,
        408: FailoverReason.TIMEOUT,
        504: FailoverReason.TIMEOUT,
    }

    @staticmethod
    def classify(exception: Exception) -> FailoverReason:
        """Classify *exception* into a failover reason.

        Handles:
        * Our own :class:`JalaAgentError` subclasses directly.
        * ``httpx.HTTPStatusError`` by status code.
        * ``httpx.TimeoutException`` → TIMEOUT.
        * ``httpx.ConnectError`` → TRANSIENT.
        * Everything else → UNKNOWN.

        Parameters
        ----------
        exception:
            The exception to classify.

        Returns
        -------
        FailoverReason
            The classified reason.
        """
        # Our own error types.
        if isinstance(exception, RateLimitError):
            return FailoverReason.RATE_LIMIT
        if isinstance(exception, AuthError):
            return FailoverReason.AUTH_ERROR
        if isinstance(exception, ContentPolicyError):
            return FailoverReason.CONTENT_POLICY
        if isinstance(exception, ContextTooLongError):
            return FailoverReason.CONTEXT_TOO_LONG
        if isinstance(exception, TimeoutError):
            return FailoverReason.TIMEOUT
        if isinstance(exception, TransientError):
            return FailoverReason.TRANSIENT

        # httpx exceptions (import lazily so agent-core doesn't hard-depend on httpx).
        cls_name = type(exception).__name__
        module = getattr(type(exception), "__module__", "")

        if "httpx" in module:
            # HTTPStatusError.
            if hasattr(exception, "response"):
                resp = getattr(exception, "response", None)
                if resp is not None and hasattr(resp, "status_code"):
                    status = resp.status_code
                    if status in APIErrorClassifier._STATUS_MAP:
                        return APIErrorClassifier._STATUS_MAP[status]
                    if 500 <= status < 600:
                        return FailoverReason.TRANSIENT

            # TimeoutException, ConnectError, etc.
            if "Timeout" in cls_name:
                return FailoverReason.TIMEOUT
            if "Connect" in cls_name or "Network" in cls_name:
                return FailoverReason.TRANSIENT

        return FailoverReason.UNKNOWN


# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------


class RetryPolicy:
    """Compute retry delays based on :class:`FailoverReason`."""

    @staticmethod
    def get_delay(attempt: int, reason: FailoverReason) -> float | None:
        """Return the delay (in seconds) before the next retry, or ``None``.

        Parameters
        ----------
        attempt:
            Which retry attempt this is (1-based).
        reason:
            The classified failover reason.

        Returns
        -------
        float | None
            Seconds to wait, or ``None`` to stop retrying.
        """
        if reason == FailoverReason.RATE_LIMIT:
            if attempt > 8:
                return None
            # Jittered exponential backoff: base 2^attempt with jitter.
            base = 2 ** attempt
            jitter = random.uniform(0, base * 0.5)
            return min(base + jitter, 120.0)

        if reason == FailoverReason.AUTH_ERROR:
            return None  # Do not retry — rotate credentials.

        if reason == FailoverReason.CONTENT_POLICY:
            return None  # Do not retry — content is blocked.

        if reason == FailoverReason.CONTEXT_TOO_LONG:
            return None  # Must compact first, then retry at higher level.

        if reason == FailoverReason.TIMEOUT:
            if attempt > 1:
                return None
            return 5.0  # One retry after 5 seconds.

        if reason == FailoverReason.TRANSIENT:
            if attempt > 3:
                return None
            base = 2 ** attempt
            jitter = random.uniform(0, base * 0.3)
            return min(base + jitter, 30.0)

        # UNKNOWN — be conservative, 1 retry.
        if attempt > 1:
            return None
        return 2.0
