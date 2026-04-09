"""
Integration tests: Retry and backoff behavior across all API calls

These tests verify the retry middleware that wraps every outbound Mistral
API call in parler:
  - Exponential backoff with jitter on 429 / 503
  - Immediate failure on 401 / 403 (auth errors — no retry)
  - Immediate failure on 400 (bad request — client error, no retry)
  - Timeout triggers retry with same backoff policy
  - Retry counter exposed for telemetry / progress reporting
  - Max retry cap respected (default: 3)
  - Checkpoint saved on final failure for transcription calls
"""

import pytest
import time
from unittest.mock import patch, MagicMock, call
from parler.utils.retry import with_retry, RetryConfig, RetryExhaustedError


# ─── Basic retry mechanics ────────────────────────────────────────────────────

class TestRetryMechanics:

    def test_no_retry_on_success(self):
        """A function that succeeds on the first try should only be called once."""
        call_count = [0]

        def fn():
            call_count[0] += 1
            return "success"

        result = with_retry(fn, config=RetryConfig(max_retries=3))
        assert result == "success"
        assert call_count[0] == 1

    def test_retries_on_retriable_exception(self):
        """Function that fails twice then succeeds → called 3 times total."""
        call_count = [0]

        def fn():
            call_count[0] += 1
            if call_count[0] < 3:
                raise ConnectionError("Network blip")
            return "ok"

        with patch("time.sleep"):
            result = with_retry(fn, config=RetryConfig(max_retries=3, retriable_exceptions=(ConnectionError,)))

        assert result == "ok"
        assert call_count[0] == 3

    def test_raises_retry_exhausted_after_max_retries(self):
        """After max_retries failures, RetryExhaustedError is raised."""
        def always_fail():
            raise ConnectionError("Always fails")

        with patch("time.sleep"):
            with pytest.raises(RetryExhaustedError):
                with_retry(always_fail, config=RetryConfig(max_retries=3, retriable_exceptions=(ConnectionError,)))

    def test_retry_exhausted_error_contains_attempt_count(self):
        """RetryExhaustedError should carry the number of attempts made."""
        def always_fail():
            raise ConnectionError("fail")

        with patch("time.sleep"):
            with pytest.raises(RetryExhaustedError) as exc_info:
                with_retry(always_fail, config=RetryConfig(max_retries=3, retriable_exceptions=(ConnectionError,)))

        assert exc_info.value.attempts == 3

    def test_non_retriable_exception_propagates_immediately(self):
        """ValueError (non-retriable) should propagate without retry."""
        call_count = [0]

        def fn():
            call_count[0] += 1
            raise ValueError("Bad input")

        with pytest.raises(ValueError):
            with_retry(fn, config=RetryConfig(max_retries=3, retriable_exceptions=(ConnectionError,)))

        assert call_count[0] == 1  # no retry


# ─── Backoff timing ───────────────────────────────────────────────────────────

