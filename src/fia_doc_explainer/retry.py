import asyncio
import functools
from collections.abc import Callable
from time import sleep


def retry(
    *, exceptions: tuple[type[Exception], ...], max_attempts: int, base_delay: float
):
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return fn(*args, **kwargs)
                except exceptions:
                    if attempt == max_attempts - 1:
                        raise
                    else:
                        delay = base_delay * (2**attempt)
                        sleep(delay)

        return wrapper

    return decorator


def async_retry(
    *, exceptions: tuple[type[Exception], ...], max_attempts: int, base_delay: float
):
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return await fn(*args, **kwargs)
                except exceptions:
                    if attempt == max_attempts - 1:
                        raise
                    else:
                        delay = base_delay * (2**attempt)
                        await asyncio.sleep(delay)

        return wrapper

    return decorator
