import pytest
from pdfplumber.utils.exceptions import PdfminerException

from fia_doc_explainer.extract import NoTextLayerError, extract_text
from tests.conftest import make_pdf_bytes


def test_extract_text_from_correct_pdf_bytes() -> None:
    test_pdf_text = [
        "Official FIA doc",
        "Hamilton wins in Barcelona 2026",
        "Leclerc DNF",
        "Antonelli DNF",
    ]
    pdf_bytes: bytes = make_pdf_bytes(pages=test_pdf_text)
    result = extract_text(pdf_bytes)
    assert result == "\n\n".join(test_pdf_text)


def test_extract_text_fails_on_broken_pdf() -> None:
    test_pdf_text = [
        "Official FIA doc",
        "Hamilton wins in Barcelona 2026",
        "Leclerc DNF",
        "Antonelli DNF",
    ]
    pdf_bytes: bytes = make_pdf_bytes(pages=test_pdf_text, is_broken=True)
    with pytest.raises(
        PdfminerException, match="Error occurred during the provided doc parsing"
    ):
        extract_text(pdf_bytes)


def test_extract_text_fails_with_no_text() -> None:
    pdf_bytes: bytes = make_pdf_bytes(pages=[None])
    with pytest.raises(
        NoTextLayerError, match="There's no text in the doc to explain/interpret"
    ):
        extract_text(pdf_bytes)
