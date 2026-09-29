"""The install checks for getting a document in, each passing, and each shown failing or not run.

The pure half holds the module's inert files to the product's own scan: the PDF names script and
nothing else is wrong with it, the Word file holds a macro part and is otherwise a Word file, and
the antivirus test string is assembled whole at run time and appears nowhere in the source.

The database half runs the module as the worker would, against PostgreSQL at head, with the link
answered by a recorded page (a test never asks the network), the object store held in memory and
the antivirus a recorded daemon. The checks pass and leave nothing; with no antivirus and no store
the two that need them say they were not run; and each is shown failing with the product broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M7.1.2, M7.1.3, M7.1.4, M7.1.5, M7.7.4, M7.7.3
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any, cast

import pytest

from brain.knowledge.ingest import MediaType, ScanCause, ScanVerdict, admit_upload
from brain.knowledge.text_path import StructuralCheck
from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, registered
from brain.ops.acceptance_ingest import (
    EICAR_HEAD,
    EICAR_TAIL,
    LINK_CHECKED,
    LINK_PHRASE,
    a_pdf_naming_script,
    a_word_document_holding_a_macro_part,
)
from brain.settings import settings_from
from brain.tools.fetch import FetchedBytes
from tests.fixtures.memory_store import MemoryStore
from tests.unit.test_acceptance import at_head, counts

MODULE = "brain.ops.acceptance_ingest"

SCAN = "a_file_carrying_script_or_macros_is_refused_before_it_is_read"
VIRUS = "the_antivirus_test_file_is_refused_as_malware"
LINK = "a_link_is_fetched_read_and_found_in_its_department"
QUEUE = "a_full_ingestion_queue_refuses_with_a_retry_hint"
QUEUED = "a_queued_file_is_kept_in_the_store_and_read_by_the_worker"
WIDTH = "the_embedding_width_is_the_installs_and_held_under_vectors"
OFFER = "a_price_list_sent_as_a_document_is_offered_to_classification"

#: The recorded page the documentation domain answers with, as its own markup has it.
EXAMPLE_PAGE = (
    b"<!doctype html><html><head><title>Example Domain</title></head><body><div>"
    b"<h1>Example Domain</h1><p>This domain is for use in documentation examples without "
    b"needing permission. Avoid use in operations.</p></div></body></html>"
)


# ------------------------------------------------------------------------ the figures
def test_the_module_declares_one_check_per_door() -> None:
    """Seven checks and the leaves each proves. Delete this and a check can lose a leaf with the
    page showing the same rows, and the leaf closes on a check that never looked."""
    checks = [(one.name, one.leaves) for one in registered((MODULE,))]
    assert checks == [
        (SCAN, ("M7.1.3",)),
        (VIRUS, ("M7.1.3",)),
        (LINK, ("M7.1.2",)),
        (QUEUE, ("M7.1.5",)),
        (QUEUED, ("M7.1.5", "M7.1.4")),
        (WIDTH, ("M7.7.4",)),
        (OFFER, ("M7.7.3",)),
    ]


def _verdict(content: bytes, media_type: MediaType) -> Any:
    admit_upload(filename="file", declared_type=media_type.value, content=content)
    return StructuralCheck().scan(content)


def test_the_inert_files_are_refused_by_the_product_s_scan_for_the_cause_the_check_names() -> None:
    """Asked of the product's own structural check, outside the module. Delete this and the files
    can drift so the scan refuses them for another cause, or not at all, and the check fails on
    every install for a reason that is the fixture's."""
    pdf = _verdict(a_pdf_naming_script("QZ00"), MediaType.PDF)
    word = _verdict(a_word_document_holding_a_macro_part("Check", "QZ00"), MediaType.DOCX)
    assert (pdf.verdict, pdf.cause) == (ScanVerdict.INFECTED, ScanCause.ACTIVE_CONTENT)
    assert (word.verdict, word.cause) == (ScanVerdict.INFECTED, ScanCause.MACROS)


