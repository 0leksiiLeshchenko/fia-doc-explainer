import pytest

from fia_doc_explainer.extract import extract_text
from fia_doc_explainer.pipeline import ExtractionError, LLMError, process_document
from fia_doc_explainer.providers.chain import ProviderChain
from fia_doc_explainer.providers.errors import (
    ProviderError,
    ProviderPermanentError,
    ProviderQuotaError,
    ProviderTransientError,
)
from fia_doc_explainer.quality import check_text_quality
from tests.conftest import make_pdf_bytes
from tests.fakes import FakeProvider, flag_response, summary_response

PRIMARY_MODEL = "claude-haiku-4-5"
ESCALATION_MODEL = "claude-sonnet-4-5"
QUOTA_FALLBACK_MODEL = "gemini-3-pro"


def _unused_provider(model: str) -> FakeProvider:
    return FakeProvider(
        model=model, outcome=AssertionError(f"{model} should not be called")
    )


def _primary_and_escalation(
    level: str, exc: ProviderError
) -> tuple[FakeProvider, FakeProvider]:
    if level == "primary":
        return FakeProvider(model=PRIMARY_MODEL, outcome=exc), _unused_provider(
            ESCALATION_MODEL
        )
    primary = FakeProvider(
        model=PRIMARY_MODEL,
        outcome=flag_response(model=PRIMARY_MODEL, reason="not sure about doc type"),
    )
    escalation = FakeProvider(model=ESCALATION_MODEL, outcome=exc)
    return primary, escalation


@pytest.mark.parametrize(
    "pdf_bytes",
    [
        make_pdf_bytes(pages=[None]),
        make_pdf_bytes(pages=["Stewards Decision"], is_broken=True),
    ],
    ids=["no_text_layer", "truncated_pdf"],
)
def test_extraction_error(pdf_bytes: bytes) -> None:
    primary = _unused_provider(PRIMARY_MODEL)
    escalation = _unused_provider(ESCALATION_MODEL)
    quota_fallback = _unused_provider(QUOTA_FALLBACK_MODEL)
    providers = ProviderChain(
        primary=primary, escalation=escalation, quota_fallback=quota_fallback
    )

    with pytest.raises(ExtractionError):
        process_document(pdf_bytes, providers)

    assert primary.calls == []
    assert escalation.calls == []
    assert quota_fallback.calls == []


def test_happy_path() -> None:
    primary = FakeProvider(
        model=PRIMARY_MODEL, outcome=summary_response(model=PRIMARY_MODEL)
    )
    escalation = _unused_provider(ESCALATION_MODEL)
    quota_fallback = _unused_provider(QUOTA_FALLBACK_MODEL)
    providers = ProviderChain(
        primary=primary, escalation=escalation, quota_fallback=quota_fallback
    )
    pdf_bytes = make_pdf_bytes(pages=["Stewards Decision Document 42"])

    result = process_document(pdf_bytes, providers)

    assert result.model_used == PRIMARY_MODEL
    assert result.low_confidence is False
    assert result.low_confidence_reason is None
    assert result.heuristic_reason is None
    assert result.doc_type == "Decision"
    assert result.key_facts == ["Kimi won", "Lewis - DNF"]
    assert result.plain_explanation == "Race was super boring"
    assert escalation.calls == []
    assert quota_fallback.calls == []


def test_source_url_comes_from_caller_not_from_model() -> None:
    # the model can hallucinate a url; only the caller-supplied one is trustworthy
    primary = FakeProvider(
        model=PRIMARY_MODEL,
        outcome=summary_response(
            model=PRIMARY_MODEL,
            source_url="https://model-made-this-up.example/x.pdf",
        ),
    )
    escalation = _unused_provider(ESCALATION_MODEL)
    quota_fallback = _unused_provider(QUOTA_FALLBACK_MODEL)
    providers = ProviderChain(
        primary=primary, escalation=escalation, quota_fallback=quota_fallback
    )
    pdf_bytes = make_pdf_bytes(pages=["Stewards Decision Document 42"])

    result = process_document(
        pdf_bytes, providers, source_url="https://fia.com/real.pdf"
    )

    assert result.source_url == "https://fia.com/real.pdf"


def test_escalation_on_model_flag() -> None:
    primary = FakeProvider(
        model=PRIMARY_MODEL,
        outcome=flag_response(model=PRIMARY_MODEL, reason="not sure about doc type"),
    )
    escalation = FakeProvider(
        model=ESCALATION_MODEL, outcome=summary_response(model=ESCALATION_MODEL)
    )
    quota_fallback = _unused_provider(QUOTA_FALLBACK_MODEL)
    providers = ProviderChain(
        primary=primary, escalation=escalation, quota_fallback=quota_fallback
    )
    pdf_bytes = make_pdf_bytes(pages=["Stewards Decision Document 42"])

    result = process_document(pdf_bytes, providers)

    assert result.model_used == ESCALATION_MODEL
    assert result.low_confidence is True
    assert result.low_confidence_reason == "not sure about doc type"
    assert result.heuristic_reason is None
    assert len(escalation.calls) == 1


