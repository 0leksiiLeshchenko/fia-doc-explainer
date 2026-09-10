from collections.abc import Callable
import functools
from time import sleep


def retry(*, exceptions: tuple[type[Exception], ...], max_attempts: int, base_delay: float):
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return fn(*args, **kwargs)  # успех — сразу выходим, никакого sleep не нужно
                except exceptions as exc:
                    # сюда попадаем только если fn упал с retryable-исключением
                    if attempt == max_attempts - 1:
                        raise
                    else:
                        delay = base_delay * (2 ** attempt)  # как выразить exponential рост через base_delay и attempt?
                        sleep(delay)
        return wrapper
    return decorator