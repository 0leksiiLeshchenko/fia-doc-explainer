class DocumentProcessingError(Exception):
    def __init__(self, message: str, *args) -> None:
        super().__init__(message, *args)

        self.message = message


class DownloadError(DocumentProcessingError): ...


class ExtractionError(DocumentProcessingError): ...


class LLMError(DocumentProcessingError): ...