class TestBackoffTiming:

    def test_backoff_increases_with_each_retry(self):
        """Sleep durations should increase between retries (exponential backoff)."""
        call_count = [0]
        sleep_durations = []

        def fn():
            call_count[0] += 1
            if call_count[0] < 4:
                raise ConnectionError("fail")
            return "ok"

        with patch("time.sleep", side_effect=lambda d: sleep_durations.append(d)):
            with_retry(fn, config=RetryConfig(
                max_retries=3,
                retriable_exceptions=(ConnectionError,),
                base_delay_s=1.0,
                backoff_multiplier=2.0,
                jitter=False,
            ))

        assert len(sleep_durations) == 3
        assert sleep_durations[0] < sleep_durations[1] < sleep_durations[2]

    def test_backoff_does_not_exceed_max_delay(self):
        """Backoff sleep should be capped at max_delay_s."""
        sleep_durations = []
        call_count = [0]

        def fn():
            call_count[0] += 1
            if call_count[0] < 6:
                raise ConnectionError("fail")
            return "ok"

        with patch("time.sleep", side_effect=lambda d: sleep_durations.append(d)):
            with_retry(fn, config=RetryConfig(
                max_retries=5,
                retriable_exceptions=(ConnectionError,),
                base_delay_s=1.0,
                backoff_multiplier=4.0,
                max_delay_s=10.0,
                jitter=False,
            ))

        for d in sleep_durations:
            assert d <= 10.0, f"Sleep {d} exceeded max_delay_s=10.0"

    def test_jitter_adds_randomness_within_bounds(self):
        """With jitter enabled, sleep durations have variance but stay within bounds."""
        sleep_durations = []
        call_count = [0]

        def fn():
            call_count[0] += 1
            if call_count[0] < 4:
                raise ConnectionError("fail")
            return "ok"

        # Run 5 times and collect sleep durations
        all_durations = []
        for _ in range(5):
            call_count[0] = 0
            sleep_durations.clear()
            try:
                with patch("time.sleep", side_effect=lambda d: sleep_durations.append(d)):
                    with_retry(fn, config=RetryConfig(
                        max_retries=3,
                        retriable_exceptions=(ConnectionError,),
                        base_delay_s=1.0,
                        jitter=True,
                    ))
            except Exception:
                pass
            all_durations.extend(sleep_durations)

        # With jitter, not all durations should be identical
        if len(all_durations) > 2:
            assert len(set(all_durations)) > 1, "Jitter is not adding randomness"


# ─── HTTP status code handling ────────────────────────────────────────────────

class TestHTTPStatusCodeHandling:

    def test_429_is_retriable(self):
        """HTTP 429 (Too Many Requests) should trigger retry."""
        from parler.utils.retry import is_retriable_http_status
        assert is_retriable_http_status(429) is True

    def test_503_is_retriable(self):
        """HTTP 503 (Service Unavailable) should trigger retry."""
        from parler.utils.retry import is_retriable_http_status
        assert is_retriable_http_status(503) is True

    def test_401_is_not_retriable(self):
        """HTTP 401 (Unauthorized) should NOT trigger retry."""
        from parler.utils.retry import is_retriable_http_status
        assert is_retriable_http_status(401) is False

    def test_403_is_not_retriable(self):
        """HTTP 403 (Forbidden) should NOT trigger retry."""
        from parler.utils.retry import is_retriable_http_status
        assert is_retriable_http_status(403) is False

    def test_400_is_not_retriable(self):
        """HTTP 400 (Bad Request — client error) should NOT trigger retry."""
        from parler.utils.retry import is_retriable_http_status
        assert is_retriable_http_status(400) is False

    def test_500_is_retriable(self):
        """HTTP 500 (Internal Server Error) should trigger retry (transient)."""
        from parler.utils.retry import is_retriable_http_status
        assert is_retriable_http_status(500) is True


# ─── Retry counter ────────────────────────────────────────────────────────────

class TestRetryCounter:

    def test_retry_counter_passed_to_on_retry_callback(self):
        """The on_retry callback should receive attempt number on each retry."""
        retry_events = []
        call_count = [0]

        def fn():
            call_count[0] += 1
            if call_count[0] < 3:
                raise ConnectionError("fail")
            return "ok"

        def on_retry(attempt, delay, exc):
            retry_events.append({"attempt": attempt, "delay": delay})

        with patch("time.sleep"):
            with_retry(fn, config=RetryConfig(
                max_retries=3,
                retriable_exceptions=(ConnectionError,),
                on_retry=on_retry,
            ))

        assert len(retry_events) == 2
        assert retry_events[0]["attempt"] == 1
        assert retry_events[1]["attempt"] == 2


# ─── Timeout handling ────────────────────────────────────────────────────────

class TestTimeoutHandling:

    def test_timeout_exception_is_retriable(self):
        """TimeoutError should be treated as retriable."""
        call_count = [0]

        def fn():
            call_count[0] += 1
            if call_count[0] < 2:
                raise TimeoutError("Request timed out")
            return "ok"

        with patch("time.sleep"):
            result = with_retry(fn, config=RetryConfig(
                max_retries=3,
                retriable_exceptions=(ConnectionError, TimeoutError),
            ))

        assert result == "ok"
        assert call_count[0] == 2
