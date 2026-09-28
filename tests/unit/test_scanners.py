"""The scanner a file meets, the cause a refusal names, and ClamAV as a choice that ships off.

Three parts. The structural check's refusals are produced from files built in memory, so the cause
each path names is read off the raw bytes rather than off a report a test wrote. ClamAV's replies
are recorded as bytes in the shapes its daemon documents (clamd(8), the `INSTREAM` command:
`stream: OK`, `stream: <name> FOUND`, and `INSTREAM size limit exceeded. ERROR` for a stream past
clamd.conf(5)'s `StreamMaxLength`), and the socket is exercised against a listener on this machine
that speaks the same protocol. No test reaches a real daemon or the network.

Task ids: M7.1.3
"""

from __future__ import annotations

import socket
import struct
import threading
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from brain.install import BY_NAME
from brain.knowledge import text_path
from brain.knowledge.ingest import (
    SCAN_CAUSE_TEXT,
    IngestRefused,
    MediaType,
    ScanCause,
    ScanVerdict,
    admit_upload,
)
from brain.knowledge.scanners import (
    CLAMAV,
    CLAMAV_ADDRESS_SETTING,
    END_OF_STREAM,
    INSTREAM_COMMAND,
    NOT_SET_UP,
    SCANNER_SETTING,
    ClamavScanner,
    ClamdSocket,
    ClamdUnreachableError,
    Layered,
    NotSetUp,
    ScannerChoice,
    checked_by,
    clamav_address,
    clamd_verdict,
    configured_scanner,
    instream_frames,
)
from brain.knowledge.scanning import ScanReport, scan_for_parsing
from brain.knowledge.text_path import STRUCTURAL_CHECK, StructuralCheck
from tests.fixtures.documents import a_pdf, a_word_document, a_zip, with_part

#: A reply of each shape the daemon documents, as the bytes it sends.
CLEAN_REPLY = b"stream: OK\x00"
FOUND_REPLY = b"stream: Win.Test.EICAR_HDB-1 FOUND\x00"
TOO_LARGE_REPLY = b"INSTREAM size limit exceeded. ERROR\x00"
ERROR_REPLY = b"stream: Can't allocate memory ERROR\x00"

WORD = a_word_document(paragraphs=["Sign the list."])

NOTHING_SAVED: dict[str, str] = {}


def refusal_of(content: bytes, media_type: MediaType, scanner: object) -> str:
    """The sentence an uploader reads when the scan refuses this file."""
    upload = admit_upload(filename="file", declared_type=media_type.value, content=content)
    with pytest.raises(IngestRefused) as refused:
        scan_for_parsing(upload, content, scanner=scanner)  # type: ignore[arg-type]
    return str(refused.value)


class Link:
    """A `ClamdLink` answering a recorded reply, or unreachable, and keeping what it was sent."""

    def __init__(self, reply: bytes = CLEAN_REPLY, *, unreachable: bool = False) -> None:
        self.reply = reply
        self.unreachable = unreachable
        self.sent: list[tuple[bytes, ...]] = []

    def exchange(self, frames: tuple[bytes, ...]) -> bytes:
        self.sent.append(frames)
        if self.unreachable:
            raise ClamdUnreachableError("ConnectionRefusedError")
        return self.reply


# ------------------------------------------------------------------ causes
def test_every_scan_cause_has_its_own_words() -> None:
    """A cause with no wording renders a refusal that names nothing, and two causes sharing
    words are one cause with two names. Delete this and a member added to `ScanCause` can reach
    an uploader as a blank."""
    assert set(SCAN_CAUSE_TEXT) == set(ScanCause)
    assert all(text.strip() for text in SCAN_CAUSE_TEXT.values())
    assert len(set(SCAN_CAUSE_TEXT.values())) == len(ScanCause)


