from typing import Protocol

from fia_doc_explainer.schemas import LLMResponse


class LLMProvider(Protocol):
    def summarize(self, text: str) -> LLMResponse: ...
