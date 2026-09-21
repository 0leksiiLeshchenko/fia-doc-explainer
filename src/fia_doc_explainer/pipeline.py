from fia_doc_explainer.extract import NoTextLayerError, PdfminerException, extract_text
from fia_doc_explainer.providers.base import LLMProvider
from fia_doc_explainer.providers.chain import ProviderChain
from fia_doc_explainer.providers.errors import (
    ProviderError,
    ProviderPermanentError,
    ProviderQuotaError,
    ProviderResponseError,
    ProviderTransientError,
)
from fia_doc_explainer.quality import check_text_quality
from fia_doc_explainer.schemas import DocumentSummary, LLMResponse


class DocumentProcessingError(Exception): ...


class DownloadError(DocumentProcessingError): ...


class ExtractionError(DocumentProcessingError):
    def __init__(self, message: str, *args):
        super().__init__(message, *args)

        self.message = message


class LLMError(DocumentProcessingError):
    def __init__(self, message: str, *args):
        super().__init__(message, *args)

        self.message = message


def _summarize_with_quota_fallback(
    provider: LLMProvider,
    quota_fallback: LLMProvider,
    text: str,
) -> LLMResponse:
    try:
        return provider.summarize(text)
    except ProviderQuotaError:
        try:
            return quota_fallback.summarize(text)
        except ProviderError as exc:
            raise LLMError(
                message="No provider can generate proper doc summary"
            ) from exc


def process_document(
    pdf_bytes: bytes,
    providers: ProviderChain,
    source_url: str | None = None,
) -> DocumentSummary:
    try:
        text = extract_text(pdf_bytes)
    except (NoTextLayerError, PdfminerException) as exc:
        raise ExtractionError(
            message=f"Error occurred extracting text from the doc: {str(exc)!r}"
        ) from exc

    escalation_needed: bool = False
    confidence_reason: str | None = None
    heuristic_reason: str | None = None

    if reason := check_text_quality(text=text):
        escalation_needed = True
        heuristic_reason = reason

    try:
        llm_response = _summarize_with_quota_fallback(
            providers.primary, providers.quota_fallback, text
        )
    except (ProviderTransientError, ProviderResponseError):
        escalation_needed = True
    except ProviderPermanentError as exc:
        raise LLMError(message=f"Primary provider failed: {exc.message}") from exc
    else:
        if llm_response.low_confidence_flag:
            escalation_needed = True
            confidence_reason = llm_response.low_confidence_flag.reason

    if escalation_needed:
        try:
            llm_response = _summarize_with_quota_fallback(
                providers.escalation, providers.quota_fallback, text
            )
        except (
            ProviderTransientError,
            ProviderResponseError,
            ProviderPermanentError,
        ) as exc:
            raise LLMError(
                message=f"Escalation provider failed: {exc.message}"
            ) from exc

        if llm_response.low_confidence_flag:
            confidence_reason = llm_response.low_confidence_flag.reason

    if llm_response.low_confidence_flag:
        raise LLMError(
            message=f"No provider can generate proper doc summary: {llm_response.low_confidence_flag.reason!r}"
        )
    assert llm_response.summary is not None
    return DocumentSummary(
        doc_type=llm_response.summary.doc_type,
        source_url=source_url,
        key_facts=llm_response.summary.key_facts,
        plain_explanation=llm_response.summary.plain_explanation,
        model_used=llm_response.model,
        low_confidence_reason=confidence_reason,
        heuristic_reason=heuristic_reason,
    )