def test_the_antivirus_test_string_is_whole_only_at_run_time() -> None:
    """`A_REFUSED_FILE_IS_BUILT_INERT`: the test signature is joined from two halves, so the module
    source never holds it whole and no scanner flags the repository. Delete this and somebody
    tidies the halves into one literal, and a developer's antivirus quarantines the module."""
    whole = EICAR_HEAD + EICAR_TAIL
    source = Path("src/brain/ops/acceptance_ingest.py").read_text(encoding="utf-8")
    assert whole.startswith("X5O!P%@AP[4") and whole.endswith("TEST-FILE!$H+H*")
    assert len(whole) == 68
    assert whole not in source


def test_the_link_names_the_documentation_domain_and_no_company() -> None:
    """RFC 2606 reserves the domain for documentation. Delete this and the check can be pointed at
    a real company's site, which is a fetch the owner never agreed to and a client value in the
    source."""
    assert LINK_CHECKED == "https://example.com/"
    assert LINK_PHRASE.encode() in EXAMPLE_PAGE


# --------------------------------------------------------------------- on an install
class _Site:
    """The documentation domain as a recorded page, so no test asks the network."""

    def get_once(self, url: str, *, address: str, max_bytes: int) -> FetchedBytes | str:
        return FetchedBytes(body=EXAMPLE_PAGE, final_url=url)


class _Public:
    def resolve(self, host: str) -> Sequence[str]:
        return ["93.184.216.34"]


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_ingest") as url:
        yield url


@pytest.fixture
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    offline_install(monkeypatch)


def offline_install(monkeypatch: pytest.MonkeyPatch) -> None:
    """The link answered by the recorded page, the queue driver's count stood in, and the
    structural check chosen, as a fresh install chooses it."""
    from brain import knowledge_intake_routes

    async def counted(self: Any) -> tuple[int, int]:
        # The queue driver's own schema is the worker's to apply, and the scratch database is
        # migrated by alembic alone, so the driver's count is stood in: an empty queue.
        return 0, 0

    monkeypatch.setattr(knowledge_intake_routes, "make_fetcher", _Site)
    monkeypatch.setattr(knowledge_intake_routes, "make_resolver", _Public)
    monkeypatch.setattr(knowledge_intake_routes.DriverQueue, "counts", counted)
    monkeypatch.setenv("INSTALL_KNOWLEDGE_SCANNER", "structural")


def run_ingest(url: str, *names: str) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url

    settings = settings_from({"BRAIN_DATABASE_URL": url})
    checks = [one for one in registered((MODULE,)) if not names or one.name in names]
    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings,
            commit="abc1234",
            checks=checks,
            force=True,
        )
    )
    return {one.name: (one.outcome, one.reason) for one in results}


@pytest.mark.needs_db
def test_on_an_install_with_no_antivirus_and_no_store_five_pass_and_two_are_not_run(
    install: str, offline: None
) -> None:
    """**The module as the worker runs it on a fresh install.** The scan, the link, the queue, the
    width and the price list's offer pass; the antivirus half and the queued file say why they
    were not asked, in their own sentences, and nothing a check wrote is left. Delete this and a
    check that can never pass on a real schema, or one that fails where it should say it was not
    run, reaches the owner's server first."""
    before = counts(install)
    outcomes = run_ingest(install)
    assert counts(install) == before
    assert {name: outcome for name, (outcome, _) in outcomes.items()} == {
        SCAN: PASSED,
        VIRUS: NOT_RUN,
        LINK: PASSED,
        QUEUE: PASSED,
        QUEUED: NOT_RUN,
        WIDTH: PASSED,
        OFFER: PASSED,
    }, outcomes
    assert "no antivirus" in outcomes[VIRUS][1]
    assert "no object store" in outcomes[QUEUED][1]