@pytest.mark.parametrize(
    ("content", "verdict", "cause"),
    [
        (with_part(WORD, "word/vbaProject.bin", b"m"), ScanVerdict.INFECTED, ScanCause.MACROS),
        (
            a_zip({"word/document.xml": bytes(4 * 1024 * 1024)}),
            ScanVerdict.INFECTED,
            ScanCause.EXPANDS_WITHOUT_BOUND,
        ),
        (
            with_part(WORD, "word/document.xml", b'<!DOCTYPE x [<!ENTITY a "b">]><x/>'),
            ScanVerdict.INFECTED,
            ScanCause.XML_ENTITIES,
        ),
        (
            a_zip({"word/document.xml": b"<w:document/>"}, encrypted=True),
            ScanVerdict.UNSCANNABLE,
            ScanCause.ENCRYPTED_PART,
        ),
        (b"PK\x03\x04 this is not a zip", ScanVerdict.UNSCANNABLE, ScanCause.UNOPENABLE),
        (
            a_pdf("x", extra="/OpenAction << /S /JavaScript /JS (go) >> "),
            ScanVerdict.INFECTED,
            ScanCause.ACTIVE_CONTENT,
        ),
        (
            b"Sixteen bytes ok" + bytes((0xFF, 0xFE)),
            ScanVerdict.UNSCANNABLE,
            ScanCause.NOT_READABLE_TEXT,
        ),
        (b"Sixteen bytes ok" + bytes(3), ScanVerdict.UNSCANNABLE, ScanCause.NOT_READABLE_TEXT),
        (
            bytes((0x89,)) + b"PNG\r\n\x1a\n" + bytes(8),
            ScanVerdict.UNSCANNABLE,
            ScanCause.NOT_CHECKABLE,
        ),
    ],
)
def test_the_structural_check_names_a_cause_on_every_path_that_refuses(
    content: bytes, verdict: ScanVerdict, cause: ScanCause
) -> None:
    """**M7.1.3's "refused naming the cause", read off the bytes.** Each hostile shape is built
    as a file and the check's own report is asked what it found. Delete this and a branch can
    refuse with no cause, which the uploader is told as `UNSTATED`, or with another branch's
    cause, which tells them to fix the wrong thing."""
    report = StructuralCheck().scan(content)

    assert (report.verdict, report.cause) == (verdict, cause)
    assert report.scanner == STRUCTURAL_CHECK


