"""The small real documents an acceptance check uploads: a PDF with a text layer, and a Word file.

`tests/fixtures/documents.py` builds the same two for the unit suite, and `tests/` is not in the
image (`.dockerignore`), so a check running on an install cannot import them. They are written
again here rather than moved, because the fixture module also builds hostile files a product module
has no business shipping. The PDF is written object by object with its offsets counted, since the
product depends on a PDF reader and not on a writer; the Word file is written by python-docx, which
the product already depends on to read one. `tests/unit/test_acceptance.py` holds both to the text
path's own parser, so a builder that drifted from what an upload reads is a failing test and not a
failing check on somebody's server.

Task ids: M38.5.1
"""

from __future__ import annotations

import io
from typing import Final

import docx

#: What separates two lines inside a document built here.
LINE: Final = chr(10)

#: A PDF that opens as a PDF and cannot be read: the header and nothing a reader can parse.
CORRUPT_PDF: Final = b"%PDF-1.4" + bytes(40)


def a_pdf(text: str) -> bytes:
    """A one-page PDF with one line of Helvetica text. No parenthesis or backslash in `text`."""
    if any(one in text for one in "()" + chr(92)):
        msg = "a PDF string here is written unescaped, so it holds no parenthesis or backslash"
        raise ValueError(msg)
    content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"
        ),
        f"<< /Length {len(content)} >>{LINE}stream{LINE}".encode()
        + content
        + f"{LINE}endstream".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(f"%PDF-1.4{LINE}".encode())
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{number} 0 obj{LINE}".encode() + body + f"{LINE}endobj{LINE}".encode())
    xref = out.tell()
    out.write(f"xref{LINE}0 {len(objects) + 1}{LINE}".encode())
    out.write(f"0000000000 65535 f {LINE}".encode())
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n {LINE}".encode())
    out.write(
        (
            f"trailer{LINE}<< /Size {len(objects) + 1} /Root 1 0 R >>{LINE}"
            f"startxref{LINE}{xref}{LINE}%%EOF{LINE}"
        ).encode()
    )
    return out.getvalue()


def a_word_document(heading: str, paragraph: str) -> bytes:
    """A Word file holding one heading and one paragraph."""
    document = docx.Document()
    document.add_heading(heading, level=1)
    document.add_paragraph(paragraph)
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


def a_markdown_document(heading: str, paragraph: str) -> bytes:
    """A Markdown file holding one heading and one paragraph."""
    return LINE.join((f"# {heading}", "", paragraph, "")).encode("utf-8")
