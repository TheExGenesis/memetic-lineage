"""Tests for retry.py utilities."""
import pytest

from lib.retry import is_rate_limit_error, is_transient_error, with_retry


class TestIsRateLimitError:
    def test_429_status(self):
        assert is_rate_limit_error(Exception("HTTP 429 Too Many Requests"))

    def test_rate_limit_message(self):
        assert is_rate_limit_error(Exception("rate_limit_exceeded"))

    def test_quota_message(self):
        assert is_rate_limit_error(Exception("You have exceeded your quota"))

    def test_too_many_requests(self):
        assert is_rate_limit_error(Exception("Too Many Requests"))

    def test_not_rate_limit(self):
        assert not is_rate_limit_error(Exception("Connection timeout"))
        assert not is_rate_limit_error(Exception("Invalid API key"))


class TestIsTransientError:
    def test_timeout(self):
        assert is_transient_error(Exception("Connection timeout"))

    def test_network_error(self):
        assert is_transient_error(Exception("Network unreachable"))

    def test_502_bad_gateway(self):
        assert is_transient_error(Exception("502 Bad Gateway"))

    def test_503_unavailable(self):
        assert is_transient_error(Exception("Service Unavailable 503"))

    def test_504_timeout(self):
        assert is_transient_error(Exception("504 Gateway Timeout"))

    def test_rate_limit_is_transient(self):
        assert is_transient_error(Exception("rate_limit_exceeded"))

    def test_not_transient(self):
        assert not is_transient_error(Exception("Invalid JSON"))
        assert not is_transient_error(Exception("Authentication failed"))


class TestWithRetry:
    def test_success_no_retry(self):
        call_count = 0

        @with_retry(max_retries=3, base_delay=0.01)
        def fn():
            nonlocal call_count
            call_count += 1
            return "success"

        result = fn()
        assert result == "success"
        assert call_count == 1

    def test_retry_then_success(self):
        call_count = 0

        @with_retry(max_retries=3, base_delay=0.01)
        def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("temporary failure")
            return "success"

        result = fn()
        assert result == "success"
        assert call_count == 3

    def test_all_retries_fail(self):
        call_count = 0

        @with_retry(max_retries=3, base_delay=0.01)
        def fn():
            nonlocal call_count
            call_count += 1
            raise ValueError("always fails")

        with pytest.raises(ValueError, match="always fails"):
            fn()
        assert call_count == 3

    def test_specific_retryable_errors(self):
        call_count = 0

        @with_retry(max_retries=3, base_delay=0.01, retryable_errors=(ValueError,))
        def fn():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("retryable")
            if call_count == 2:
                raise TypeError("not retryable")
            return "success"

        with pytest.raises(TypeError, match="not retryable"):
            fn()
        assert call_count == 2

    def test_on_retry_callback(self):
        retry_logs = []

        def log_retry(e, attempt):
            retry_logs.append((str(e), attempt))

        @with_retry(max_retries=3, base_delay=0.01, on_retry=log_retry)
        def fn():
            if len(retry_logs) < 2:
                raise ValueError("fail")
            return "ok"

        fn()
        assert len(retry_logs) == 2
        assert retry_logs[0] == ("fail", 0)
        assert retry_logs[1] == ("fail", 1)







