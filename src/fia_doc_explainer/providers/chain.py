from dataclasses import dataclass

from fia_doc_explainer.providers.base import LLMProvider


@dataclass(frozen=True)
class ProviderChain:
    primary: LLMProvider
    escalation: LLMProvider
    quota_fallback: LLMProvider
