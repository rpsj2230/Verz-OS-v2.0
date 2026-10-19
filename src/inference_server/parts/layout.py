"""The layout part: a page's regions, reading order and tables, read by Docling on a CPU.

**Never run against the real library.** Nothing in this repository has installed Docling, so the
calls into it (`DocumentConverter`, `PdfPipelineOptions`, `iterate_items`) are written from its
documented interface and have not been executed, and the tests drive the rest of the part through
a stand-in for the one object that touches it. The first install that switches this part on is
the first run; `docs/needs-rupash.md` item 240 says so, and the weights it needs are fetched by a
step that is also unrun.

**OCR is switched off inside it, on purpose.** Docling can run an OCR engine over a page with no
text, and doing it here would make a scanned document read by this part and recorded as a layout
reading, which is the quiet quality change `brain.knowledge.parse_paths` exists to prevent. With it
off, a PDF with no text layer comes back with no blocks, the application turns that into
`no_text_layer`, and the route sends it to the scanned-page part, which records that its text was
guessed.

**It answers with the four causes it may declare and nothing it was told.** A password-protected
PDF is `encrypted` and a file the library could not open is `corrupt`; any other exception is this
process failing, which the worker reports as an outage and the application retries, and the text of
it is never sent because a parser's message quotes the file.

**A heading is a block and also the section of what follows it.** The citation names the section a
passage came from, so every block after a heading carries the heading's words (cut to the column's
width), and the heading itself is indexed as prose so a search for it finds it.

Task ids: M7.2.1
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Protocol

from inference_server.config import ServerConfig
from inference_server.parts.documents import (
    OUR_OWN_MISTAKES,
    BadRequest,
    Draft,
    Unreadable,
    as_file,
    bad_request,
    blocks_answer,
    laid_out,
    read_document,
    refusal,
    refusal_for,
)
from inference_server.worker import Answer

#: The name the application records as the model that read a document, and the weights directory
#: under the models volume. Spelled as `brain.knowledge.parse_layout.LAYOUT_ENGINE`.
LABEL: Final = "docling-layout-and-tableformer"
WEIGHTS_DIRECTORY: Final = "docling"

#: Docling's labels for the items that are a heading, a table and a thing to leave out. Everything
#: else is prose. A label this program does not know is read as prose rather than dropped: a
#: dropped block is text that is not searchable while the document reads as indexed.
HEADING_LABELS: Final = frozenset({"title", "section_header"})
TABLE_LABELS: Final = frozenset({"table"})
LEFT_OUT_LABELS: Final = frozenset({"page_header", "page_footer", "picture", "footnote"})


@dataclass(frozen=True)
class Item:
    """One thing the library found, reduced to the four facts a block needs."""

    label: str
    text: str
    page: int | None


class Reader(Protocol):
    """What reads a file into items. The real one is Docling's; a test supplies its own."""

    def read(self, path: Path) -> Sequence[Item]: ...


def drafts_from(items: Iterable[Item]) -> list[Draft]:
    """Items in reading order as drafts, each carrying the section its heading opened."""
    drafts: list[Draft] = []
    section = ""
    for item in items:
        if item.label in LEFT_OUT_LABELS:
            continue
        if item.label in HEADING_LABELS:
            section = " ".join(item.text.split())
        kind = "table" if item.label in TABLE_LABELS else "prose"
        drafts.append(Draft(text=item.text, kind=kind, page=item.page, section=section))
    return drafts


class LayoutBackend:
    """`Backend`: reads one document into blocks, or says in the four words why it cannot."""

    def __init__(self, reader: Reader, label: str = LABEL) -> None:
        self._reader = reader
        self.label = label

    def handle(self, body: bytes) -> Answer:
        try:
            document = read_document(body)
            with as_file(document) as path:
                items = self._reader.read(path)
        except BadRequest as error:
            return bad_request(error)
        except Unreadable as error:
            return refusal(error.cause, error.stage)
        return blocks_answer(laid_out(drafts_from(items)))


class DoclingReader:
    """The one object that touches Docling. Imported only when a layout part is loaded."""

    def __init__(self, weights: Path) -> None:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption

        options = PdfPipelineOptions(artifacts_path=str(weights), do_ocr=False)
        self._converter: Any = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
        )

    def read(self, path: Path) -> Sequence[Item]:
        try:
            result = self._converter.convert(str(path))
        except OUR_OWN_MISTAKES:
            raise
        except Exception as error:
            raise refusal_for(error, stage="layout") from None
        document = result.document
        items: list[Item] = []
        for node, _level in document.iterate_items():
            label = str(getattr(getattr(node, "label", ""), "value", getattr(node, "label", "")))
            if label in TABLE_LABELS:
                text = node.export_to_markdown(doc=document)
            else:
                text = str(getattr(node, "text", "") or "")
            provenance = getattr(node, "prov", None) or ()
            page = provenance[0].page_no if provenance else None
            items.append(Item(label=label, text=text, page=page))
        return items


def load(config: ServerConfig, *, reader: Callable[[Path], Reader] | None = None) -> LayoutBackend:
    """The layout backend, with Docling loaded from the weights volume unless a reader is given."""
    weights = config.model_dir / WEIGHTS_DIRECTORY
    return LayoutBackend((reader or DoclingReader)(weights))
