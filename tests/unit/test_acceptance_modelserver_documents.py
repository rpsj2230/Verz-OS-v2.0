"""The install's checks of the model server's document parts, judged against stand-ins.

The first check sends each chosen part a page this module's code writes, so the page is shown to
be a real PDF first (a real library reads the line back out of it). The part itself is a stand-in
that answers in the shape the product decodes, shown giving the line back, saying nothing,
refusing and not answering, each with the check's own sentence. The second reads the ring of
recorded peaks, the third judges photographs by their headers and needs no server. Every one is
shown failing, because a check nobody has watched fail is a check nobody knows works.

Task ids: M7.2.1, M7.2.3, M7.2.4, M7.7.11
"""

from __future__ import annotations

import asyncio
import io
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from pypdf import PdfReader

from brain.connectors.throttle import CallOutcome
from brain.install import hold_saved
from brain.knowledge import text_path
from brain.ops import acceptance_checks_modelserver as modelserver
from brain.ops import model_server_client, model_server_store
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, Check, reason_for, registered
from brain.ops.acceptance_run import Harness
from brain.ops.model_server import Part, effective_limit_mib, read_config
from brain.ops.model_server_client import Reply
from brain.ops.model_server_peaks import RecordedPeak
from brain.settings import settings_from

MODULE = "brain.ops.acceptance_checks_modelserver"
READS = "each_document_part_chosen_reads_a_printed_line"
PEAKS = "no_recorded_model_server_peak_exceeds_its_costed_limit"
PHOTOGRAPHS = "a_photograph_is_judged_by_what_its_header_claims"
LONG_AGO = datetime(2019, 3, 6, 9, 0, tzinfo=UTC)
SENTENCE = "Acceptance check page"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def judged(name: str) -> tuple[str, str]:
    harness = Harness(
        run="0a1b2c3d",
        now=LONG_AGO,
        settings=settings_from({}),
        connection=None,  # type: ignore[arg-type]
    )
    try:
        asyncio.run(mine()[name].run(harness))
    except Exception as exc:
        return reason_for(exc)
    return PASSED, ""


@pytest.fixture
def chosen() -> Iterator[None]:
    """The server run, with all three document parts chosen."""
    before = hold_saved(
        {"INSTALL_SERVICES": "modelserver", "INSTALL_MODEL_PARTS": "layout,ocr,tika"}
    )
    yield
    hold_saved(before)


# ------------------------------------------------------------------ the page
def test_the_page_the_check_sends_is_a_valid_pdf_with_its_line_on_it() -> None:
    """A real PDF library opens it, finds one page and reads the line back out.

    Delete this and the page is only ever read by the parts under test, so a malformed page is a
    part failing and nobody can tell which side was wrong."""
    reader = PdfReader(io.BytesIO(modelserver.a_page_of_text(SENTENCE)))

    assert len(reader.pages) == 1
    assert reader.pages[0].extract_text().strip() == SENTENCE


# ------------------------------------------------------------------ the parts read the page
class _Server:
    """Answers each part as scripted and keeps which were asked."""

    def __init__(self, **replies: Reply) -> None:
        self.replies = {Part(name): reply for name, reply in replies.items()}
        self.asked: list[Part] = []

    def ask(self, part: Part, request: object) -> Reply:
        self.asked.append(part)
        return self.replies.get(part, Reply(CallOutcome.UNAVAILABLE))


def _block(text: str) -> dict[str, object]:
    return {"kind": "prose", "text": text, "start": 0, "page": 1, "section": ""}


def _good() -> dict[str, Reply]:
    blocks = {"blocks": [_block(SENTENCE)]}
    scan = {**blocks, "pages": [{"page": 1, "confidence": 0.95}]}
    return {
        "layout": Reply(CallOutcome.OK, blocks),
        "ocr": Reply(CallOutcome.OK, scan),
        "tika": Reply(CallOutcome.OK, blocks),
    }


def serving(monkeypatch: pytest.MonkeyPatch, server: _Server) -> None:
    monkeypatch.setattr(model_server_client, "make_model_server_client", lambda *_a, **_k: server)


def test_an_install_without_the_server_or_a_document_part_is_not_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Not failed: an install that runs no server, or one whose parts read no document, has
    nothing wrong, and a red row it cannot act on teaches an owner to ignore the page.

    Delete this and every install that chose not to run these shows a failure."""
    server = _Server(**_good())
    serving(monkeypatch, server)
    before = hold_saved({})
    try:
        assert judged(READS) == (NOT_RUN, modelserver.NO_MODEL_SERVER_HERE)
        hold_saved({"INSTALL_SERVICES": "modelserver", "INSTALL_MODEL_PARTS": "embedding"})
        assert judged(READS) == (NOT_RUN, modelserver.NO_DOCUMENT_PART_HERE)
    finally:
        hold_saved(before)
    assert server.asked == []


@pytest.mark.usefixtures("chosen")
def test_parts_that_give_the_line_back_pass_and_each_chosen_part_is_asked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The positive case, and which parts were asked: all three, in the order the route reads.

    Delete this and a check that refuses everything passes every refusal test here."""
    server = _Server(**_good())
    serving(monkeypatch, server)

    assert judged(READS) == (PASSED, "")
    assert server.asked == [Part.LAYOUT, Part.OCR, Part.TIKA]


def test_only_the_parts_the_install_chose_are_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    """An install that chose the scanned-page part alone is held to that part and not to the
    other two, which it never started.

    Delete this and every install is held to all three and fails for two it does not run."""
    server = _Server(**_good())
    serving(monkeypatch, server)
    before = hold_saved({"INSTALL_SERVICES": "modelserver", "INSTALL_MODEL_PARTS": "ocr"})
    try:
        assert judged(READS) == (PASSED, "")
    finally:
        hold_saved(before)
    assert server.asked == [Part.OCR]


