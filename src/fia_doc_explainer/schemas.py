from pydantic import BaseModel, computed_field, model_validator


class ProvideSummary(BaseModel):
    doc_type: str
    source_url: str | None
    key_facts: list[str]
    plain_explanation: str


class FlagLowConfidence(BaseModel):
    reason: str


class LLMResponse(BaseModel):
    summary: ProvideSummary | None = None
    low_confidence_flag: FlagLowConfidence | None = None
    model: str

    @model_validator(mode="after")
    def one_of_two(self):
        if bool(self.summary) is bool(self.low_confidence_flag):
            raise ValueError(
                "Exactly one of summary or low_confidence_flag must be set: "
                f"summary_set={self.summary is not None}, "
                f"low_confidence_flag_set={self.low_confidence_flag is not None}"
            )
        return self


class DocumentSummary(BaseModel):
    doc_type: str
    source_url: str | None
    key_facts: list[str]
    plain_explanation: str
    model_used: str
    low_confidence_reason: str | None
    heuristic_reason: str | None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def low_confidence(self) -> bool:
        return (
            self.low_confidence_reason is not None or self.heuristic_reason is not None
        )
