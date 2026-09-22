from google import genai
from google.genai import types
from pydantic import ValidationError

from fia_doc_explainer.providers.errors import ProviderResponseError
from fia_doc_explainer.schemas import FlagLowConfidence, LLMResponse, ProvideSummary


class GeminiProvider:
    def __init__(self, model: str, client: genai.Client | None = None) -> None:
        self.model = model
        self.client = client or genai.Client()

    def summarize(self, text: str) -> LLMResponse:
        response = self.client.models.generate_content(
            model=self.model,
            contents=text,
            config=types.GenerateContentConfig(
                tools=[
                    types.Tool(
                        function_declarations=[
                            types.FunctionDeclaration(
                                name="provide_summary",
                                description="Provide summary of the given FIA document if you are confident you understood it",
                                parameters_json_schema=ProvideSummary.model_json_schema(),
                            ),
                            types.FunctionDeclaration(
                                name="flag_low_confidence",
                                description="Provide a low confidence reason if you don't clearly understand a given FIA doc and can't explain it's content and meaning",
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
