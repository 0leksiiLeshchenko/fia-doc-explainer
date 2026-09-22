import httpx
from google import genai
from google.genai import types
from pydantic import ValidationError

from fia_doc_explainer.providers.errors import (
    ProviderPermanentError,
    ProviderResponseError,
    ProviderTransientError,
)
from fia_doc_explainer.retry import retry
from fia_doc_explainer.schemas import FlagLowConfidence, LLMResponse, ProvideSummary


class _RateLimited(Exception):
    """Marker for genai.errors.ClientError(code=429): free-tier quota and rate limit are indistinguishable."""


RETRYABLE_GEMINI_EXCEPTIONS = (
    genai.errors.ServerError,
    _RateLimited,
    httpx.TimeoutException,
    httpx.ConnectError,
)


class GeminiProvider:
    def __init__(self, model: str, client: genai.Client | None = None) -> None:
        self.model = model
        self.client = client or genai.Client()

    @retry(exceptions=RETRYABLE_GEMINI_EXCEPTIONS, max_attempts=5, base_delay=1)
    def _generate_content(self, text: str) -> types.GenerateContentResponse:
        try:
            return self.client.models.generate_content(
                model=self.model,
                contents=text,
                config=types.GenerateContentConfig(
                    tools=[
                        types.Tool(
                            function_declarations=[
                                types.FunctionDeclaration(
                                    name="provide_summary",
                                    description="Provide summary of the given FIA document if you are confident you understood it",
                                    # verified against the live API on 2026-09-22: parameters_json_schema=
                                    # accepts anyOf for source_url: str | None
                                    parameters_json_schema=ProvideSummary.model_json_schema(),
                                ),
                                types.FunctionDeclaration(
                                    name="flag_low_confidence",
                                    description="Provide a low confidence reason if you don't clearly understand a given FIA doc and can't explain it's content and meaning",
                                    # verified against the live API on 2026-09-22: parameters_json_schema=
                                    # accepts anyOf for source_url: str | None
                                    parameters_json_schema=FlagLowConfidence.model_json_schema(),
                                ),
                            ]
                        )
                    ],
                    tool_config=types.ToolConfig(
                        function_calling_config=types.FunctionCallingConfig(
                            mode=types.FunctionCallingConfigMode.ANY,
                        )
                    ),
                ),
            )
        except genai.errors.ClientError as e:
            if e.code == 429:
                raise _RateLimited(str(e)) from e
            raise

    def summarize(self, text: str) -> LLMResponse:
        try:
            response = self._generate_content(text)
        except (_RateLimited, genai.errors.ServerError) as err:
            raise ProviderTransientError(
                f"Gemini transient failure: {err}", model=self.model
            ) from err
        except genai.errors.ClientError as err:
            raise ProviderPermanentError(
                f"Gemini rejected request: {err}", model=self.model
            ) from err

        function_calls = response.function_calls
        if not function_calls:
            raise ProviderResponseError(
                f"No function call in response: {function_calls!r}",
                model=self.model,
            )

        call = function_calls[0]
        tool_name = call.name
        try:
            if tool_name == "provide_summary":
                summary = ProvideSummary.model_validate(call.args)
                return LLMResponse(summary=summary, model=self.model)
            elif tool_name == "flag_low_confidence":
                low_confident_flag = FlagLowConfidence.model_validate(call.args)
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