@pytest.fixture
def stored(monkeypatch: pytest.MonkeyPatch) -> MemoryStore:
    """An object store connected, held in memory."""
    from brain.ops import object_store

    memory = MemoryStore()
    connected = object_store.ObjectStore(backend=cast(Any, memory), prefix="brain")
    monkeypatch.setattr(object_store, "object_store_at_start", lambda *args, **kw: connected)
    return memory


@pytest.mark.needs_db
def test_with_a_store_the_queued_file_is_kept_read_and_removed_after(
    install: str, offline: None, stored: MemoryStore
) -> None:
    """With an object store connected the queued file's original is kept byte for byte, the
    worker's job reads it, and both keys it wrote are gone when the check ends. Delete this and
    M7.1.4 and M7.1.5 close on a check no test ever saw pass, or one that leaves originals behind
    on the owner's store."""
    outcomes = run_ingest(install, QUEUED)
    assert outcomes == {QUEUED: (PASSED, "")}, outcomes
    assert stored.objects == {}


@pytest.mark.needs_db
def test_with_an_antivirus_the_test_file_is_refused_as_malware(
    install: str, offline: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With ClamAV chosen and a daemon that reports the test signature, the antivirus half
    passes. Delete this and it can never be shown passing, and it stays not run for ever."""
    from brain.knowledge import scanners, uploads

    class _Daemon:
        def exchange(self, frames: tuple[bytes, ...]) -> bytes:
            return b"stream: Win.Test.EICAR_HDB-1 FOUND" + bytes(1)

    monkeypatch.setenv("INSTALL_KNOWLEDGE_SCANNER", "clamav")
    monkeypatch.setenv("INSTALL_CLAMAV_ADDRESS", "clamav.acceptance.invalid:3310")
    monkeypatch.setattr(
        uploads,
        "configured_scanner",
        lambda: scanners.configured_scanner(make_link=lambda host, port: _Daemon()),
    )
    assert run_ingest(install, VIRUS) == {VIRUS: (PASSED, "")}


def _failed(url: str, name: str) -> str:
    [(outcome, reason)] = run_ingest(url, name).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_a_scan_that_misses_script_fails_the_scan_check(
    install: str, offline: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The structural check blind to a PDF's script action. Delete this and M7.1.3 closes on a
    check that never saw a refusal."""
    from brain.knowledge import text_path

    monkeypatch.setattr(text_path, "PDF_ACTIVE_NAMES", ())
    said = _failed(install, SCAN)
    assert "reached the parser" in said or "was read" in said


@pytest.mark.needs_db
def test_a_queue_that_takes_everything_fails_the_queue_check(
    install: str, offline: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A queue with no depth limit, which accepts and drops later. Delete this and M7.1.5 closes
    on a check that never saw backpressure."""
    from brain.knowledge import uploads
    from brain.knowledge.ingest import QueueDecision

    monkeypatch.setattr(uploads, "admit_to_queue", lambda **kwargs: QueueDecision(admitted=True))
    assert "full queue" in _failed(install, QUEUE)


@pytest.mark.needs_db
def test_a_width_refusal_that_refuses_nothing_fails_the_width_check(
    install: str, offline: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The migration's refusal emptied of its test. Delete this and M7.7.4 closes on a check that
    never saw a width change refused."""
    from brain.knowledge import search

    monkeypatch.setattr(search, "width_change_refusal", lambda dimensions: "SELECT 1")
    assert "let a width change pass" in _failed(install, WIDTH)


@pytest.mark.needs_db
def test_a_spreadsheet_read_as_a_document_fails_the_offer_check(
    install: str, offline: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The doors as they were until 2026-09-29, taking a spreadsheet as a document. Delete this and
    M7.7.3 closes on a check that never saw a door make the offer."""
    from brain import knowledge_intake_routes, knowledge_routes

    for module in (knowledge_routes, knowledge_intake_routes):
        monkeypatch.setattr(module, "offer_a_table_file", lambda *args: None)
    assert "not offered" in _failed(install, OFFER)
