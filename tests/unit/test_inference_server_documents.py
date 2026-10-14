"""The three document parts of the model server, held against the application that sends to them.

The application and the server are built and deployed apart, so every spelling they share is held
equal by a test that reads both, and the answers a part produces are read by the application's own
decoder. A part is judged with a stand-in for the one object that touches its library (Docling,
Tesseract, the JVM), because none of those is installed here: what these tests prove is this
program's own work, which is the request it reads, the blocks it lays out, the refusals it may
say and the processes it leaves behind. **Nothing here has run a real document through a real
library**, and the part modules say so at their head.

Task ids: M7.2.1, M7.2.3, M7.2.4
"""

from __future__ import annotations

import http.server
import importlib.util
import json
import os
import socket
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, ClassVar

import pytest

from brain.knowledge.chunking import BlockKind
from brain.knowledge.ingest import AdmittedUpload, MediaType, ScanVerdict, admit_upload
from brain.knowledge.parse_layout import (
    CAUSES_A_PARSER_MAY_DECLARE,
    DOCUMENT_KEYS,
    REQUEST_KEYS,
    STAGES_A_PARSER_MAY_DECLARE,
    decode_layout,
    layout_request,
)
from brain.knowledge.scanning import ScannedContent, ScanReport, scan_for_parsing
from brain.knowledge.search import SECTION_CHARS
from brain.knowledge.text_path import BLOCK_SEPARATOR, Drafted, joined
from brain.knowledge.text_path import laid_out as product_laid_out
from brain.ops import model_server as product
from brain.ops.inference_client import jsonable
from inference_server import supervisor
from inference_server.parts import NEEDS, documents, layout, ocr, tika
from inference_server.parts.documents import Draft

PDF = b"%PDF-1.7\n1 0 obj\n<< >>\nendobj\n"
PACKAGE = Path(__file__).resolve().parents[2] / "src" / "inference_server"


class _Clean:
    def scan(self, content: bytes) -> ScanReport:
        return ScanReport(verdict=ScanVerdict.CLEAN, scanner="fake-av")


def _upload(content: bytes = PDF) -> AdmittedUpload:
    return admit_upload(filename="sop.pdf", declared_type=MediaType.PDF.value, content=content)


def _cleared(content: bytes = PDF) -> ScannedContent:
    return scan_for_parsing(_upload(content), content, scanner=_Clean())


def request_body(content: bytes = PDF) -> bytes:
    """The bytes the application's own builder puts on the wire for a document."""
    return json.dumps(jsonable(layout_request(_cleared(content)))).encode("utf-8")


# ------------------------------------------------------------------ the wire, held equal
def test_the_wire_this_program_speaks_is_the_one_the_application_writes() -> None:
    """Every spelling the two programs share is read from both and compared: the keys of a
    request and of its document, the four causes and the stages a part may declare, the
    separator between blocks, the section's width and the types a file can be saved under.

    Delete this and a renamed key or a fifth cause is a request the server cannot read or an
    answer the application reads as an outage, and a document is retried for ever."""
    assert documents.REQUEST_KEYS == REQUEST_KEYS
    assert documents.DOCUMENT_KEYS == DOCUMENT_KEYS
    assert set(documents.CAUSES) == {cause.value for cause in CAUSES_A_PARSER_MAY_DECLARE}
    assert set(documents.STAGES) == {stage.value for stage in STAGES_A_PARSER_MAY_DECLARE}
    assert documents.BLOCK_SEPARATOR == BLOCK_SEPARATOR
    assert documents.SECTION_CHARS == SECTION_CHARS
    assert set(documents.SUFFIX) <= {media.value for media in MediaType}


def test_a_request_the_application_builds_is_read_back_as_the_same_bytes_and_digest() -> None:
    """The producer's output is fed to the consumer: the document the application encodes is the
    document this program decodes, with the digest it was admitted under.

    Delete this and each side is tested only against a request it built itself, so a mismatch in
    the encoding would pass both suites and fail on the first real document."""
    document = documents.read_document(request_body())

    assert document.content == PDF
    assert document.media_type == MediaType.PDF.value
    assert document.digest == _upload().digest


