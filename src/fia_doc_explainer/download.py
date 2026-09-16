from enum import IntEnum

import httpx

from fia_doc_explainer.retry import async_retry


class RetryableHTTPError(Exception):
    def __init__(self, url: str, status_code: int, message: str, *args):
        super().__init__(message, *args)

        self.url = url
        self.status_code = status_code
        self.message = message


class RetryableStatusCode(IntEnum):
    TOO_MANY_REQUESTS = 429
    INTERNAL_SERVER_ERROR = 500
    BAD_GATEWAY = 502
    SERVICE_UNAVAILABLE = 503
    GATEWAY_TIMEOUT = 504


RETRYABLE_EXCEPTIONS = (
    RetryableHTTPError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
    httpx.ConnectError,
    httpx.CloseError,
    httpx.ReadError,
    httpx.WriteError,
    httpx.RemoteProtocolError,
)


@async_retry(
    exceptions=RETRYABLE_EXCEPTIONS,
    max_attempts=5,
    base_delay=1,
)
async def download_pdf(url: str) -> bytes:
    async with httpx.AsyncClient() as client:
        response = await client.get(url=url)
        if response.status_code in RetryableStatusCode:
            raise RetryableHTTPError(
                url=url,
                status_code=response.status_code,
                message=f"Request to {url} failed with status code {response.status_code}, error: {response.text!r}",
            )

        response.raise_for_status()

        return response.content
