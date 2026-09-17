import io

import pytest
from pdfplumber.utils.exceptions import PdfminerException
from reportlab.pdfgen import canvas

from fia_doc_explainer.extract import NoTextLayerError, extract_text


def make_pdf_bytes(pages: list[str | None], is_broken: bool = False) -> bytes:
    """Build a synthetic in-memory PDF for tests.

    Args:
        pages: One entry per page. A string draws that text on the page;
            None produces a page with no text objects at all (simulates
            a PDF with no extractable text layer, e.g. a scan).
        is_broken: If True, truncate the finished PDF to half its length,
            simulating a corrupted/incomplete file (e.g. a truncated
            download) that pdfplumber cannot parse.

    Returns:
        Raw PDF bytes, ready to wrap in io.BytesIO for pdfplumber.
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(612, 792))

    for page_content in pages:
        if page_content:
            c.drawString(50, 600, page_content)
        c.showPage()

    c.save()
    pdf_bytes = buf.getvalue()

    if is_broken:
        pdf_bytes = pdf_bytes[: len(pdf_bytes) // 2]

    return pdf_bytes


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