@pytest.mark.parametrize(
    "body",
    [b"not json", b"[]", b'{"document": 1}', b'{"document": {"media_type": "application/pdf"}}'],
)
def test_a_body_that_is_not_a_document_request_is_a_bad_request(body: bytes) -> None:
    """A body that is not JSON, not an object, or names no content is refused as the
    application's mistake and never read as an empty document.

    Delete this and a malformed request is parsed as a document with nothing in it, which comes
    back as an answer saying there is no text."""
    with pytest.raises(documents.BadRequest):
        documents.read_document(body)


def test_content_that_is_not_base64_is_a_bad_request() -> None:
    """The content is decoded strictly: a character outside the alphabet is refused and not
    skipped. Delete this and a corrupted body is silently shortened and parsed as a smaller file."""
    request = json.dumps(
        {"model": "m", "document": {"digest": "d", "media_type": "a/b", "content_base64": "!!!"}}
    ).encode()

    with pytest.raises(documents.BadRequest):
        documents.read_document(request)


# ------------------------------------------------------------------ laying blocks out
def test_blocks_are_laid_out_where_the_applications_own_layout_puts_them() -> None:
    """The same drafts laid out here and by `brain.knowledge.text_path.laid_out` give the same
    offsets and text, and the application's own check that every block sits where its start says
    accepts them.

    Delete this and an offset off by one separator is a citation that points at the wrong words,
    which nothing downstream can notice."""
    words = ["Heading", "  First paragraph  \n", "", "Second\x00 one", "a" * (SECTION_CHARS + 20)]
    ours = documents.laid_out(
        [Draft(text=text, page=index + 1) for index, text in enumerate(words)]
    )
    theirs = product_laid_out(
        [Drafted(text=text, page=index + 1) for index, text in enumerate(words)]
    )

    assert [(one["text"], one["start"]) for one in ours] == [
        (block.text, block.start) for block in theirs
    ]
    assert joined(theirs) == documents.BLOCK_SEPARATOR.join(str(one["text"]) for one in ours)


def test_a_section_is_cut_to_the_width_the_column_has() -> None:
    """A heading longer than the column is cut where the application would refuse it.

    Delete this and a long heading makes the application call the whole answer unreadable."""
    [block] = documents.laid_out([Draft(text="x", section="s" * (SECTION_CHARS + 50))])

    assert len(str(block["section"])) == SECTION_CHARS


# ------------------------------------------------------------------ refusals
def test_a_part_may_declare_only_what_the_application_accepts() -> None:
    """Each of the four causes at each stage is a refusal the application reads back as that cause;
    a fifth cause, or a stage it would not accept, is refused by this program before it is sent.

    Delete this and a part can name a cause of the application's own (an outage, say), which the
    application treats as unreadable, so the document is retried for ever."""
    for cause in documents.CAUSES:
        answer = documents.refusal(cause, "open")
        decoded = decode_layout(answer.payload)
        assert not isinstance(decoded, tuple)
        assert decoded.cause.value == cause
    with pytest.raises(ValueError, match="not something a part may declare"):
        documents.refusal("parser_unavailable", "open")
    with pytest.raises(ValueError, match="not something a part may declare"):
        documents.refusal("corrupt", "admit")


def test_a_library_exception_is_a_refusal_only_by_the_words_its_type_carries() -> None:
    """A password exception is `encrypted`, a corrupt-file exception is `corrupt`, and every
    other exception about a document is `unsupported` at the stage named, which is the one word
    true whatever went wrong and the one that lets the route try the next reader.

    Delete this and a failure nobody understood ends a document as damaged, where the next reader
    would have read it."""

    class PasswordRequiredError(Exception):
        pass

    class CorruptFileError(Exception):
        pass

    assert documents.refusal_for(PasswordRequiredError(), stage="layout").cause == "encrypted"
    assert documents.refusal_for(CorruptFileError(), stage="layout").cause == "corrupt"
    other = documents.refusal_for(ValueError("quotes the file"), stage="ocr")
    assert (other.cause, other.stage) == ("unsupported", "ocr")
    assert "quotes" not in str(other)


