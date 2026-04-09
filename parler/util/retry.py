"""Retry helpers for transient external failures."""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


class RetryExhaustedError(RuntimeError):
    def __init__(self, attempts: int, last_exception: BaseException):
        super().__init__(str(last_exception))
        self.attempts = attempts
        self.last_exception = last_exception


@dataclass(frozen=True)
class RetryConfig:
    max_retries: int = 3
    retriable_exceptions: tuple[type[BaseException], ...] = (Exception,)
    base_delay_s: float = 0.5
    backoff_multiplier: float = 2.0
    max_delay_s: float = 30.0
    jitter: bool = True
    on_retry: Callable[[int, float, BaseException], None] | None = None


def is_retriable_http_status(status_code: int) -> bool:
    return status_code in {429, 500, 502, 503, 504}


def _compute_delay(retry_number: int, config: RetryConfig) -> float:
    delay = min(
        config.base_delay_s * (config.backoff_multiplier ** max(retry_number - 1, 0)),
        config.max_delay_s,
    )
    if not config.jitter:
        return delay
    jittered = random.uniform(delay * 0.5, delay * 1.5)
    return min(jittered, config.max_delay_s)


def with_retry(fn: Callable[[], Any], *, config: RetryConfig) -> Any:
    retries_used = 0
    while True:
        try:
            return fn()
        except config.retriable_exceptions as exc:
            if retries_used >= config.max_retries:
                raise RetryExhaustedError(config.max_retries, exc) from exc
            retries_used += 1
            delay = _compute_delay(retries_used, config)
            if config.on_retry is not None:
                config.on_retry(retries_used, delay, exc)
            time.sleep(delay)
