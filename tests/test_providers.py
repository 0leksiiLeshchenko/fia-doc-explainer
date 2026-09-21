from types import SimpleNamespace

import anthropic
import httpx2
import pytest
from anthropic.types import ToolUseBlock

from fia_doc_explainer.providers.anthropic_provider import AnthropicProvider
from fia_doc_explainer.providers.errors import (
    ProviderPermanentError,
    ProviderQuotaError,
    ProviderResponseError,
    ProviderTransientError,
)
from fia_doc_explainer.schemas import FlagLowConfidence, LLMResponse, ProvideSummary


@pytest.fixture
def provider(mocker):
    mock_client_class = mocker.patch(
        "fia_doc_explainer.providers.anthropic_provider.Anthropic"
    )
    mock_client = mock_client_class.return_value
    return AnthropicProvider(model="claude-haiku-4-5", client=mock_client), mock_client


def test_summarize_returns_provide_summary_on_valid_input(provider) -> None:
    provider_instance, mock_client = provider
    tool_block = ToolUseBlock(
        id="toolu_1",
        name="provide_summary",
        type="tool_use",
        input={
            "doc_type": "Classification & Results",
            "source_url": "https://www.fia.com/system/files/decision-document/2026_spanish_grand_prix_-_final_race_classification.pdf",
            "key_facts": ["Kimi won", "Lewis - DNF", "Stroll - GOAT"],
            "plain_explanation": "Race was super boring",
        },
    )
    response = SimpleNamespace(content=[tool_block])
    mock_client.messages.create.return_value = response

    result = provider_instance.summarize("FIA doc text version")
    assert isinstance(result, LLMResponse)
    assert isinstance(result.summary, ProvideSummary)
    assert result.summary.doc_type == "Classification & Results"
    assert result.summary.plain_explanation == "Race was super boring"
    assert result.low_confidence_flag is None


def test_summarize_returns_flag_low_confidence_on_valid_input(provider) -> None:
    provider_instance, mock_client = provider
    tool_block = ToolUseBlock(
        id="toolu_2",
        name="flag_low_confidence",
        type="tool_use",
        input={"reason": "Not sure about doc type; too many tables"},
    )
    response = SimpleNamespace(content=[tool_block])
    mock_client.messages.create.return_value = response

    result = provider_instance.summarize("FIA doc text version")
    assert isinstance(result, LLMResponse)
    assert isinstance(result.low_confidence_flag, FlagLowConfidence)
    assert (
        result.low_confidence_flag.reason == "Not sure about doc type; too many tables"
    )
    assert result.summary is None


def test_summarize_returns_provide_summary_with_incorrect_args(provider) -> None:
    provider_instance, mock_client = provider
    tool_block = ToolUseBlock(
        id="toolu_3",
        name="provide_summary",
        type="tool_use",
        input={
            "source_url": "https://www.fia.com/system/files/decision-document/2026_spanish_grand_prix_-_final_race_classification.pdf",
            "key_facts": ["Kimi won", "Lewis - DNF", "Stroll - GOAT"],
            "plain_explanation": "Race was super boring",
        },
    )
    response = SimpleNamespace(content=[tool_block])
    mock_client.messages.create.return_value = response

    result = provider_instance.summarize("FIA doc text version")
    assert isinstance(result, LLMResponse)
    assert isinstance(result.low_confidence_flag, FlagLowConfidence)
    assert result.low_confidence_flag.reason.startswith(
        "Schema validation failed for tool 'provide_summary'"
    )
    assert result.summary is None


def test_summarize_returns_low_confident_flag_with_incorrect_args(provider) -> None:
    provider_instance, mock_client = provider
    tool_block = ToolUseBlock(
        id="toolu_4",
        name="flag_low_confidence",
        type="tool_use",
        input={"error": "low_confidence"},
    )
    response = SimpleNamespace(content=[tool_block])
    mock_client.messages.create.return_value = response

    result = provider_instance.summarize("FIA doc text version")
    assert isinstance(result, LLMResponse)
    assert isinstance(result.low_confidence_flag, FlagLowConfidence)
    assert result.low_confidence_flag.reason.startswith(
        "Schema validation failed for tool 'flag_low_confidence'"
    )
    assert result.summary is None


def test_summarize_returns_unexpected_tool_name(provider) -> None:
    provider_instance, mock_client = provider
    tool_block = ToolUseBlock(
        id="toolu_5",
        name="doc_summary",
        type="tool_use",
        input={"summary": "Madrid race was great"},
    )
    response = SimpleNamespace(content=[tool_block])
    mock_client.messages.create.return_value = response

    with pytest.raises(ProviderResponseError) as err:
        provider_instance.summarize("FIA doc text version")
    assert err.value.args[0] == "Unexpected tool called: 'doc_summary'"


def test_summarize_returns_no_tool_use_block(provider) -> None:
    provider_instance, mock_client = provider
    response = SimpleNamespace(content=[])
    mock_client.messages.create.return_value = response

    with pytest.raises(ProviderResponseError) as err:
        provider_instance.summarize("FIA doc text version")
    assert err.value.args[0] == "No tool_use block in response: []"


def _api_status_error(
    cls: type[anthropic.APIStatusError], status_code: int, message: str
) -> anthropic.APIStatusError:
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx2.Response(status_code, request=request)
    body = {"error": {"type": "error", "message": message}}
    return cls(message, response=response, body=body)


def test_summarize_translates_quota_error(provider, mocker) -> None:
    provider_instance, _ = provider
    original = _api_status_error(
        anthropic.BadRequestError, 400, "Your credit balance is too low"
    )
    mocker.patch.object(provider_instance, "_create_message", side_effect=original)

    with pytest.raises(ProviderQuotaError) as err:
        provider_instance.summarize("FIA doc text version")
    assert err.value.model == "claude-haiku-4-5"
    assert "credit balance is too low" in err.value.message
    assert err.value.__cause__ is original


def test_summarize_translates_bad_request_to_permanent_error(provider, mocker) -> None:
    provider_instance, _ = provider
    original = _api_status_error(
        anthropic.BadRequestError, 400, "max_tokens must be positive"
    )
    mocker.patch.object(provider_instance, "_create_message", side_effect=original)

    with pytest.raises(ProviderPermanentError) as err:
        provider_instance.summarize("FIA doc text version")
    assert err.value.model == "claude-haiku-4-5"
    assert "max_tokens must be positive" in err.value.message
    assert err.value.__cause__ is original


def test_summarize_translates_retryable_error_to_transient_error(
    provider, mocker
) -> None:
    provider_instance, _ = provider
    original = _api_status_error(anthropic.RateLimitError, 429, "Rate limited")
    mocker.patch.object(provider_instance, "_create_message", side_effect=original)

    with pytest.raises(ProviderTransientError) as err:
        provider_instance.summarize("FIA doc text version")
    assert err.value.model == "claude-haiku-4-5"
    assert "Rate limited" in err.value.message
    assert err.value.__cause__ is original