# ------------------------------------------------------------------ the layout part
class _Reader:
    """Stands in for the one object that touches Docling."""

    def __init__(self, items: list[layout.Item] | Exception) -> None:
        self.items = items
        self.paths: list[Path] = []

    def read(self, path: Path) -> list[layout.Item]:
        self.paths.append(path)
        assert path.read_bytes() == PDF
        if isinstance(self.items, Exception):
            raise self.items
        return self.items


def test_a_layout_answer_is_read_by_the_applications_decoder_as_the_blocks_the_reader_found() -> (
    None
):
    """The producer's answer is fed to the application's own decoder: headings open a section for
    what follows, a table stays a table, the page furniture is left out, and the offsets are the
    ones the decoder demands.

    Delete this and the part is tested only against its own idea of what the application reads."""
    reader = _Reader(
        [
            layout.Item("page_header", "Company Confidential", 1),
            layout.Item("section_header", "Safety", 1),
            layout.Item("text", "Wear a helmet.", 1),
            layout.Item("table", "| a | b |\n| - | - |\n| 1 | 2 |", 2),
            layout.Item("page_footer", "Page 2", 2),
            layout.Item("some_new_label", "Still prose.", 2),
        ]
    )
    answer = layout.LayoutBackend(reader).handle(request_body())

    decoded = decode_layout(answer.payload)

    assert isinstance(decoded, tuple)
    assert [
        (block.text.splitlines()[0], block.kind, block.page, block.section) for block in decoded
    ] == [
        ("Safety", BlockKind.PROSE, 1, "Safety"),
        ("Wear a helmet.", BlockKind.PROSE, 1, "Safety"),
        ("| a | b |", BlockKind.TABLE, 2, "Safety"),
        ("Still prose.", BlockKind.PROSE, 2, "Safety"),
    ]
    assert answer.items == 4


def test_the_document_is_off_the_disk_before_the_answer_is_sent() -> None:
    """The file a library read is gone when the part has answered, whether it read it or failed.

    Delete this and a client's document stays in the container's layer for the next one to find."""
    reader = _Reader([layout.Item("text", "words", 1)])
    layout.LayoutBackend(reader).handle(request_body())
    failing = _Reader(ValueError("x"))
    with pytest.raises(ValueError, match="x"):
        layout.LayoutBackend(failing).handle(request_body())

    assert reader.paths and failing.paths
    assert not any(path.exists() for path in reader.paths + failing.paths)


def test_a_document_the_reader_cannot_open_is_refused_in_the_four_words() -> None:
    """An `Unreadable` from the reader is the refusal it names, as a 200 the application decodes;
    a document with no recognised text is an empty list, which the application turns into
    `no_text_layer` and sends to the scanned-page part.

    Delete this and a locked file is an outage retried for ever, or a scan is read as empty and
    never routed to OCR."""
    locked = layout.LayoutBackend(_Reader(documents.Unreadable("encrypted", "open")))
    empty = layout.LayoutBackend(_Reader([]))

    refused = decode_layout(locked.handle(request_body()).payload)
    nothing = decode_layout(empty.handle(request_body()).payload)

    assert not isinstance(refused, tuple) and refused.cause.value == "encrypted"
    assert nothing == ()


def test_our_own_programming_error_is_an_outage_and_not_a_fact_about_the_document() -> None:
    """A TypeError or an AttributeError out of the reader propagates, so the worker reports an
    outage and the application retries; it is not turned into `unsupported`.

    Delete this and a bug in this program reads every document as unsupported while it lasts, and
    the route quietly falls back for all of them with nothing saying why."""
    assert isinstance(documents.OUR_OWN_MISTAKES, tuple)
    backend = layout.LayoutBackend(_Reader(AttributeError("a bug")))

    with pytest.raises(AttributeError):
        backend.handle(request_body())


def test_a_type_no_part_reads_is_a_bad_request_and_not_an_empty_answer() -> None:
    """A document of a type with no suffix is refused as the application's mistake.

    Delete this and a plain-text file sent here is written without a suffix, a library guesses,
    and the answer is whatever it guessed."""
    request = json.dumps(
        {
            "model": "m",
            "document": {"digest": "d", "media_type": "text/plain", "content_base64": "YQ=="},
        }
    ).encode()

    answer = layout.LayoutBackend(_Reader([])).handle(request)

    assert answer.status == 400


