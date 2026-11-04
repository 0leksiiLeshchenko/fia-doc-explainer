from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
import pytest
from anthropic.types import ToolUseBlock
from pydantic import BaseModel, Field, ValidationError

from fia_doc_explainer.providers.anthropic_provider import (
    STRICT_UNSUPPORTED_KEYWORDS,
    AnthropicProvider,
    strict_tool_schema,
)
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


def test_summarize_raises_response_error_on_invalid_provide_summary_args(
    provider,
) -> None:
    provider_instance, mock_client = provider
    tool_block = ToolUseBlock(
        id="toolu_3",
        name="provide_summary",
        type="tool_use",
        input={
            "key_facts": ["Kimi won", "Lewis - DNF", "Stroll - GOAT"],
            "plain_explanation": "Race was super boring",
        },
    )
    response = SimpleNamespace(content=[tool_block])
    mock_client.messages.create.return_value = response

    with pytest.raises(
        ProviderResponseError,
        match=r"^Schema validation failed for tool 'provide_summary'",
    ):
        provider_instance.summarize("FIA doc text version")


def test_summarize_raises_response_error_on_invalid_flag_args(provider) -> None:
    provider_instance, mock_client = provider
    tool_block = ToolUseBlock(
        id="toolu_4",
        name="flag_low_confidence",
        type="tool_use",
        input={"error": "low_confidence"},
    )
    response = SimpleNamespace(content=[tool_block])
    mock_client.messages.create.return_value = response

    with pytest.raises(
        ProviderResponseError,
        match=r"^Schema validation failed for tool 'flag_low_confidence'",
    ):
        provider_instance.summarize("FIA doc text version")


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


def test_empty_low_confidence_reason_raises_ValidationError() -> None:
    with pytest.raises(ValidationError):
        FlagLowConfidence(reason="")


class _Inner(BaseModel):
    name: str = Field(min_length=2, max_length=9)
    score: int = Field(ge=0, le=10, multiple_of=2)


class _Outer(BaseModel):
    inner: _Inner
    items: list[_Inner]
    ratio: float = Field(gt=0, lt=1)


def _walk(node: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(node, dict):
        found.append(node)
        for value in node.values():
            found.extend(_walk(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_walk(item))
    return found


def _assert_strict_compatible(schema: dict[str, Any]) -> None:
    for node in _walk(schema):
        assert not STRICT_UNSUPPORTED_KEYWORDS & node.keys()
        if node.get("type") == "object":
            assert node["additionalProperties"] is False


@pytest.mark.parametrize("model", [FlagLowConfidence, ProvideSummary])
def test_strict_schema_of_real_models_is_compatible(model: type[BaseModel]) -> None:
    _assert_strict_compatible(strict_tool_schema(model))


def test_strict_schema_strips_nested_constraints() -> None:
    original = _Outer.model_json_schema()
    assert any("minLength" in n for n in _walk(original))

    schema = strict_tool_schema(_Outer)

    _assert_strict_compatible(schema)
    assert "_Inner" in schema["$defs"]
    assert schema["$defs"]["_Inner"]["additionalProperties"] is False


def test_strict_schema_keeps_property_named_like_a_keyword() -> None:
    class Odd(BaseModel):
        minimum: int

    schema = strict_tool_schema(Odd)
    assert "minimum" in schema["properties"]


def test_strict_schema_does_not_mutate_source_schema() -> None:
    before = FlagLowConfidence.model_json_schema()
    assert before["properties"]["reason"]["minLength"] == 1

    strict_tool_schema(FlagLowConfidence)

    after = FlagLowConfidence.model_json_schema()
    assert after == before
    assert after["properties"]["reason"]["minLength"] == 1
    assert "additionalProperties" not in after


def test_empty_reason_still_fails_model_validate() -> None:
    with pytest.raises(ValidationError):
        FlagLowConfidence.model_validate({"reason": ""})


class _FakeMessages:
    def __init__(self, response: SimpleNamespace) -> None:
        self.response = response
        self.kwargs: dict[str, Any] = {}

    def create(self, **kwargs: Any) -> SimpleNamespace:
        self.kwargs = kwargs
        return self.response


class _FakeClient:
    def __init__(self, response: SimpleNamespace) -> None:
        self.messages = _FakeMessages(response)


def _tool_response(name: str, tool_input: dict[str, Any]) -> SimpleNamespace:
    block = ToolUseBlock(id="toolu_x", name=name, type="tool_use", input=tool_input)
    return SimpleNamespace(content=[block])


def test_summarize_sends_both_tools_as_strict_without_min_length() -> None:
    client = _FakeClient(_tool_response("flag_low_confidence", {"reason": "garbled"}))
    provider_instance = AnthropicProvider(
        model="claude-haiku-4-5",
        client=client,  # type: ignore[arg-type]
    )

    provider_instance.summarize("FIA doc text version")

    tools = client.messages.kwargs["tools"]
    assert {t["name"] for t in tools} == {"provide_summary", "flag_low_confidence"}
    for tool in tools:
        assert tool["strict"] is True
        _assert_strict_compatible(tool["input_schema"])
        assert "minLength" not in str(tool["input_schema"])


def test_summarize_raises_response_error_on_empty_reason_from_strict_tool() -> None:
    client = _FakeClient(_tool_response("flag_low_confidence", {"reason": ""}))
    provider_instance = AnthropicProvider(
        model="claude-haiku-4-5",
        client=client,  # type: ignore[arg-type]
    )

    with pytest.raises(
        ProviderResponseError,
        match=r"^Schema validation failed for tool 'flag_low_confidence'",
    ):
        provider_instance.summarize("FIA doc text version")
