from pydantic import BaseModel, Field, computed_field, model_validator


# No source_url here: the prompt never contains the URL, so the model
# can't be asked for it. The caller supplies it; see DocumentSummary.
class ProvideSummary(BaseModel):
    doc_type: str = Field(
        description="The kind of FIA document this is, in the wording the document uses for itself — "
        "for example 'Stewards Decision', 'Technical Directive', 'Competition Note'. "
        "Keep it short. Do not invent a category of your own."
    )
    key_facts: list[str] = Field(
        description="The facts a reader needs in order to know what this document decides: "
        "who or what it applies to, which event and session the document concerns, what was decided, and on what grounds. "
        "Three to six items, each a complete sentence. "
        "Leave out procedural boilerplate such as appeal rights or "
        "which evidence was reviewed, unless the decision turns on it."
    )
    plain_explanation: str = Field(
        description="Plain-language explanation of the document for the reader described in the system prompt. "
        "It names the event and session the document concerns, where the document states them. "
        "If the document is simple — an engine changed on a given car, "
        "a driver given a grid penalty of N places — it states the meaning briefly "
        "instead of padding it out, and adds no background the document does not support."
    )


class FlagLowConfidence(BaseModel):
    reason: str = Field(
        description="What specifically is wrong with the input, in one or two sentences. "
        "Name the problem, not your impression of it: which part of the text is garbled, "
        "which numbers cannot be attributed to rows or columns, "
        "or what the text appears to be instead of an FIA document."
    )


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