# ------------------------------------------------------------------ the scanned-page part
def _word(text: str, confidence: float, block: int = 1, paragraph: int = 1, line: int = 1) -> Any:
    return ocr.Word(text, block, paragraph, line, confidence)


class _Recogniser:
    def __init__(self, pages: list[ocr.PageReading]) -> None:
        self.pages_to_give = pages

    def pages(self, path: Path, media_type: str) -> Iterator[ocr.PageReading]:
        assert path.exists()
        yield from self.pages_to_give


def test_a_pages_confidence_is_the_mean_of_the_words_read_and_zero_for_a_page_with_none() -> None:
    """The mean is over recognised words only (a row the engine marks -1 is not a word), scaled to
    0 to 1, and a page with nothing read is 0 and not absent.

    Delete this and a blank page has no confidence, the application hears nothing about it, and
    it is indexed as though it had been read."""
    words = (_word("a", 90), _word("b", 70), _word("", 99), _word("noise", -1))

    assert ocr.page_confidence(words) == pytest.approx(0.8)
    assert ocr.page_confidence(()) == 0.0
    assert ocr.page_confidence((_word("x", -1),)) == 0.0
    assert ocr.page_confidence((_word("x", 250),)) == 1.0


def test_words_are_grouped_into_paragraphs_of_lines_in_the_order_the_engine_found_them() -> None:
    """Words sharing a block and paragraph are one block, lines in order and words in a line
    joined by a space; an engine's non-word rows are not text.

    Delete this and a page is one block of words with no breaks, which chunking cannot cut."""
    words = (
        _word("Invoice", 95, 1, 1, 1),
        _word("1042", 96, 1, 1, 1),
        _word("Total", 92, 1, 1, 2),
        _word("", -1, 1, 1, 2),
        _word("Pay", 88, 2, 1, 1),
        _word("now", 89, 2, 1, 1),
    )

    assert ocr.paragraphs_of(words) == ["Invoice 1042\nTotal", "Pay now"]


def test_every_page_is_reported_with_its_confidence_and_blocks_are_laid_out_across_them() -> None:
    """The answer carries blocks for every page that had words and a confidence for every page,
    including the one with none, and the application's decoder reads the blocks.

    Delete this and the application cannot apply a floor per page: it hears one figure, or none."""
    pages = [
        ocr.PageReading(1, (_word("Clear", 95), _word("text", 93))),
        ocr.PageReading(2, ()),
        ocr.PageReading(3, (_word("smudge", 20),)),
    ]
    answer = ocr.OcrBackend(_Recogniser(pages)).handle(request_body())

    decoded = decode_layout(answer.payload)

    assert isinstance(decoded, tuple)
    assert [(block.text, block.page) for block in decoded] == [("Clear text", 1), ("smudge", 3)]
    reported = answer.payload["pages"]
    assert isinstance(reported, list)
    assert [(one["page"], round(float(one["confidence"]), 2)) for one in reported] == [
        (1, 0.94),
        (2, 0.0),
        (3, 0.2),
    ]


def test_a_document_with_more_pages_than_one_request_can_finish_is_refused_up_front() -> None:
    """One page over the cap is `unsupported` at the scanned-page stage, and exactly the cap is
    read.

    Delete this and a document too long for the supervisor's clock is killed and retried for
    ever, each attempt costing the whole clock."""
    at_cap = [ocr.PageReading(n, (_word("w", 90),)) for n in range(1, ocr.MAX_PAGES + 1)]
    over = [*at_cap, ocr.PageReading(ocr.MAX_PAGES + 1, (_word("w", 90),))]

    ok = ocr.OcrBackend(_Recogniser(at_cap)).handle(request_body())
    refused = decode_layout(ocr.OcrBackend(_Recogniser(over)).handle(request_body()).payload)

    assert len(ok.payload["pages"]) == ocr.MAX_PAGES  # type: ignore[arg-type]
    assert not isinstance(refused, tuple)
    assert (refused.cause.value, refused.stage.value) == ("unsupported", "ocr")


