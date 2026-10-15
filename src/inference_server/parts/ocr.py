"""The scanned-page part: Tesseract over each page of a scan, with a confidence for every page.

**Never run against the real libraries.** Nothing in this repository has installed Tesseract,
pytesseract, pypdfium2 or Pillow, so the calls into them are written from their documented
interfaces and have not been executed. The grouping of recognised words into paragraphs, the
per-page confidence and the refusals are the program's own and are tested through a stand-in for
the one object that touches the libraries.

**The answer carries a confidence for every page, and the application decides on each.** One figure
for a whole document passes a ten-page scan whose tenth page is noise, and that page is then
indexed and cited as though it had been read (`brain.knowledge.parse_ocr` says so about itself).
So the page's confidence travels beside the blocks, in `pages`, and the application drops the pages
under its floor and names them to the uploader. This program decides nothing about the floor: the
number that says how sure is the engine's, and the number that says how sure is enough is the
product's, in one place.

**One page is in memory at a time.** A scan is rendered, recognised and let go a page at a time, so
the memory a document costs is a page and not the document, which is what the container was sized
for (`brain.ops.model_server.SIZING`). A page that is larger than a sensible scan is refused rather
than rendered: the pixel ceiling is what stops a small file that decodes to a gigapixel from
taking the container's memory.

**A document with more pages than it can finish in the time the supervisor allows is refused up
front**, as `unsupported`, because a request that outruns the supervisor's clock is killed and
retried, and a document that always outruns it would be retried for ever.

Task ids: M7.2.4
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
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

#: The model the server reports having loaded. Not the provenance name the application records
#: beside a passage (`brain.knowledge.parse_ocr.OCR_ENGINE`), which it keeps apart on purpose: one
#: says which program ran and can change with a version, the other says what kind of evidence the
#: text is.
LABEL: Final = "tesseract-eng-fast"

#: Where the language data sits under the models volume.
TESSDATA_DIRECTORY: Final = "tessdata"
LANGUAGE: Final = "eng"

#: How a page is drawn for recognition, in dots an inch. 300 is the figure Tesseract's own guidance
#: gives for scanned text; the sizing basis in `brain.ops.model_server` is written for it.
RENDER_DPI: Final = 300
PDF_POINTS_PER_INCH: Final = 72

#: The most pages one request reads, and the most pixels one page may have. Judgements: at about
#: three seconds a page the first is what fits in a request the supervisor allows 900 seconds,
#: and the second is a 300 dpi page of about 20 by 20 inches, which no scan of a document is.
MAX_PAGES: Final = 200
MAX_PAGE_PIXELS: Final = 100_000_000


@dataclass(frozen=True)
class Word:
    """One recognised word, with where the engine put it and how sure it said it was (0 to 100)."""

    text: str
    block: int
    paragraph: int
    line: int
    confidence: float


@dataclass(frozen=True)
class PageReading:
    """What the engine made of one page."""

    page: int
    words: tuple[Word, ...]


class Recogniser(Protocol):
    """What turns a file into pages of words. The real one is Tesseract's; a test has its own."""

    def pages(
        self, path: Path, media_type: str, only: frozenset[int] | None = None
    ) -> Iterator[PageReading]: ...


def page_confidence(words: Sequence[Word]) -> float:
    """How sure the engine was of a page, from 0 to 1: the mean over the words it recognised.

    A page with no recognised word is 0, not missing: nothing was read from it, and the application
    must hear that, because a page it does not hear about is a page it would index as read.
    """
    sure = [word.confidence for word in words if word.text.strip() and word.confidence >= 0]
    if not sure:
        return 0.0
    return min(max(sum(sure) / len(sure) / 100.0, 0.0), 1.0)


def paragraphs_of(words: Sequence[Word]) -> list[str]:
    """The words of a page as paragraphs, each of lines, in the order the engine found them."""
    order: list[tuple[int, int]] = []
    lines: dict[tuple[int, int], dict[int, list[str]]] = {}
    for word in words:
        if not word.text.strip() or word.confidence < 0:
            continue
        key = (word.block, word.paragraph)
        if key not in lines:
            order.append(key)
            lines[key] = {}
        lines[key].setdefault(word.line, []).append(word.text.strip())
    return ["\n".join(" ".join(row) for _, row in sorted(lines[key].items())) for key in order]


