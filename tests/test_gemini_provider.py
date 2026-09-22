from types import SimpleNamespace

import pytest
from google.genai import errors, types

from fia_doc_explainer.providers.errors import (
    ProviderPermanentError,
    ProviderQuotaError,
    ProviderResponseError,
    ProviderTransientError,
)
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


def test_summarize_returns_provide_summary_with_incorrect_args(provider) -> None:
    provider_instance, mock_client = provider
    call = types.FunctionCall(
        name="provide_summary",
        args={
            "source_url": "https://www.fia.com/system/files/decision-document/2026_spanish_grand_prix_-_final_race_classification.pdf",
            "key_facts": ["Kimi won", "Lewis - DNF", "Stroll - GOAT"],
            "plain_explanation": "Race was super boring",
        },
    )
    response = SimpleNamespace(function_calls=[call])
    mock_client.models.generate_content.return_value = response

    result = provider_instance.summarize("FIA doc text version")
    assert isinstance(result, LLMResponse)
    assert isinstance(result.low_confidence_flag, FlagLowConfidence)
    assert result.low_confidence_flag.reason.startswith(
        "Schema validation failed for tool 'provide_summary'"
    )
    assert result.summary is None


def test_summarize_returns_low_confident_flag_with_incorrect_args(provider) -> None:
    provider_instance, mock_client = provider
    call = types.FunctionCall(
        name="flag_low_confidence", args={"error": "low_confidence"}
    )
    response = SimpleNamespace(function_calls=[call])
    mock_client.models.generate_content.return_value = response

    result = provider_instance.summarize("FIA doc text version")
    assert isinstance(result, LLMResponse)
    assert isinstance(result.low_confidence_flag, FlagLowConfidence)
    assert result.low_confidence_flag.reason.startswith(
        "Schema validation failed for tool 'flag_low_confidence'"
    )
    assert result.summary is None


def test_summarize_returns_unexpected_tool_name(provider) -> None:
    provider_instance, mock_client = provider
    call = types.FunctionCall(
        name="doc_summary", args={"summary": "Madrid race was great"}
    )
    response = SimpleNamespace(function_calls=[call])
    mock_client.models.generate_content.return_value = response

    with pytest.raises(ProviderResponseError) as err:
        provider_instance.summarize("FIA doc text version")
    assert err.value.args[0] == "Unexpected tool called: 'doc_summary'"


def test_summarize_returns_no_function_calls(provider) -> None:
    provider_instance, mock_client = provider
    response = SimpleNamespace(function_calls=[])
    mock_client.models.generate_content.return_value = response

    with pytest.raises(ProviderResponseError) as err:
        provider_instance.summarize("FIA doc text version")
    assert err.value.args[0] == "No function call in response: []"


def test_summarize_translates_rate_limit_to_transient_error(provider, mocker) -> None:
    provider_instance, mock_client = provider
    mocker.patch("fia_doc_explainer.retry.sleep")
    original = errors.ClientError(
        429, {"error": {"status": "RESOURCE_EXHAUSTED", "message": "Quota exceeded"}}
    )
    mock_client.models.generate_content.side_effect = original

    with pytest.raises(ProviderTransientError) as err:
        provider_instance.summarize("FIA doc text version")
    assert err.value.model == "gemini-3.5-flash-lite"
    assert "Quota exceeded" in err.value.message


def test_summarize_translates_server_error_to_transient_error(provider, mocker) -> None:
    provider_instance, mock_client = provider
    mocker.patch("fia_doc_explainer.retry.sleep")
    original = errors.ServerError(
        500, {"error": {"status": "INTERNAL", "message": "Internal error"}}
    )
    mock_client.models.generate_content.side_effect = original

    with pytest.raises(ProviderTransientError) as err:
        provider_instance.summarize("FIA doc text version")
    assert err.value.model == "gemini-3.5-flash-lite"
    assert "Internal error" in err.value.message
    assert err.value.__cause__ is original


def test_summarize_translates_client_error_to_permanent_error(provider) -> None:
    provider_instance, mock_client = provider
    original = errors.ClientError(
        400, {"error": {"status": "INVALID_ARGUMENT", "message": "Bad request"}}
    )
    mock_client.models.generate_content.side_effect = original

    with pytest.raises(ProviderPermanentError) as err:
        provider_instance.summarize("FIA doc text version")
    assert err.value.model == "gemini-3.5-flash-lite"
    assert "Bad request" in err.value.message
    assert err.value.__cause__ is original


def test_summarize_never_raises_quota_error(provider, mocker) -> None:
    provider_instance, mock_client = provider
    mocker.patch("fia_doc_explainer.retry.sleep")
    scenarios = [
        errors.ClientError(
            429,
            {"error": {"status": "RESOURCE_EXHAUSTED", "message": "Quota exceeded"}},
        ),
        errors.ServerError(
            500, {"error": {"status": "INTERNAL", "message": "Internal error"}}
        ),
        errors.ClientError(
            400, {"error": {"status": "INVALID_ARGUMENT", "message": "Bad request"}}
        ),
    ]

    for scenario in scenarios:
        mock_client.models.generate_content.side_effect = scenario
        with pytest.raises(Exception) as err:
            provider_instance.summarize("FIA doc text version")
        assert not isinstance(err.value, ProviderQuotaError)
        assert isinstance(err.value, (ProviderTransientError, ProviderPermanentError))