# ------------------------------------------------------------------ the general reader
class _FakeTika(http.server.BaseHTTPRequestHandler):
    status = 200
    answer = b""
    seen: ClassVar[list[tuple[str, dict[str, str], bytes]]] = []

    def do_PUT(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        self.seen.append((self.path, dict(self.headers.items()), self.rfile.read(length)))
        self.send_response(self.status)
        self.end_headers()
        self.wfile.write(self.answer)

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture
def fake_tika() -> Iterator[tuple[int, type[_FakeTika]]]:
    handler = type("Handler", (_FakeTika,), {"seen": []})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield int(server.server_address[1]), handler
    server.shutdown()
    server.server_close()


def test_the_general_reader_asks_for_plain_text_and_never_for_metadata(
    fake_tika: tuple[int, type[_FakeTika]],
) -> None:
    """The request is a PUT of the file to `/tika` asking for `text/plain` under the file's own
    type, and the paragraphs of the answer are the blocks.

    Delete this and a request for `/rmeta` returns a title and an author, which are
    attacker-chosen prose in a field a pipeline concatenates near a prompt."""
    port, handler = fake_tika
    handler.answer = b"First paragraph.\nstill first.\n\n\nSecond paragraph.\n"
    backend = tika.TikaBackend(tika.sender(port))

    answer = backend.handle(request_body())

    decoded = decode_layout(answer.payload)
    assert isinstance(decoded, tuple)
    assert [block.text for block in decoded] == [
        "First paragraph.\nstill first.",
        "Second paragraph.",
    ]
    [(path, headers, body)] = handler.seen
    assert path == "/tika"
    assert headers["Accept"] == "text/plain"
    assert headers["Content-Type"] == MediaType.PDF.value
    assert body == PDF
    assert "/rmeta" not in path


@pytest.mark.parametrize("status", [415, 422])
def test_a_file_the_general_reader_will_not_process_is_unsupported_and_never_encrypted(
    status: int, fake_tika: tuple[int, type[_FakeTika]]
) -> None:
    """Tika's 415 and 422 are the refusal `unsupported`: it does not say whether a 422 is a
    password or damage, and `encrypted` would send somebody to remove one that is not there.

    Delete this and either status ends the document with a remedy that may be false."""
    port, handler = fake_tika
    handler.status = status

    refused = decode_layout(tika.TikaBackend(tika.sender(port)).handle(request_body()).payload)

    assert not isinstance(refused, tuple)
    assert (refused.cause.value, refused.stage.value) == ("unsupported", "text")


def test_any_other_status_from_the_general_reader_is_an_outage(
    fake_tika: tuple[int, type[_FakeTika]],
) -> None:
    """A 500 raises, so the worker reports an outage and the application retries.

    Delete this and a server error is read as a document with no text."""
    port, handler = fake_tika
    handler.status = 500

    with pytest.raises(RuntimeError, match="answered 500"):
        tika.TikaBackend(tika.sender(port)).handle(request_body())


def test_a_part_whose_jvm_has_gone_ends_itself_so_the_supervisor_starts_a_fresh_one() -> None:
    """With the JVM dead the part exits with status 70 and does not answer, before and after the
    connection fails.

    Delete this and the part stays up answering every request with an error until it is idle."""
    dead = tika.TikaBackend(lambda body, media: (200, b""), alive=lambda: False)
    dying = tika.TikaBackend(_refuse, alive=iter([True, False]).__next__)

    with pytest.raises(SystemExit) as first:
        dead.handle(request_body())
    with pytest.raises(SystemExit) as second:
        dying.handle(request_body())

    assert first.value.code == second.value.code == tika.JVM_GONE


def _refuse(body: bytes, media: str) -> tuple[int, bytes]:
    raise ConnectionRefusedError


def test_the_jvms_heap_is_the_heap_the_budget_was_written_for() -> None:
    """The ceiling the JVM is started with plus the 128 MiB the heap does not cover is the
    anonymous figure the budget gives this part.

    Delete this and the two are edited apart, and the container is sized for a JVM that is not the
    one started."""
    assert product.SIZING[product.Part.TIKA].anonymous_mib == tika.HEAP_MIB + 128


def test_paragraphs_split_on_a_blank_line_and_drop_the_empty_ones() -> None:
    """Text is cut where a blank line, even one with spaces in it, ends a paragraph.

    Delete this and a document is one block the size of the document."""
    assert tika.paragraphs("a\n \nb\n\n\n\nc\n") == ["a", "b", "c\n"]
    assert tika.paragraphs("   \n\n  ") == []


# ------------------------------------------------------------------ what a part needs
def test_the_three_document_parts_are_in_this_image_and_named_as_the_supervisor_expects() -> None:
    """Each document part's module is found where `NEEDS` says, and each module has `load`.

    Delete this and a renamed module is a part the readiness check reports as not in the image."""
    for name in ("layout", "ocr", "tika"):
        module = NEEDS[name].module
        assert importlib.util.find_spec(f"inference_server.parts.{module}") is not None
        assert callable(__import__(f"inference_server.parts.{module}", fromlist=["load"]).load)


# ------------------------------------------------------------------ nothing is left running
_GRANDCHILD = r"""
import json, subprocess, sys
sys.path.insert(0, {src!r})
from inference_server.framing import read_frame, write_frame
sleeper = "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(120)"
child = subprocess.Popen([sys.executable, "-c", sleeper])
open({pidfile!r}, "w").write(str(child.pid))
write_frame(sys.stdout.buffer, json.dumps({{"ready": True, "model": "stand-in"}}).encode())
while read_frame(sys.stdin.buffer, ceiling=1 << 20) is not None:
    pass
"""


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_ending_a_part_ends_what_the_part_started_as_well(tmp_path: Path) -> None:
    """A part that started a child of its own (the general reader's JVM) leaves nothing running
    once it is stopped: the child is in the part's process group, which is what is ended.

    Delete this and the memory the idle stop exists to give back stays held by a process nobody
    holds a handle to."""
    pidfile = tmp_path / "pid"
    script = _GRANDCHILD.format(src=str(PACKAGE.parent), pidfile=str(pidfile))
    part = supervisor.SubprocessPart("tika", argv=[sys.executable, "-c", script])

    part.start()
    grandchild = int(pidfile.read_text())
    assert _alive(grandchild)
    part.stop()

    deadline = time.monotonic() + 10
    while _alive(grandchild) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not _alive(grandchild)


def test_a_free_port_is_one_nothing_listens_on() -> None:
    """The port the JVM is told to listen on is free at the moment it is chosen.

    Delete this and the helper is a constant, and two parts on one host collide."""
    port = tika.free_port()

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))


