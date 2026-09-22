from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from fia_doc_explainer.schemas import FlagLowConfidence, LLMResponse, ProvideSummary


@dataclass
class FakeProvider:
    model: str
    outcome: LLMResponse | Exception
    calls: list[str] = field(default_factory=list)

    def summarize(self, text: str) -> LLMResponse:
        self.calls.append(text)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def summary_response(
    model: str, doc_type: str = "Decision", source_url: str | None = None
) -> LLMResponse:
    return LLMResponse(
        summary=ProvideSummary(
            doc_type=doc_type,
            source_url=source_url,
            key_facts=["Kimi won", "Lewis - DNF"],
            plain_explanation="Race was super boring",
        ),
        model=model,
    )


def flag_response(model: str, reason: str) -> LLMResponse:
    return LLMResponse(
        low_confidence_flag=FlagLowConfidence(reason=reason), model=model
    )


if TYPE_CHECKING:
    from fia_doc_explainer.providers.base import LLMProvider

    _protocol_check: LLMProvider = FakeProvider(model="x", outcome=Exception("x"))
