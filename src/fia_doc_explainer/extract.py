import io

import pdfplumber
from pdfplumber.utils.exceptions import PdfminerException


class NoTextLayerError(ValueError):
    def __init__(self, message: str, *args):
        super().__init__(message, *args)

        self.message = message


def extract_text(pdf_bytes: bytes) -> str:
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            text_by_page: list[str] = []
            for page in pdf.pages:
                text_by_page.append(page.extract_text())
    except PdfminerException as exc:
        raise PdfminerException(
            "Error occurred during the provided doc parsing"
        ) from exc

    whole_doc_text = "\n\n".join(text_by_page)
    if not whole_doc_text.strip():
        raise NoTextLayerError(
            message="There's no text in the doc to explain/interpret"
        )

    return whole_doc_text