# ------------------------------------------------------------------ where the weights are put
def test_every_file_a_part_needs_is_where_the_fetch_puts_it() -> None:
    """The paths the readiness check looks at for the three document parts are the paths
    `inference_server.fetch` writes: the English data under `tessdata`, the jar under `tika`, and
    the directory Docling's downloader fills.

    Delete this and a renamed path leaves a part the fetch filled and the readiness check says is
    missing, for ever, on every install."""
    from inference_server import fetch
    from inference_server.parts import NEEDS
    from tests.unit.test_inference_server import server_config

    config = server_config(INFERENCE_PARTS="layout,ocr,tika")
    fetched = {str(config.model_dir / one.name) for one in fetch.SOURCES}
    fetched |= {str(config.model_dir / name) for name in fetch.DIRECTORIES.values()}

    for part in ("layout", "ocr", "tika"):
        assert {str(path) for path in NEEDS[part].files(config)} <= fetched, part


def test_a_nested_weight_file_is_put_in_its_directory_and_a_second_fetch_leaves_it_alone(
    tmp_path: Path,
) -> None:
    """A source named under a directory makes the directory, and the second fetch reads its own
    record and fetches nothing.

    Delete this and the data for the scanned-page part cannot be written, or is fetched on every
    deploy."""
    from inference_server import fetch

    source = fetch.Source(
        part="ocr", name="tessdata/eng.traineddata", url="http://example.invalid/e"
    )

    class Response:
        def __init__(self) -> None:
            self.data = [b"abc", b""]

        def read(self, size: int) -> bytes:
            return self.data.pop(0)

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *a: object) -> None:
            return None

    opened: list[str] = []

    def opener(url: str, timeout: int) -> Response:
        opened.append(url)
        return Response()

    first = fetch.fetch_one(source, tmp_path, opener=opener)
    second = fetch.fetch_one(source, tmp_path, opener=opener)

    assert (tmp_path / "tessdata" / "eng.traineddata").read_bytes() == b"abc"
    assert "fetched" in first and "already here" in second
    assert opened == ["http://example.invalid/e"]


