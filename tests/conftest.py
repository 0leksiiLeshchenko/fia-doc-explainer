import io
import os

import reportlab
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

VERA_TTF = os.path.join(os.path.dirname(reportlab.__file__), "fonts", "Vera.ttf")
pdfmetrics.registerFont(TTFont("Vera", VERA_TTF))


def make_pdf_bytes(
    pages: list[str | None], is_broken: bool = False, font: str | None = None
) -> bytes:
    """Build a synthetic in-memory PDF for tests.

    Args:
        pages: One entry per page. A string draws that text on the page;
            None produces a page with no text objects at all (simulates
            a PDF with no extractable text layer, e.g. a scan).
        is_broken: If True, truncate the finished PDF to half its length,
            simulating a corrupted/incomplete file (e.g. a truncated
            download) that pdfplumber cannot parse.
        font: Optional font name to draw with, e.g. "Vera" (bundled with
            reportlab, registered above). Glyphs the font can't encode come
            back from extraction as \\x00, which is how tests produce real
            non-printable characters — Helvetica/WinAnsi never round-trips
            them.

    Returns:
        Raw PDF bytes, ready to wrap in io.BytesIO for pdfplumber.
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(612, 792))

    for page_content in pages:
        if page_content:
            if font:
                c.setFont(font, 12)
            c.drawString(50, 600, page_content)
        c.showPage()

    c.save()
    pdf_bytes = buf.getvalue()

    if is_broken:
        pdf_bytes = pdf_bytes[: len(pdf_bytes) // 2]

    return pdf_bytes
