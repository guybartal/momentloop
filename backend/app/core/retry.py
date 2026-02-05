"""Retry utilities for external API calls."""

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

# Retry decorator for HTTP API calls with exponential backoff
api_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException)),
    reraise=True,
)


def with_retry(max_attempts: int = 3, min_wait: int = 2, max_wait: int = 30):
    """Create a retry decorator with custom parameters.

    Args:
        max_attempts: Maximum number of retry attempts
        min_wait: Minimum wait time between retries (seconds)
        max_wait: Maximum wait time between retries (seconds)

    Returns:
        A tenacity retry decorator
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
        retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException)),
        reraise=True,
    )
