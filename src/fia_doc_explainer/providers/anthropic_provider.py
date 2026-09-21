import logging

import anthropic
from anthropic import Anthropic
from pydantic import ValidationError

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
                tools=[
                    {
                        "name": "provide_summary",
                        "description": "Provide summary of the given FIA document if you are confident you understood it",
                        "input_schema": ProvideSummary.model_json_schema(),
                    },
                    {
                        "name": "flag_low_confidence",
                        "description": "Provide a low confidence reason if you don't clearly understand a given FIA doc and can't explain it's content and meaning",
                        "input_schema": FlagLowConfidence.model_json_schema(),
                    },
                ],
                tool_choice={"type": "any"},
                messages=[{"role": "user", "content": text}],
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
            reason = f"Schema validation failed for tool '{tool_name}': {e}"
            return LLMResponse(
                low_confidence_flag=FlagLowConfidence(reason=reason), model=self.model
            )
        raise ProviderResponseError(
            f"Unexpected tool called: {tool_name!r}", model=self.model
        )
