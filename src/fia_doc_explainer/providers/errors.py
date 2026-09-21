class ProviderError(Exception):
    """Base for all provider failures; carries the model that raised it."""

    def __init__(self, message: str, *, model: str):
        super().__init__(message)
        self.message = message
        self.model = model


class ProviderQuotaError(ProviderError):
    """Vendor quota/balance exhausted: switch to a fallback provider, do not retry."""


class ProviderTransientError(ProviderError):
    """Temporary failure with retries already exhausted: escalate or fail the request."""


class ProviderPermanentError(ProviderError):
    """Request is invalid: retrying will not help, surface the error."""


class ProviderResponseError(ProviderError):
    """Response received but unusable (no tool_use block, unknown tool): treat as failure, may escalate."""