@pytest.mark.usefixtures("chosen")
@pytest.mark.parametrize(
    ("part", "reply", "sentence"),
    [
        ("layout", Reply(CallOutcome.UNAVAILABLE), modelserver.A_DOCUMENT_PART_DID_NOT_ANSWER),
        ("ocr", Reply(CallOutcome.UNAVAILABLE), modelserver.A_DOCUMENT_PART_DID_NOT_ANSWER),
        ("tika", Reply(CallOutcome.UNAVAILABLE), modelserver.A_DOCUMENT_PART_DID_NOT_ANSWER),
        (
            "layout",
            Reply(CallOutcome.OK, {"refusal": {"cause": "corrupt", "stage": "open"}}),
            modelserver.A_DOCUMENT_PART_REFUSED_THE_PAGE,
        ),
        (
            "tika",
            Reply(CallOutcome.OK, {"blocks": [_block("something else entirely")]}),
            modelserver.A_DOCUMENT_PART_READ_NOTHING,
        ),
        (
            "ocr",
            Reply(
                CallOutcome.OK,
                {"blocks": [_block(SENTENCE)], "pages": [{"page": 1, "confidence": 0.1}]},
            ),
            modelserver.A_DOCUMENT_PART_REFUSED_THE_PAGE,
        ),
    ],
    ids=["layout-down", "ocr-down", "tika-down", "refuses", "reads-other-words", "unsure-scan"],
)
def test_a_part_that_does_not_answer_refuses_or_reads_the_wrong_words_fails_with_its_own_sentence(
    monkeypatch: pytest.MonkeyPatch, part: str, reply: Reply, sentence: str
) -> None:
    """Each way a part can fail the page is a different sentence: silent, refusing, and answering
    with words that are not the page's. A scan the recogniser was unsure of is refused as
    illegible, which is the product's reading and not a pass.

    Delete this and a part that answers nothing, or answers wrongly, passes by answering."""
    replies = {**_good(), part: reply}
    serving(monkeypatch, _Server(**replies))

    assert judged(READS) == (FAILED, sentence)


# ------------------------------------------------------------------ the peaks
def _peak(anon: int, part: Part = Part.LAYOUT) -> RecordedPeak:
    return RecordedPeak(
        part=part,
        batch_no=1,
        at=LONG_AGO,
        model="m",
        items=1,
        request_bytes=1,
        duration_ms=1,
        anon_peak_mib=anon,
        cache_peak_mib=0,
        cgroup_limit_mib=None,
    )


def ring(monkeypatch: pytest.MonkeyPatch, rows: list[RecordedPeak]) -> None:
    async def read(session: Any) -> list[RecordedPeak]:
        return rows

    monkeypatch.setattr(model_server_store, "recorded_peaks", read)


def test_a_peak_check_on_an_install_without_the_server_is_not_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and an install without the server shows a failure for peaks it never made."""
    ring(monkeypatch, [_peak(10_000)])
    before = hold_saved({})
    try:
        assert judged(PEAKS) == (NOT_RUN, modelserver.NO_MODEL_SERVER_HERE)
    finally:
        hold_saved(before)


@pytest.mark.usefixtures("chosen")
def test_with_no_peak_recorded_yet_the_check_is_not_run_and_not_passed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty ring is no evidence either way, so it says that and does not pass.

    Delete this and a new install shows a pass for a limit nothing has been measured against."""
    ring(monkeypatch, [])

    assert judged(PEAKS) == (NOT_RUN, modelserver.NO_PEAK_HAS_BEEN_RECORDED_YET)


@pytest.mark.usefixtures("chosen")
def test_peaks_at_or_under_the_costed_limit_pass_and_one_over_it_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """At the limit passes, one mebibyte over it fails, and a larger cache figure is not counted:
    cache is given back before anything is killed.

    Delete this and the comparison moves by one, or is made against the total and fails a server
    that read a large file through its page cache."""
    limit = effective_limit_mib(read_config())

    ring(monkeypatch, [_peak(limit)])
    assert judged(PEAKS) == (PASSED, "")
    ring(monkeypatch, [_peak(limit + 1)])
    assert judged(PEAKS) == (FAILED, modelserver.A_PEAK_WAS_LARGER_THAN_THE_LIMIT)
    heavy_cache = RecordedPeak(**{**_peak(100).__dict__, "cache_peak_mib": 10 * limit})
    ring(monkeypatch, [heavy_cache])
    assert judged(PEAKS) == (PASSED, "")


# ------------------------------------------------------------------ photographs at the door
def test_the_photograph_check_passes_on_the_product_as_it_stands() -> None:
    """The positive case. Delete this and a check that fails everything passes the two below."""
    assert judged(PHOTOGRAPHS) == (PASSED, "")


def test_the_photograph_check_fails_where_a_header_claiming_a_gigapixel_is_cleared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The size test removed from the image judgement. Delete this and the one defence against a
    small file that decodes to the memory of a server can be dropped with nothing red."""
    monkeypatch.setattr(text_path, "MAX_IMAGE_PIXELS", 10**12)

    outcome = judged(PHOTOGRAPHS)

    assert outcome[0] == FAILED and "more pixels" in outcome[1]


def test_the_photograph_check_fails_where_an_ordinary_page_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bound set below an ordinary page. Delete this and a bound that refuses every photograph
    passes the check that exists to show a scan can reach the reader."""
    monkeypatch.setattr(text_path, "MAX_IMAGE_PIXELS", 1000)

    outcome = judged(PHOTOGRAPHS)

    assert outcome[0] == FAILED and "ordinary page was refused" in outcome[1]
