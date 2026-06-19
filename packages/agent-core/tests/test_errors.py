"""Tests for agent-core error classification and retry policy."""

import pytest
from agent_core.errors import (
    APIErrorClassifier,
    AuthError,
    ContentPolicyError,
    ContextTooLongError,
    JalaAgentError,
    RateLimitError,
    RetryPolicy,
    TimeoutError,
    TransientError,
)
from agent_core.models import FailoverReason


class TestErrorHierarchy:
    def test_subclass_chain(self) -> None:
        assert issubclass(RateLimitError, JalaAgentError)
        assert issubclass(AuthError, JalaAgentError)
        assert issubclass(TransientError, JalaAgentError)


class TestAPIErrorClassifier:
    def test_own_rate_limit(self) -> None:
        reason = APIErrorClassifier.classify(RateLimitError())
        assert reason == FailoverReason.RATE_LIMIT

    def test_own_auth(self) -> None:
        reason = APIErrorClassifier.classify(AuthError())
        assert reason == FailoverReason.AUTH_ERROR

    def test_own_content_policy(self) -> None:
        reason = APIErrorClassifier.classify(ContentPolicyError())
        assert reason == FailoverReason.CONTENT_POLICY

    def test_own_context_too_long(self) -> None:
        reason = APIErrorClassifier.classify(ContextTooLongError())
        assert reason == FailoverReason.CONTEXT_TOO_LONG

    def test_own_timeout(self) -> None:
        reason = APIErrorClassifier.classify(TimeoutError())
        assert reason == FailoverReason.TIMEOUT

    def test_own_transient(self) -> None:
        reason = APIErrorClassifier.classify(TransientError())
        assert reason == FailoverReason.TRANSIENT

    def test_generic_exception_is_unknown(self) -> None:
        reason = APIErrorClassifier.classify(ValueError("something"))
        assert reason == FailoverReason.UNKNOWN

    def test_httpx_http_status_error_429(self) -> None:
        # Simulate an httpx HTTPStatusError with status 429.
        class FakeResponse:
            status_code = 429

        class FakeHTTPError(Exception):
            @property
            def response(self):
                return FakeResponse()

        # Manually set module to simulate httpx.
        error = FakeHTTPError()
        type(error).__module__ = "httpx"
        reason = APIErrorClassifier.classify(error)
        assert reason == FailoverReason.RATE_LIMIT

    def test_httpx_http_status_error_500(self) -> None:
        class FakeResponse:
            status_code = 500

        class FakeHTTPError(Exception):
            @property
            def response(self):
                return FakeResponse()

        error = FakeHTTPError()
        type(error).__module__ = "httpx"
        reason = APIErrorClassifier.classify(error)
        assert reason == FailoverReason.TRANSIENT

    def test_httpx_timeout(self) -> None:
        class FakeTimeout(Exception):
            pass

        error = FakeTimeout()
        type(error).__module__ = "httpx"
        type(error).__name__ = "TimeoutException"
        reason = APIErrorClassifier.classify(error)
        assert reason == FailoverReason.TIMEOUT


class TestRetryPolicy:
    def test_rate_limit_returns_delay(self) -> None:
        delay = RetryPolicy.get_delay(1, FailoverReason.RATE_LIMIT)
        assert delay is not None
        assert 2.0 <= delay <= 4.0  # 2^1=2 + jitter up to 1

    def test_rate_limit_max_8_retries(self) -> None:
        assert RetryPolicy.get_delay(8, FailoverReason.RATE_LIMIT) is not None
        assert RetryPolicy.get_delay(9, FailoverReason.RATE_LIMIT) is None

    def test_auth_no_retry(self) -> None:
        assert RetryPolicy.get_delay(1, FailoverReason.AUTH_ERROR) is None

    def test_content_policy_no_retry(self) -> None:
        assert RetryPolicy.get_delay(1, FailoverReason.CONTENT_POLICY) is None

    def test_context_too_long_no_retry(self) -> None:
        assert RetryPolicy.get_delay(1, FailoverReason.CONTEXT_TOO_LONG) is None

    def test_timeout_one_retry(self) -> None:
        assert RetryPolicy.get_delay(1, FailoverReason.TIMEOUT) == pytest.approx(5.0)
        assert RetryPolicy.get_delay(2, FailoverReason.TIMEOUT) is None

    def test_transient_max_3(self) -> None:
        assert RetryPolicy.get_delay(3, FailoverReason.TRANSIENT) is not None
        assert RetryPolicy.get_delay(4, FailoverReason.TRANSIENT) is None

    def test_unknown_one_retry(self) -> None:
        assert RetryPolicy.get_delay(1, FailoverReason.UNKNOWN) == 2.0
        assert RetryPolicy.get_delay(2, FailoverReason.UNKNOWN) is None
