from collections.abc import Callable

import httpx
import pytest

from fia_doc_explainer.retry import async_retry, retry


def make_flaky_function(
    fail_times: int, exception: type[Exception] = ConnectionError
) -> Callable:
    def flaky():
        flaky.call_count += 1
        if flaky.call_count <= fail_times:
            raise exception("simulated failure")
        return "success"

    flaky.call_count = 0
    return flaky


def test_retry_succeeds_after_transient_failures() -> None:
    flaky = make_flaky_function(fail_times=2)
    wrapped = retry(exceptions=(ConnectionError,), max_attempts=3, base_delay=0.01)(
        flaky
    )

    result = wrapped()

    assert result == "success"


def test_retry_raises_after_exhausting_attempts() -> None:
    flaky = make_flaky_function(fail_times=5)
    wrapped = retry(exceptions=(ConnectionError,), max_attempts=3, base_delay=0.01)(
        flaky
    )

    with pytest.raises(ConnectionError):
        wrapped()

    assert flaky.call_count == 3


def test_retry_does_not_retry_non_retryable_exception() -> None:
    flaky = make_flaky_function(fail_times=5, exception=ValueError)
    wrapped = retry(exceptions=(ConnectionError,), max_attempts=3, base_delay=0.01)(
        flaky
    )

    with pytest.raises(ValueError):
        wrapped()

    assert flaky.call_count == 1


def make_async_flaky_function(
    fail_times: int, exception: type[Exception] = httpx.ConnectTimeout
) -> Callable:
    async def flaky():
        flaky.call_count += 1
        if flaky.call_count <= fail_times:
            raise exception("simulated failure")
        return "success"

    flaky.call_count = 0
    return flaky


async def test_async_retry_succeeds_after_transient_failures() -> None:
    flaky = make_async_flaky_function(fail_times=2)
    wrapped = async_retry(
        exceptions=(httpx.ConnectTimeout,), max_attempts=3, base_delay=0.01
    )(flaky)

    result = await wrapped()

    assert result == "success"


async def test_async_retry_raises_after_exhausting_attempts() -> None:
    flaky = make_async_flaky_function(fail_times=5)
    wrapped = async_retry(
        exceptions=(httpx.ConnectTimeout,), max_attempts=3, base_delay=0.01
    )(flaky)

    with pytest.raises(httpx.ConnectTimeout):
        await wrapped()

    assert flaky.call_count == 3


async def test_async_retry_does_not_retry_non_retryable_exception() -> None:
    flaky = make_async_flaky_function(fail_times=5, exception=ValueError)
    wrapped = async_retry(
        exceptions=(httpx.ConnectTimeout,), max_attempts=3, base_delay=0.01
    )(flaky)

    with pytest.raises(ValueError):
        await wrapped()

    assert flaky.call_count == 1
