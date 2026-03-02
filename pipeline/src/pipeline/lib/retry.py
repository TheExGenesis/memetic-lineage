"""Retry utilities with exponential backoff."""
import time
from functools import wraps
from typing import Callable, Tuple, Type, TypeVar, Optional

T = TypeVar('T')


def with_retry(
    max_retries: int = 5,
    base_delay: float = 1.0,
    retryable_errors: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None
):
    """
    Decorator for exponential backoff retry.
    
    Args:
        max_retries: Maximum number of attempts
        base_delay: Initial delay in seconds (doubles each retry)
        retryable_errors: Tuple of exception types to retry on
        on_retry: Optional callback(exception, attempt) called before each retry
    """
    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @wraps(fn)
        def wrapper(*args, **kwargs) -> T:
            for attempt in range(max_retries):
                try:
                    return fn(*args, **kwargs)
                except retryable_errors as e:
                    if attempt == max_retries - 1:
                        raise
                    delay = base_delay * (2 ** attempt)
                    if on_retry:
                        on_retry(e, attempt)
                    else:
                        print(f"Retry {attempt + 1}/{max_retries} in {delay:.1f}s: {type(e).__name__}: {e}")
                    time.sleep(delay)
            raise RuntimeError("Unreachable")
        return wrapper
    return decorator


def is_rate_limit_error(e: Exception) -> bool:
    """Check if exception looks like a rate limit error."""
    error_str = str(e).lower()
    return any(x in error_str for x in ["rate_limit", "429", "too many requests", "quota"])


def is_transient_error(e: Exception) -> bool:
    """Check if exception is likely transient (network, timeout, etc)."""
    error_str = str(e).lower()
    return any(x in error_str for x in [
        "timeout", "connection", "network", "unavailable", 
        "502", "503", "504", "rate_limit", "429"
    ])

