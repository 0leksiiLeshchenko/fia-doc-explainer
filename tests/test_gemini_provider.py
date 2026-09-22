from types import SimpleNamespace

import pytest
from google.genai import types

from fia_doc_explainer.providers.gemini_provider import GeminiProvider
from fia_doc_explainer.schemas import FlagLowConfidence, LLMResponse, ProvideSummary


@pytest.fixture
def provider(mocker):
    mock_client_class = mocker.patch(
        "fia_doc_explainer.providers.gemini_provider.genai.Client"
    )
    mock_client = mock_client_class.return_value
    return (
        GeminiProvider(model="gemini-3.5-flash-lite", client=mock_client),
        mock_client,
    )


def test_summarize_returns_provide_summary_on_valid_input(provider) -> None:
    provider_instance, mock_client = provider
    call = types.FunctionCall(
        name="provide_summary",
        args={
            "doc_type": "Classification & Results",
            "source_url": "https://www.fia.com/system/files/decision-document/2026_spanish_grand_prix_-_final_race_classification.pdf",
            "key_facts": ["Kimi won", "Lewis - DNF", "Stroll - GOAT"],
            "plain_explanation": "Race was super boring",
        },
    )
    response = SimpleNamespace(function_calls=[call])
    mock_client.models.generate_content.return_value = response

    result = provider_instance.summarize("FIA doc text version")
    assert isinstance(result, LLMResponse)
    assert isinstance(result.summary, ProvideSummary)
    assert result.summary.doc_type == "Classification & Results"
    assert result.summary.plain_explanation == "Race was super boring"
    assert result.low_confidence_flag is None


def test_summarize_returns_flag_low_confidence_on_valid_input(provider) -> None:
    provider_instance, mock_client = provider
    call = types.FunctionCall(
        name="flag_low_confidence",
        args={"reason": "Not sure about doc type; too many tables"},
    )
    response = SimpleNamespace(function_calls=[call])
    mock_client.models.generate_content.return_value = response

    result = provider_instance.summarize("FIA doc text version")
    assert isinstance(result, LLMResponse)
    assert isinstance(result.low_confidence_flag, FlagLowConfidence)
    assert (
        result.low_confidence_flag.reason == "Not sure about doc type; too many tables"
    )
    assert result.summary is None