def test_a_directory_of_weights_is_fetched_once_and_a_failure_names_only_its_type(
    tmp_path: Path,
) -> None:
    """An empty directory is filled by the downloader it is given; one that holds something is left
    alone; an exception becomes a refusal naming its type and nothing a library said.

    Delete this and a restart of the release downloads Docling's models again, or a library's
    message about a path reaches a log."""
    from inference_server import fetch

    calls: list[Path] = []

    def download(target: Path) -> None:
        calls.append(target)
        (target / "model.bin").write_bytes(b"x")

    def failing(target: Path) -> None:
        raise OSError("/secret/path was refused")

    assert "fetched" in fetch.fetch_directory("docling", tmp_path, download=download)
    assert "already here" in fetch.fetch_directory("docling", tmp_path, download=download)
    assert calls == [tmp_path / "docling"]
    with pytest.raises(fetch.FetchError) as raised:
        fetch.fetch_directory("other", tmp_path, download=failing)
    assert "OSError" in str(raised.value) and "secret" not in str(raised.value)


# ---------------------------------------------------------------- the objects that touch libraries
class _Label:
    def __init__(self, value: str) -> None:
        self.value = value


class _Node:
    def __init__(self, label: str, text: str = "", page: int | None = None) -> None:
        self.label = _Label(label)
        self.text = text
        self.prov = [type("Prov", (), {"page_no": page})()] if page is not None else []

    def export_to_markdown(self, doc: object) -> str:
        return "| a | b |"


class _Converted:
    def __init__(self, nodes: list[_Node]) -> None:
        self.document = self
        self.nodes = nodes

    def iterate_items(self) -> list[tuple[_Node, int]]:
        return [(node, 0) for node in self.nodes]


class _Converter:
    def __init__(self, result: object) -> None:
        self.result = result

    def convert(self, path: str) -> object:
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _docling(result: object) -> layout.DoclingReader:
    reader = object.__new__(layout.DoclingReader)
    reader._converter = _Converter(result)
    return reader


def test_the_object_that_touches_docling_reduces_its_items_to_labels_text_and_pages(
    tmp_path: Path,
) -> None:
    """A table is exported as the library exports one, an item with no provenance has no page, and
    the label is its value and not the enum's name.

    Delete this and the one piece of the layout part that cannot be run without Docling is
    untested, so a mapping slip is found on the first install."""
    nodes = [
        _Node("section_header", "Safety", 3),
        _Node("table", "ignored", 3),
        _Node("text", "Wear a helmet.", None),
    ]

    items = _docling(_Converted(nodes)).read(tmp_path / "x.pdf")

    assert [(one.label, one.text, one.page) for one in items] == [
        ("section_header", "Safety", 3),
        ("table", "| a | b |", 3),
        ("text", "Wear a helmet.", None),
    ]


def test_a_library_failure_about_the_document_is_a_refusal_and_one_about_us_is_not(
    tmp_path: Path,
) -> None:
    """A password exception is `encrypted`; an exception the library raised about the document is
    `unsupported` at the layout stage; a TypeError is this program's own and propagates.

    Delete this and the mapping from a library's exception to the four words is never run."""

    class PasswordRequiredError(Exception):
        pass

    with pytest.raises(documents.Unreadable) as locked:
        _docling(PasswordRequiredError()).read(tmp_path / "x.pdf")
    with pytest.raises(documents.Unreadable) as other:
        _docling(ValueError("quotes the file")).read(tmp_path / "x.pdf")
    with pytest.raises(TypeError):
        _docling(TypeError("a bug")).read(tmp_path / "x.pdf")

    assert (locked.value.cause, locked.value.stage) == ("encrypted", "open")
    assert (other.value.cause, other.value.stage) == ("unsupported", "layout")