def test_the_archive_ceilings_name_the_same_cause_as_the_ratio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Too many parts and too much in total are both an archive built to exhaust its reader.
    Delete this and the two ceilings can refuse with a cause that sends the uploader elsewhere."""
    parts = {f"word/part{index}.xml": b"<x/>" for index in range(5)}
    monkeypatch.setattr(text_path, "MAX_ARCHIVE_ENTRIES", 4)
    assert StructuralCheck().scan(a_zip(parts)).cause is ScanCause.EXPANDS_WITHOUT_BOUND
    monkeypatch.setattr(text_path, "MAX_ARCHIVE_ENTRIES", 2000)
    monkeypatch.setattr(text_path, "MAX_EXPANDED_BYTES", 10)
    assert StructuralCheck().scan(a_zip(parts)).cause is ScanCause.EXPANDS_WITHOUT_BOUND


def test_a_clean_file_carries_no_cause_and_a_clean_report_cannot_be_given_one() -> None:
    """The positive case for the table above, and the rule that keeps it honest: a report saying
    clean and giving a reason to refuse is two reports. Delete this and a check that attaches a
    cause to everything passes the table."""
    for content in (WORD, a_pdf("Sign the list."), "Sign the list, café.".encode()):
        report = StructuralCheck().scan(content)
        assert (report.verdict, report.cause) == (ScanVerdict.CLEAN, None)
    with pytest.raises(IngestRefused, match="clean verdict carries no cause"):
        ScanReport(verdict=ScanVerdict.CLEAN, scanner="x", cause=ScanCause.MACROS)


def test_a_refusal_tells_the_uploader_which_scanner_refused_and_why() -> None:
    """The sentence as the route sends it: the scanner's name and the cause's words. Delete this
    and `assert_clean` can go back to "refused by structural check", which sends the same file
    straight back."""
    told = refusal_of(
        with_part(WORD, "word/vbaProject.bin", b"m"), MediaType.DOCX, StructuralCheck()
    )

    assert STRUCTURAL_CHECK in told
    assert SCAN_CAUSE_TEXT[ScanCause.MACROS] in told


def test_a_scanner_that_gives_no_cause_is_told_as_unstated() -> None:
    """A scanner this product did not write may know no causes. Delete this and its refusal
    raises a KeyError instead of telling the uploader anything."""

    class Silent:
        def scan(self, content: bytes) -> ScanReport:
            return ScanReport(verdict=ScanVerdict.UNSCANNABLE, scanner="a plugin's scanner")

    told = refusal_of(WORD, MediaType.DOCX, Silent())

    assert SCAN_CAUSE_TEXT[ScanCause.UNSTATED] in told
    assert "unscanned is not clean" in told


# ------------------------------------------------------------------ ClamAV's replies
@pytest.mark.parametrize(
    ("reply", "verdict", "cause"),
    [
        (CLEAN_REPLY, ScanVerdict.CLEAN, None),
        (FOUND_REPLY, ScanVerdict.INFECTED, ScanCause.MALWARE_SIGNATURE),
        (TOO_LARGE_REPLY, ScanVerdict.UNSCANNABLE, ScanCause.TOO_LARGE_TO_SCAN),
        (ERROR_REPLY, ScanVerdict.UNSCANNABLE, ScanCause.SCANNER_FAILED),
        (b"", ScanVerdict.UNSCANNABLE, ScanCause.SCANNER_FAILED),
        (b"PONG\x00", ScanVerdict.UNSCANNABLE, ScanCause.SCANNER_FAILED),
        (b"stream: OK FOUND\x00", ScanVerdict.INFECTED, ScanCause.MALWARE_SIGNATURE),
    ],
)
def test_each_documented_reply_is_read_as_its_verdict_and_anything_else_is_not_clean(
    reply: bytes, verdict: ScanVerdict, cause: ScanCause | None
) -> None:
    """The three documented shapes, and that nothing else is ever clean. Delete this and an empty
    reply from a daemon that died mid-scan, or an answer to the wrong command, reads as clean."""
    answer = clamd_verdict(reply)

    assert (answer.verdict, answer.cause) == (verdict, cause)


def test_a_signature_is_kept_for_the_log_and_never_reaches_the_report() -> None:
    """A signature name is vendor prose, and `ScanReport` has no field for it by design. Delete
    this and a signature name can be carried into the message the uploader reads."""
    assert clamd_verdict(FOUND_REPLY).signature == "Win.Test.EICAR_HDB-1"
    report = ClamavScanner(link=Link(FOUND_REPLY)).scan(b"x")

    assert "EICAR" not in repr(report)
    assert (report.verdict, report.cause, report.scanner) == (
        ScanVerdict.INFECTED,
        ScanCause.MALWARE_SIGNATURE,
        CLAMAV,
    )


def test_a_scan_is_sent_as_the_command_then_length_prefixed_chunks_then_a_zero_chunk() -> None:
    """The protocol's framing, which a daemon enforces by hanging or refusing. Delete this and a
    little-endian length or a missing terminator is found on the first install that chose it."""
    frames = instream_frames(b"abcdefgh", chunk=3)

    assert frames[0] == INSTREAM_COMMAND == b"zINSTREAM\x00"
    assert frames[1:-1] == (
        struct.pack("!I", 3) + b"abc",
        struct.pack("!I", 3) + b"def",
        struct.pack("!I", 2) + b"gh",
    )
    assert frames[-1] == END_OF_STREAM == bytes(4)


def test_a_daemon_that_does_not_answer_is_a_scan_with_no_verdict() -> None:
    """**Chosen and unreachable refuses, clearly.** Delete this and an unreachable daemon raises
    out of the scan as a 500, or worse is read as clean."""
    report = ClamavScanner(link=Link(unreachable=True)).scan(b"x")

    assert (report.verdict, report.cause) == (
        ScanVerdict.UNSCANNABLE,
        ScanCause.SCANNER_UNREACHABLE,
    )
    told = refusal_of(WORD, MediaType.DOCX, ClamavScanner(link=Link(unreachable=True)))
    assert SCAN_CAUSE_TEXT[ScanCause.SCANNER_UNREACHABLE] in told


# ------------------------------------------------------------------ the socket
@contextmanager
def a_daemon(reply: bytes) -> Iterator[tuple[int, list[bytes]]]:
    """A listener on this machine speaking `INSTREAM`: it reads the command and every chunk to
    the zero-length one, keeps what arrived, and answers `reply`."""
    server = socket.create_server(("127.0.0.1", 0))
    received: list[bytes] = []

    def serve() -> None:
        connection, _ = server.accept()
        with connection:
            reader = connection.makefile("rb")
            received.append(reader.read(len(INSTREAM_COMMAND)))
            while True:
                size = struct.unpack("!I", reader.read(4))[0]
                if size == 0:
                    break
                received.append(reader.read(size))
            connection.sendall(reply)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield server.getsockname()[1], received
    finally:
        thread.join(timeout=5)
        server.close()


def test_the_socket_sends_the_whole_file_and_reads_the_daemons_reply() -> None:
    """The real transport, end to end on a loopback socket. Delete this and `ClamdSocket` can
    stop sending the terminator, or read the reply before the daemon has sent it, with every
    stand-in test green."""
    body = bytes(range(256)) * 600
    with a_daemon(FOUND_REPLY) as (port, received):
        reply = ClamdSocket(host="127.0.0.1", port=port, timeout_seconds=5).exchange(
            instream_frames(body)
        )

    assert reply == FOUND_REPLY
    assert received[0] == INSTREAM_COMMAND
    assert b"".join(received[1:]) == body


def test_a_port_nobody_listens_on_is_unreachable() -> None:
    """Delete this and a refused connection is read as a reply, empty, and told as a daemon
    error rather than as the antivirus not answering."""
    closed = socket.create_server(("127.0.0.1", 0))
    port = closed.getsockname()[1]
    closed.close()

    with pytest.raises(ClamdUnreachableError):
        ClamdSocket(host="127.0.0.1", port=port, timeout_seconds=2).exchange(instream_frames(b"x"))


# ------------------------------------------------------------------ the choice
def test_the_antivirus_ships_off_and_the_structural_check_is_the_default() -> None:
    """**The owner's capacity decision is open, so ClamAV is not on.** The default is read off
    the declaration and off what an install with nothing set scans with. Delete this and a change
    to the default turns an antivirus on for every install that has no daemon, refusing every
    upload on it."""
    assert BY_NAME[SCANNER_SETTING].default == ScannerChoice.STRUCTURAL
    scanner = configured_scanner(env={}, saved=NOTHING_SAVED)

    assert isinstance(scanner, StructuralCheck)
    assert checked_by(env={}, saved=NOTHING_SAVED) == STRUCTURAL_CHECK


def test_chosen_clamav_is_added_after_the_structural_check_and_both_must_say_clean() -> None:
    """A file the structural check refuses never reaches the daemon, and a clean file meets both.
    Delete this and choosing ClamAV replaces the check that refuses zip bombs, or spends the
    daemon on files already refused."""
    links: list[Link] = []

    def make_link(host: str, port: int) -> Link:
        assert (host, port) == ("clamav.internal", 3310)
        links.append(Link(CLEAN_REPLY))
        return links[-1]

    chosen = {SCANNER_SETTING: "clamav", CLAMAV_ADDRESS_SETTING: "clamav.internal:3310"}
    scanner = configured_scanner(env=chosen, saved=NOTHING_SAVED, make_link=make_link)
    assert isinstance(scanner, Layered)

    refused = scanner.scan(with_part(WORD, "word/vbaProject.bin", b"m"))
    assert (refused.cause, refused.scanner) == (ScanCause.MACROS, STRUCTURAL_CHECK)
    assert links[0].sent == []

    clean = scanner.scan(WORD)
    assert clean.verdict is ScanVerdict.CLEAN
    assert clean.scanner == f"{STRUCTURAL_CHECK} and {CLAMAV}"
    assert len(links[0].sent) == 1
    assert checked_by(env=chosen, saved=NOTHING_SAVED) == f"{STRUCTURAL_CHECK} and {CLAMAV}"


def test_a_saved_choice_outranks_the_environment() -> None:
    """The console saves a choice and the scan reads it at the next upload. Delete this and a
    scanner switched in the console is ignored until somebody edits the server's environment."""
    scanner = configured_scanner(
        env={SCANNER_SETTING: "structural"},
        saved={SCANNER_SETTING: "clamav", CLAMAV_ADDRESS_SETTING: "127.0.0.1:3310"},
        make_link=lambda host, port: Link(),
    )

    assert isinstance(scanner, Layered)


