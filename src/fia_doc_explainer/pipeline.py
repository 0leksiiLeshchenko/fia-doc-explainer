import anthropic

from fia_doc_explainer.extract import NoTextLayerError, PdfminerException, extract_text
from fia_doc_explainer.providers.anthropic_provider import (
    RETRYABLE_ANTHROPIC_EXCEPTIONS,
    is_quota_error,
)
from fia_doc_explainer.providers.chain import ProviderChain
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

    llm_response: LLMResponse | None = None
    escalation_needed: bool = False
    confidence_flagged: bool = False
    confidence_reason: str | None = None
    heuristic_reason: str | None = None

    if reason := check_text_quality(text=text):
        escalation_needed = True
        heuristic_reason = reason

    try:
        llm_response = providers.primary.summarize(text)
    except anthropic.BadRequestError as err:
        if is_quota_error(err):
            try:
                llm_response = providers.quota_fallback.summarize(text)
            except Exception as exc:
                raise LLMError(
                    message="No provider can generate proper doc summary"
                ) from exc
        else:
            raise LLMError(message=f"Primary provider failed: {err.body}") from err
    except RETRYABLE_ANTHROPIC_EXCEPTIONS:
        escalation_needed = True

    if llm_response and llm_response.low_confidence_flag:
        escalation_needed = True
        confidence_flagged = True
        confidence_reason = llm_response.low_confidence_flag.reason

    if escalation_needed:
        try:
            llm_response = providers.escalation.summarize(text)
        except anthropic.BadRequestError as err:
            if is_quota_error(err):
                try:
                    llm_response = providers.quota_fallback.summarize(text)
                except Exception as exc:
                    raise LLMError(
                        message="No provider can generate proper doc summary"
                    ) from exc
            else:
                raise LLMError(
                    message=f"Escalation provider failed: {err.body}"
                ) from err
        except RETRYABLE_ANTHROPIC_EXCEPTIONS as exc:
            raise LLMError(
                f"Error occurred processing the document: {str(exc)!r}"
            ) from exc

        if llm_response and llm_response.low_confidence_flag:
            confidence_flagged = True
            confidence_reason = llm_response.low_confidence_flag.reason

    if llm_response and llm_response.low_confidence_flag:
        raise LLMError(
            message=f"No provider can generate proper doc summary: {llm_response.low_confidence_flag.reason!r}"
        )
    assert llm_response is not None and llm_response.summary is not None
    return DocumentSummary(
        doc_type=llm_response.summary.doc_type,
        source_url=source_url,
        key_facts=llm_response.summary.key_facts,
        plain_explanation=llm_response.summary.plain_explanation,
        model_used=llm_response.model,
        low_confidence=confidence_flagged or heuristic_reason is not None,
        low_confidence_reason=confidence_reason,
        heuristic_reason=heuristic_reason,
    )