def test_escalation_on_heuristic() -> None:
    pdf_bytes = make_pdf_bytes(
        pages=["Stewards Decision 文書番号 42 判定 penalty"], font="Vera"
    )
    # Precondition: if pdfminer's glyph-fallback behavior ever changes, this
    # test must fail loudly instead of silently no longer exercising escalation.
    assert check_text_quality(extract_text(pdf_bytes)) is not None

    primary = FakeProvider(
        model=PRIMARY_MODEL, outcome=summary_response(model=PRIMARY_MODEL)
    )
    escalation = FakeProvider(
        model=ESCALATION_MODEL, outcome=summary_response(model=ESCALATION_MODEL)
    )
    quota_fallback = _unused_provider(QUOTA_FALLBACK_MODEL)
    providers = ProviderChain(
        primary=primary, escalation=escalation, quota_fallback=quota_fallback
    )

    result = process_document(pdf_bytes, providers)

    assert result.model_used == ESCALATION_MODEL
    assert result.low_confidence is True
    assert result.heuristic_reason is not None
    assert result.low_confidence_reason is None


def test_escalation_on_transient_exhaustion() -> None:
    primary = FakeProvider(
        model=PRIMARY_MODEL,
        outcome=ProviderTransientError("rate limited", model=PRIMARY_MODEL),
    )
    escalation = FakeProvider(
        model=ESCALATION_MODEL, outcome=summary_response(model=ESCALATION_MODEL)
    )
    quota_fallback = _unused_provider(QUOTA_FALLBACK_MODEL)
    providers = ProviderChain(
        primary=primary, escalation=escalation, quota_fallback=quota_fallback
    )
    pdf_bytes = make_pdf_bytes(pages=["Stewards Decision Document 42"])

    result = process_document(pdf_bytes, providers)

    assert result.model_used == ESCALATION_MODEL
    assert result.low_confidence is False


def test_escalation_also_flags() -> None:
    primary = FakeProvider(
        model=PRIMARY_MODEL,
        outcome=flag_response(model=PRIMARY_MODEL, reason="not sure about doc type"),
    )
    escalation = FakeProvider(
        model=ESCALATION_MODEL,
        outcome=flag_response(model=ESCALATION_MODEL, reason="still not sure"),
    )
    quota_fallback = _unused_provider(QUOTA_FALLBACK_MODEL)
    providers = ProviderChain(
        primary=primary, escalation=escalation, quota_fallback=quota_fallback
    )
    pdf_bytes = make_pdf_bytes(pages=["Stewards Decision Document 42"])

    with pytest.raises(LLMError, match="still not sure"):
        process_document(pdf_bytes, providers)


@pytest.mark.parametrize("level", ["primary", "escalation"])
def test_quota_falls_back_to_secondary_vendor(level: str) -> None:
    model = PRIMARY_MODEL if level == "primary" else ESCALATION_MODEL
    primary, escalation = _primary_and_escalation(
        level, ProviderQuotaError("quota exhausted", model=model)
    )
    quota_fallback = FakeProvider(
        model=QUOTA_FALLBACK_MODEL,
        outcome=summary_response(model=QUOTA_FALLBACK_MODEL),
    )
    providers = ProviderChain(
        primary=primary, escalation=escalation, quota_fallback=quota_fallback
    )
    pdf_bytes = make_pdf_bytes(pages=["Stewards Decision Document 42"])

    result = process_document(pdf_bytes, providers)

    assert result.model_used == QUOTA_FALLBACK_MODEL
    assert len(quota_fallback.calls) == 1


@pytest.mark.parametrize("level", ["primary", "escalation"])
def test_quota_fallback_also_fails(level: str) -> None:
    model = PRIMARY_MODEL if level == "primary" else ESCALATION_MODEL
    primary, escalation = _primary_and_escalation(
        level, ProviderQuotaError("quota exhausted", model=model)
    )
    quota_fallback = FakeProvider(
        model=QUOTA_FALLBACK_MODEL,
        outcome=ProviderTransientError(
            "still rate limited", model=QUOTA_FALLBACK_MODEL
        ),
    )
    providers = ProviderChain(
        primary=primary, escalation=escalation, quota_fallback=quota_fallback
    )
    pdf_bytes = make_pdf_bytes(pages=["Stewards Decision Document 42"])

    with pytest.raises(LLMError) as exc_info:
        process_document(pdf_bytes, providers)

    assert isinstance(exc_info.value.__cause__, ProviderTransientError)


@pytest.mark.parametrize("level", ["primary", "escalation"])
def test_permanent_error_fails_fast(level: str) -> None:
    model = PRIMARY_MODEL if level == "primary" else ESCALATION_MODEL
    primary, escalation = _primary_and_escalation(
        level, ProviderPermanentError("bad request", model=model)
    )
    quota_fallback = _unused_provider(QUOTA_FALLBACK_MODEL)
    providers = ProviderChain(
        primary=primary, escalation=escalation, quota_fallback=quota_fallback
    )
    pdf_bytes = make_pdf_bytes(pages=["Stewards Decision Document 42"])

    with pytest.raises(LLMError):
        process_document(pdf_bytes, providers)

    if level == "primary":
        assert escalation.calls == []
        assert quota_fallback.calls == []


def test_escalation_transient_exhaustion() -> None:
    primary = FakeProvider(
        model=PRIMARY_MODEL,
        outcome=ProviderTransientError("rate limited", model=PRIMARY_MODEL),
    )
    escalation = FakeProvider(
        model=ESCALATION_MODEL,
        outcome=ProviderTransientError("still rate limited", model=ESCALATION_MODEL),
    )
    quota_fallback = _unused_provider(QUOTA_FALLBACK_MODEL)
    providers = ProviderChain(
        primary=primary, escalation=escalation, quota_fallback=quota_fallback
    )
    pdf_bytes = make_pdf_bytes(pages=["Stewards Decision Document 42"])

    with pytest.raises(LLMError):
        process_document(pdf_bytes, providers)