def test_tesseracts_columns_become_words_and_the_rows_that_are_not_words_are_skipped() -> None:
    """The engine's column-per-key table is read row by row; a figure that is not a number is a
    row that is not a word and is skipped, and the grouping keys are whole numbers.

    Delete this and a header row of the engine's table is a word with a confidence of nothing."""
    data = {
        "text": ["", "Hello", "world"],
        "conf": ["-1", "96.5", "x"],
        "block_num": ["0", "1", "1"],
        "par_num": ["0", "1", "1"],
        "line_num": ["0", "1", "1"],
    }

    [word] = ocr._words_from(data)[1:2] or [None]
    words = ocr._words_from(data)

    assert [(one.text, one.confidence) for one in words] == [("", -1.0), ("Hello", 96.5)]
    assert word is not None and (word.block, word.paragraph, word.line) == (1, 1, 1)


class _Pdfium:
    class PdfiumError(Exception):
        def __init__(self, err_code: int | None) -> None:
            super().__init__("x")
            self.err_code = err_code

    def __init__(self, pages: int = 0, opening: Exception | None = None) -> None:
        self.pages = pages
        self.opening = opening
        self.closed = False

    def PdfDocument(self, path: str) -> object:  # noqa: N802 - the library's own name
        if self.opening is not None:
            raise self.opening
        outer = self

        class Page:
            def get_size(self) -> tuple[float, float]:
                return (612.0, 792.0)

            def render(self, scale: float) -> object:
                return type(
                    "R", (), {"to_pil": lambda s: type("I", (), {"convert": lambda i, m: "img"})()}
                )()

        class Doc:
            def __len__(self) -> int:
                return outer.pages

            def __getitem__(self, number: int) -> Page:
                return Page()

            def close(self) -> None:
                outer.closed = True

        return Doc()


def _tesseract(pdfium: _Pdfium) -> ocr.TesseractRecogniser:
    recogniser = object.__new__(ocr.TesseractRecogniser)
    recogniser._pdfium = pdfium
    recogniser._tesseract = type(
        "T",
        (),
        {
            "Output": type("O", (), {"DICT": "dict"}),
            "image_to_data": staticmethod(
                lambda image, lang, output_type: {
                    "text": ["Hi"],
                    "conf": ["90"],
                    "block_num": ["1"],
                    "par_num": ["1"],
                    "line_num": ["1"],
                }
            ),
        },
    )
    return recogniser


def test_a_pdf_is_recognised_a_page_at_a_time_and_closed(tmp_path: Path) -> None:
    """Each page is rendered and read in turn, numbered from one, and the document is closed when
    the last is done, so one page is in memory at a time and nothing holds the file.

    Delete this and the per-page memory claim the container was sized on has no test, or a document
    handle outlives the request."""
    pdfium = _Pdfium(pages=3)

    readings = list(_tesseract(pdfium).pages(tmp_path / "x.pdf", "application/pdf"))

    assert [one.page for one in readings] == [1, 2, 3]
    assert [word.text for word in readings[0].words] == ["Hi"]
    assert pdfium.closed


def test_a_pdf_that_wants_a_password_is_encrypted_and_any_other_failure_is_unsupported(
    tmp_path: Path,
) -> None:
    """pdfium's password code is the one that means locked; its other errors are a refusal the next
    reader may try, and this program's own mistakes propagate.

    Delete this and every unreadable PDF is told to remove a password it does not have."""
    locked = _Pdfium(opening=_Pdfium.PdfiumError(4))
    damaged = _Pdfium(opening=_Pdfium.PdfiumError(3))

    with pytest.raises(documents.Unreadable) as refused:
        list(_tesseract(locked).pages(tmp_path / "x.pdf", "application/pdf"))
    with pytest.raises(documents.Unreadable) as other:
        list(_tesseract(damaged).pages(tmp_path / "x.pdf", "application/pdf"))

    assert refused.value.cause == "encrypted"
    assert (other.value.cause, other.value.stage) == ("unsupported", "ocr")