@pytest.mark.parametrize(
    "chosen",
    [
        {SCANNER_SETTING: "clamav", CLAMAV_ADDRESS_SETTING: "no port here"},
        {SCANNER_SETTING: "clamav", CLAMAV_ADDRESS_SETTING: "fd00::1:3310"},
        {SCANNER_SETTING: "clamav", CLAMAV_ADDRESS_SETTING: "clamav:99999"},
        {SCANNER_SETTING: "sophos"},
    ],
)
def test_a_choice_that_cannot_be_built_refuses_every_file_and_says_so(
    chosen: dict[str, str],
) -> None:
    """**Never a silent fall back to the structural check.** Delete this and an administrator who
    chose an antivirus and mistyped its address runs with none, believing otherwise."""
    scanner = configured_scanner(env=chosen, saved=NOTHING_SAVED)

    assert isinstance(scanner, NotSetUp)
    told = refusal_of(a_pdf("Sign the list."), MediaType.PDF, scanner)
    assert NOT_SET_UP in told
    assert SCAN_CAUSE_TEXT[ScanCause.SCANNER_NOT_SET_UP] in told
    assert checked_by(env=chosen, saved=NOTHING_SAVED) == NOT_SET_UP


def test_an_address_is_host_and_port_with_ipv6_only_in_brackets() -> None:
    """The positive and the refused shapes of the one value an administrator types. Delete this
    and an unbracketed IPv6 address is split at its last colon into a host that does not exist."""
    assert clamav_address("clamav:3310") == ("clamav", 3310)
    assert clamav_address(" 10.0.0.5:3310 ") == ("10.0.0.5", 3310)
    assert clamav_address("[fd00::1]:3310") == ("fd00::1", 3310)
    assert clamav_address("fd00::1:3310") is None
    assert clamav_address("clamav") is None
    assert clamav_address(":3310") is None
    assert clamav_address("clamav:0") is None
