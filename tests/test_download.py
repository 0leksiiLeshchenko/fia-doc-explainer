import httpx
import pytest
import respx

from fia_doc_explainer.download import RetryableHTTPError, download_pdf
from fia_doc_explainer.errors import DownloadError

TEST_URL = "https://example.com/fia_doc.pdf"


@respx.mock
async def test_download_pdf_success() -> None:
    respx.get(TEST_URL).mock(return_value=httpx.Response(200, content=b"%PDF-1.4..."))
    result = await download_pdf(TEST_URL)
    assert result == b"%PDF-1.4..."


@respx.mock
async def test_download_pdf_succeeds_after_retryable_status() -> None:
    route = respx.get(TEST_URL)
    route.side_effect = [
        httpx.Response(status_code=500),
        httpx.Response(status_code=200, content=b"%PDF-1.4..."),
    ]

    result = await download_pdf(TEST_URL)
    assert result == b"%PDF-1.4..."
    assert route.call_count == 2


@respx.mock
async def test_download_pdf_fails_with_retryable_status_after_exhausting_attempts() -> (
    None
):
    route = respx.get(TEST_URL)
    route.side_effect = [httpx.Response(status_code=500)] * 5

    with pytest.raises(DownloadError) as exc_info:
        await download_pdf(TEST_URL)
    assert isinstance(exc_info.value.__cause__, RetryableHTTPError)
    assert route.call_count == 5


@respx.mock
async def test_download_pdf_succeeds_after_transport_failures() -> None:
    route = respx.get(TEST_URL)
    route.side_effect = [
        httpx.ConnectTimeout,
        httpx.Response(status_code=200, content=b"%PDF-1.4..."),
    ]

    result = await download_pdf(TEST_URL)
    assert result == b"%PDF-1.4..."
    assert route.call_count == 2


@respx.mock
async def test_download_pdf_fails_with_transport_after_exhausting_attempts() -> None:
    route = respx.get(TEST_URL)
    route.side_effect = [httpx.ConnectTimeout] * 5

    with pytest.raises(DownloadError) as exc_info:
        await download_pdf(TEST_URL)
    assert isinstance(exc_info.value.__cause__, httpx.ConnectTimeout)
    assert route.call_count == 5


@respx.mock
async def test_download_pdf_fails_after_non_retryable_status_code() -> None:
    route = respx.get(TEST_URL).mock(return_value=httpx.Response(status_code=404))

    with pytest.raises(DownloadError) as exc_info:
        await download_pdf(TEST_URL)

    assert isinstance(exc_info.value.__cause__, httpx.HTTPStatusError)
    assert route.call_count == 1


async def test_download_pdf_fails_with_invalid_url() -> None:
    with pytest.raises(DownloadError):
        await download_pdf("не-url")
