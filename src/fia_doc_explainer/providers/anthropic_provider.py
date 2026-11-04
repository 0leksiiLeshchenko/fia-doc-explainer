import logging
from typing import Any

import anthropic
from anthropic import Anthropic
from pydantic import BaseModel, ValidationError

from fia_doc_explainer.prompts import (
    FLAG_LOW_CONFIDENCE_DESCRIPTION,
    PROVIDE_SUMMARY_DESCRIPTION,
    SYSTEM_PROMPT,
    build_user_message,
)
from fia_doc_explainer.providers.errors import (
    ProviderPermanentError,
    ProviderQuotaError,
    ProviderResponseError,
    ProviderTransientError,
)
from fia_doc_explainer.retry import retry
from fia_doc_explainer.schemas import FlagLowConfidence, LLMResponse, ProvideSummary

logger = logging.getLogger(__name__)

RETRYABLE_ANTHROPIC_EXCEPTIONS = (
    anthropic.RateLimitError,
    anthropic.InternalServerError,
    anthropic.APITimeoutError,
    anthropic.APIConnectionError,
)

# Unsupported by strict tool use: the API answers 400 if any of these is present.
STRICT_UNSUPPORTED_KEYWORDS = frozenset(
    {
        "minLength",
        "maxLength",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
    }
)

# Keys whose value maps arbitrary names to schemas: the names are not keywords.
_NAMED_SCHEMA_MAPS = frozenset({"properties", "$defs", "definitions"})


def _to_strict(node: Any) -> Any:
    if isinstance(node, list):
        return [_to_strict(item) for item in node]
    if not isinstance(node, dict):
        return node
    result: dict[str, Any] = {}
    for key, value in node.items():
        if key in STRICT_UNSUPPORTED_KEYWORDS:
            continue
        if key in _NAMED_SCHEMA_MAPS and isinstance(value, dict):
            result[key] = {name: _to_strict(sub) for name, sub in value.items()}
        else:
            result[key] = _to_strict(value)
    node_type = result.get("type")
    if node_type == "object" or (isinstance(node_type, list) and "object" in node_type):
        result["additionalProperties"] = False
    return result


def strict_tool_schema(model: type[BaseModel]) -> dict[str, Any]:
    return _to_strict(model.model_json_schema())


def is_quota_error(err: anthropic.BadRequestError) -> bool:
    body = err.body
    message = (
        body.get("error", {}).get("message", "") if isinstance(body, dict) else str(err)
    )
    return "credit balance is too low" in message


class AnthropicProvider:
    def __init__(self, model: str, client: Anthropic | None = None) -> None:
        self.model = model
        self.client = client or Anthropic(max_retries=0)

    @retry(exceptions=RETRYABLE_ANTHROPIC_EXCEPTIONS, max_attempts=5, base_delay=1)
    def _create_message(self, text: str) -> anthropic.types.Message:
        try:
            return self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                tools=[
                    {
                        "name": "provide_summary",
                        "description": PROVIDE_SUMMARY_DESCRIPTION,
                        "strict": True,
                        "input_schema": strict_tool_schema(ProvideSummary),
                    },
                    {
                        "name": "flag_low_confidence",
                        "description": FLAG_LOW_CONFIDENCE_DESCRIPTION,
                        "strict": True,
                        "input_schema": strict_tool_schema(FlagLowConfidence),
                    },
                ],
                tool_choice={"type": "any"},
                messages=[{"role": "user", "content": build_user_message(text)}],
            )
        except anthropic.APIStatusError as e:
            logger.error(
                "Anthropic API error: status=%s body=%s",
                e.status_code,
                e.response.text,
            )
            raise

    def summarize(self, text: str) -> LLMResponse:
        try:
            response = self._create_message(text)
        except anthropic.BadRequestError as err:
            if is_quota_error(err):
                raise ProviderQuotaError(
                    f"Anthropic quota exhausted: {err}", model=self.model
                ) from err
            raise ProviderPermanentError(
                f"Anthropic rejected request: {err}", model=self.model
            ) from err
        except RETRYABLE_ANTHROPIC_EXCEPTIONS as err:
            raise ProviderTransientError(
                f"Anthropic transient failure: {err}", model=self.model
            ) from err

        tool_block = next(
            (block for block in response.content if block.type == "tool_use"),
            None,
        )
        if tool_block is None:
            raise ProviderResponseError(
                f"No tool_use block in response: {response.content!r}",
                model=self.model,
            )

        tool_name = tool_block.name
        try:
            if tool_name == "provide_summary":
                summary = ProvideSummary.model_validate(tool_block.input)
                return LLMResponse(summary=summary, model=self.model)
            elif tool_name == "flag_low_confidence":
                low_confident_flag = FlagLowConfidence.model_validate(tool_block.input)
                return LLMResponse(
                    low_confidence_flag=low_confident_flag, model=self.model
                )
        except ValidationError as e:
            raise ProviderResponseError(
                f"Schema validation failed for tool '{tool_name}': {e}",
                model=self.model,
            ) from e
        raise ProviderResponseError(
            f"Unexpected tool called: {tool_name!r}", model=self.model
        )