class OcrBackend:
    """`Backend`: recognises one document, a page at a time, and reports each page's confidence."""

    def __init__(self, recogniser: Recogniser, label: str = LABEL) -> None:
        self._recogniser = recogniser
        self.label = label

    def handle(self, body: bytes) -> Answer:
        drafts: list[Draft] = []
        pages: list[dict[str, object]] = []
        try:
            document = read_document(body)
            with as_file(document) as path:
                for reading in self._recogniser.pages(path, document.media_type, document.pages):
                    if len(pages) >= MAX_PAGES:
                        return refusal("unsupported", "ocr")
                    pages.append(
                        {"page": reading.page, "confidence": page_confidence(reading.words)}
                    )
                    drafts.extend(
                        Draft(text=text, page=reading.page) for text in paragraphs_of(reading.words)
                    )
        except BadRequest as error:
            return bad_request(error)
        except Unreadable as error:
            return refusal(error.cause, error.stage)
        return blocks_answer(laid_out(drafts), pages=pages)


def _words_from(data: Mapping[str, Sequence[Any]]) -> tuple[Word, ...]:
    """Tesseract's column-per-key table as words, skipping the rows that are not words."""
    words: list[Word] = []
    for index, text in enumerate(data["text"]):
        try:
            confidence = float(data["conf"][index])
        except (TypeError, ValueError):
            continue
        words.append(
            Word(
                text=str(text),
                block=int(data["block_num"][index]),
                paragraph=int(data["par_num"][index]),
                line=int(data["line_num"][index]),
                confidence=confidence,
            )
        )
    return tuple(words)


class TesseractRecogniser:
    """The one object that touches the libraries. Imported only when an OCR part is loaded."""

    def __init__(self, tessdata: Path) -> None:
        import os

        import pypdfium2
        import pytesseract
        from PIL import Image

        # Tesseract finds its language data by this variable, and the volume it is on is read-only.
        os.environ["TESSDATA_PREFIX"] = str(tessdata)
        Image.MAX_IMAGE_PIXELS = MAX_PAGE_PIXELS
        self._pdfium: Any = pypdfium2
        self._tesseract: Any = pytesseract
        self._image: Any = Image

    def _read(self, image: Any, page: int) -> PageReading:
        data = self._tesseract.image_to_data(
            image, lang=LANGUAGE, output_type=self._tesseract.Output.DICT
        )
        return PageReading(page=page, words=_words_from(data))

    def pages(
        self, path: Path, media_type: str, only: frozenset[int] | None = None
    ) -> Iterator[PageReading]:
        try:
            if media_type == "application/pdf":
                yield from self._pdf_pages(path, only)
            elif only is None or 1 in only:
                with self._image.open(path) as image:
                    yield self._read(image.convert("RGB"), 1)
        except OUR_OWN_MISTAKES:
            raise
        except Unreadable:
            raise
        except Exception as error:
            raise refusal_for(error, stage="ocr") from None

    def _pdf_pages(self, path: Path, only: frozenset[int] | None) -> Iterator[PageReading]:
        try:
            document = self._pdfium.PdfDocument(str(path))
        except self._pdfium.PdfiumError as error:
            # pdfium's own code for a password it was not given (FPDF_ERR_PASSWORD).
            if getattr(error, "err_code", None) == 4:
                raise Unreadable("encrypted", "open") from None
            raise
        try:
            scale = RENDER_DPI / PDF_POINTS_PER_INCH
            for number in range(len(document)):
                if only is not None and number + 1 not in only:
                    continue
                page = document[number]
                width, height = page.get_size()
                if width * scale * height * scale > MAX_PAGE_PIXELS:
                    raise Unreadable("unsupported", "ocr")
                image = page.render(scale=scale).to_pil().convert("RGB")
                yield self._read(image, number + 1)
        finally:
            document.close()


def load(
    config: ServerConfig, *, recogniser: Callable[[Path], Recogniser] | None = None
) -> OcrBackend:
    """The OCR backend, with Tesseract loaded from the weights volume unless one is given."""
    tessdata = config.model_dir / TESSDATA_DIRECTORY
    return OcrBackend((recogniser or TesseractRecogniser)(tessdata))
