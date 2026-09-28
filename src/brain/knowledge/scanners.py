"""Which scanner a file meets before it is read, and the antivirus an install may choose.

`brain.knowledge.scanning` makes the scan a type the parser cannot be reached without, and names
the protocol a scanner satisfies. This module decides which scanner that is on an install, and
holds the one antivirus the product can speak to.

**The default is the structural check, and it is the default because it needs nothing.** Every
install runs `brain.knowledge.text_path.StructuralCheck` in process: it refuses the shapes that
attack the parser this product runs (an archive that expands without bound, an encrypted part,
macros, a declared XML entity, script or an embedded file in a PDF) and says in its own name that
it recognises no malware. Whether an install also runs an antivirus is a question about the
server's memory, which the owner has not answered (`docs/needs-rupash.md` items 25 and 105), so
it is configuration and it ships off: `INSTALL_KNOWLEDGE_SCANNER` is `structural` until somebody
sets it to `clamav`. See `THE_ANTIVIRUS_IS_A_CHOICE_AND_THE_STRUCTURAL_CHECK_IS_NOT`.

**Chosen, ClamAV is added to the structural check, never put in its place.** The two answer
different questions. ClamAV recognises known malware and says nothing about a zip that unpacks to
a terabyte, which it may itself spend minutes on; the structural check is the reverse. So the file
meets the structural check first, which is cheap and in process, and ClamAV only if that is
clean, and both have to say clean. See `AN_ANTIVIRUS_IS_ADDED_AND_NEVER_SUBSTITUTED`.

**Chosen and not answering, every upload is refused, and says so.** A scanner that did not answer
has reached no verdict, and `ingest.assert_clean` refuses unscannable as it refuses infected. The
tempting alternative, falling back to the structural check when the daemon is down, is a setting
that says antivirus while the install runs none, which is worse than the setting being off: an
administrator who chose it believes it. So the refusal names `SCANNER_UNREACHABLE`, whose words
say nothing is wrong with the file and that an administrator checks the antivirus. A choice this
module cannot build at all, an address that is not host:port or a scanner name nothing
recognises, is refused the same way under `SCANNER_NOT_SET_UP`, per file, rather than by stopping
the process: a knowledge setting is not a reason every other screen stops answering.

**The daemon is spoken to over its own documented protocol, with no client library.** ClamAV's
`clamd` takes `zINSTREAM` followed by the bytes in length-prefixed chunks and a zero-length chunk,
and answers `stream: OK`, `stream: <signature> FOUND` or a line ending `ERROR` (clamd(8), the
`INSTREAM` command, and clamd.conf(5) `StreamMaxLength` for the size refusal). `clamd_verdict` reads
those three shapes; anything else is an error rather than a guess. A client library was rejected
for the reason `brain.ops.object_store` gives about boto3's credential chain, in miniature: the
protocol is four lines and a dependency is a licence review, a supply chain and an update cadence
for four lines. `ClamdLink` is the seam, so the replies are tested as recorded bytes and the socket
against a listener on this machine, and no test reaches a daemon.

**The signature name reaches the operator's log and never the uploader.** It is vendor prose
(`Win.Test.EICAR_HDB-1`) and `scanning.ScanReport` has no field for it by design; the uploader is
told the cause, `MALWARE_SIGNATURE`, and what to do.

Task ids: M7.1.3
"""

from __future__ import annotations

import enum
import socket
import struct
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final, Protocol

import structlog

from brain.install import value_of
from brain.knowledge.ingest import ScanCause, ScanVerdict
from brain.knowledge.scanning import Scanner, ScanReport
from brain.knowledge.text_path import STRUCTURAL_CHECK, StructuralCheck

log = structlog.get_logger()

# ------------------------------------------------------------------ written-down reasons
#: Why the antivirus ships off and the structural check does not.
THE_ANTIVIRUS_IS_A_CHOICE_AND_THE_STRUCTURAL_CHECK_IS_NOT: Final = (
    "The structural check runs in process and needs nothing, so every install runs it. An "
    "antivirus is a daemon with a signature database held in memory, and whether a server can "
    "hold one is the owner's capacity decision, so INSTALL_KNOWLEDGE_SCANNER ships as structural "
    "and clamav is a value an administrator sets. Nothing here turns it on by itself."
)

#: Why ClamAV is layered over the structural check rather than replacing it.
AN_ANTIVIRUS_IS_ADDED_AND_NEVER_SUBSTITUTED: Final = (
    "ClamAV recognises known malware and says nothing about an archive built to exhaust its "
    "reader; the structural check refuses that archive and recognises no malware. Each misses "
    "what the other catches, so a chosen antivirus is added after the structural check and both "
    "must say clean. The structural check goes first because it is in process and cheap, and a "
    "file it refuses never costs the daemon anything."
)

#: Why a chosen antivirus that does not answer refuses rather than falling back.
A_CHOSEN_ANTIVIRUS_THAT_DOES_NOT_ANSWER_REFUSES: Final = (
    "Falling back to the structural check while the daemon is down makes the setting say "
    "antivirus on an install running none, and the administrator who chose it believes it. So "
    "a daemon that does not answer is a scan with no verdict, refused as unscanned is refused, "
    "naming SCANNER_UNREACHABLE, until it answers again or the setting is changed back."
)

# ------------------------------------------------------------------ the figures
#: The setting naming the scanner, and the one naming where ClamAV listens.
SCANNER_SETTING: Final = "INSTALL_KNOWLEDGE_SCANNER"
CLAMAV_ADDRESS_SETTING: Final = "INSTALL_CLAMAV_ADDRESS"

#: The scanner's name on every verdict ClamAV reaches.
CLAMAV: Final = "ClamAV"

#: How long one scan may take, connect to verdict. A fifty megabyte PDF is seconds of work for
#: the daemon; longer than this is a daemon that is not coming back, and a request is waiting.
CLAMAV_TIMEOUT_SECONDS: Final = 60.0

#: How much of the file one `INSTREAM` chunk carries. The protocol allows any length up to the
#: daemon's stream limit; this keeps one `sendall` small enough to fail fast on a closed socket.
CLAMAV_CHUNK_BYTES: Final = 64 * 1024

#: The command, in the NUL-terminated form the daemon answers with a NUL-terminated line.
INSTREAM_COMMAND: Final = b"zINSTREAM\x00"

#: The chunk that ends a stream: a length of zero.
END_OF_STREAM: Final = struct.pack("!I", 0)

#: The most of a reply that is read. A verdict is one short line; more is not a verdict.
MAX_REPLY_BYTES: Final = 1024

#: The characters of a signature name that reach the operator's log.
_SIGNATURE_CHARS: Final = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_:"
)

#: How much of a signature name reaches the log.
SIGNATURE_LOG_CHARS: Final = 80


class ScannerChoice(enum.StrEnum):
    """What `INSTALL_KNOWLEDGE_SCANNER` may name."""

    STRUCTURAL = "structural"
    CLAMAV = "clamav"


# ------------------------------------------------------------------ ClamAV's replies
@dataclass(frozen=True)
class ClamdAnswer:
    """What one reply from the daemon means: a verdict, the cause, and a signature for the log."""

    verdict: ScanVerdict
    cause: ScanCause | None = None
    signature: str = ""


def clamd_verdict(reply: bytes) -> ClamdAnswer:
    """Read one `INSTREAM` reply. The three documented shapes, and everything else is an error.

    `stream: OK` is clean. `stream: <name> FOUND` is infected, with the name kept for the log.
    A size refusal (`INSTREAM size limit exceeded. ERROR`) is unscannable as too large, because
    its remedy differs from a daemon fault. Anything else, an empty reply included, is a daemon
    that answered without a verdict, which is not clean.
    """
    text = reply.rstrip(b"\x00").decode("ascii", errors="replace").strip()
    if text == "stream: OK":
        return ClamdAnswer(verdict=ScanVerdict.CLEAN)
    if text.startswith("stream: ") and text.endswith(" FOUND"):
        name = text[len("stream: ") : -len(" FOUND")]
        kept = "".join(ch for ch in name if ch in _SIGNATURE_CHARS)[:SIGNATURE_LOG_CHARS]
        return ClamdAnswer(
            verdict=ScanVerdict.INFECTED, cause=ScanCause.MALWARE_SIGNATURE, signature=kept
        )
    if "size limit exceeded" in text.lower():
        return ClamdAnswer(verdict=ScanVerdict.UNSCANNABLE, cause=ScanCause.TOO_LARGE_TO_SCAN)
    return ClamdAnswer(verdict=ScanVerdict.UNSCANNABLE, cause=ScanCause.SCANNER_FAILED)


def instream_frames(content: bytes, *, chunk: int = CLAMAV_CHUNK_BYTES) -> tuple[bytes, ...]:
    """The bytes sent for one scan: the command, each chunk with its length, then the end."""
    frames = [INSTREAM_COMMAND]
    for start in range(0, len(content), chunk):
        piece = content[start : start + chunk]
        frames.append(struct.pack("!I", len(piece)) + piece)
    frames.append(END_OF_STREAM)
    return tuple(frames)


# ------------------------------------------------------------------ the daemon
class ClamdUnreachableError(Exception):
    """The daemon could not be connected to at all."""


class ClamdLink(Protocol):
    """Sends the frames of one scan and answers the reply. The seam every test stands in for.

    Raises `ClamdUnreachableError` when no connection was made, and returns whatever came back
    otherwise, an empty reply included: a daemon that closed without answering answered, badly.
    """

    def exchange(self, frames: tuple[bytes, ...]) -> bytes: ...


@dataclass(frozen=True)
class ClamdSocket:
    """`ClamdLink` over TCP to the daemon at `host`:`port`."""

    host: str
    port: int
    timeout_seconds: float = CLAMAV_TIMEOUT_SECONDS

    def exchange(self, frames: tuple[bytes, ...]) -> bytes:
        try:
            connection = socket.create_connection(
                (self.host, self.port), timeout=self.timeout_seconds
            )
        except OSError as exc:
            raise ClamdUnreachableError(type(exc).__name__) from None
        reply = bytearray()
        with connection:
            try:
                for frame in frames:
                    connection.sendall(frame)
            except OSError:
                # The daemon closes a stream it will not take, the size limit among them, and
                # says why before it does; what it said is read below rather than lost here.
                pass
            try:
                while len(reply) < MAX_REPLY_BYTES and not reply.endswith(b"\x00"):
                    got = connection.recv(MAX_REPLY_BYTES)
                    if not got:
                        break
                    reply += got
            except OSError:
                pass
        return bytes(reply)


@dataclass(frozen=True)
class ClamavScanner:
    """`scanning.Scanner` over a ClamAV daemon. Told only the bytes, as the protocol requires."""

    link: ClamdLink

    def scan(self, content: bytes) -> ScanReport:
        try:
            reply = self.link.exchange(instream_frames(content))
        except ClamdUnreachableError as exc:
            log.warning("knowledge.antivirus_unreachable", scanner=CLAMAV, error=str(exc))
            return ScanReport(
                verdict=ScanVerdict.UNSCANNABLE,
                scanner=CLAMAV,
                cause=ScanCause.SCANNER_UNREACHABLE,
            )
        answer = clamd_verdict(reply)
        if answer.verdict is ScanVerdict.INFECTED:
            log.warning("knowledge.antivirus_refused", scanner=CLAMAV, signature=answer.signature)
        elif answer.verdict is not ScanVerdict.CLEAN:
            log.warning("knowledge.antivirus_no_verdict", scanner=CLAMAV, cause=answer.cause)
        return ScanReport(verdict=answer.verdict, scanner=CLAMAV, cause=answer.cause)


# ------------------------------------------------------------------ layering and refusing
@dataclass(frozen=True)
class Layered:
    """Two scanners, both of which must say clean; `AN_ANTIVIRUS_IS_ADDED_AND_NEVER_SUBSTITUTED`.

    The first refusal is the one reported, with the name of the scanner that made it, so the
    uploader is told which of the two looked and why. A clean verdict names both.
    """

    first: Scanner
    then: Scanner

    def scan(self, content: bytes) -> ScanReport:
        one = self.first.scan(content)
        if one.verdict is not ScanVerdict.CLEAN:
            return one
        two = self.then.scan(content)
        if two.verdict is not ScanVerdict.CLEAN:
            return two
        return ScanReport(verdict=ScanVerdict.CLEAN, scanner=f"{one.scanner} and {two.scanner}")


#: The name a scanner that is not set up reports under.
NOT_SET_UP: Final = "the scanner this install names, which is not set up"


@dataclass(frozen=True)
class NotSetUp:
    """What a choice this module cannot build scans with: nothing, and every file refused.

    See the module docstring on why this refuses per file rather than stopping the process.
    """

    def scan(self, content: bytes) -> ScanReport:
        return ScanReport(
            verdict=ScanVerdict.UNSCANNABLE,
            scanner=NOT_SET_UP,
            cause=ScanCause.SCANNER_NOT_SET_UP,
        )


# ------------------------------------------------------------------ the choice
def clamav_address(address: str) -> tuple[str, int] | None:
    """`host:port` as a host and a port, or None for anything that is not one.

    A bracketed IPv6 literal is accepted as `[::1]:3310`; an unbracketed one is refused, for the
    reason `brain.tools.fetch.assert_fetchable` gives about reading one generously.
    """
    host, colon, port = address.strip().rpartition(":")
    if not colon or not host or not port.isdigit():
        return None
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    elif ":" in host:
        return None
    number = int(port)
    if not host or not 0 < number < 65536:
        return None
    return host, number


#: How a ClamAV link is made from an address. A parameter of `configured_scanner` so a test can
#: stand one in; every install uses `ClamdSocket`.
LinkMaker = Callable[[str, int], ClamdLink]


def _socket(host: str, port: int) -> ClamdLink:
    return ClamdSocket(host=host, port=port)


def configured_scanner(
    *,
    env: Mapping[str, str] | None = None,
    saved: Mapping[str, str] | None = None,
    make_link: LinkMaker = _socket,
) -> Scanner:
    """The scanner this install's setting names. The structural check unless ClamAV is chosen.

    Read at the moment a file is scanned rather than once at start, so a scanner chosen in the
    console applies to the next upload without a restart; `brain.install.value_of` is the one
    reader. See the module docstring for each of the three outcomes.
    """
    chosen = value_of(SCANNER_SETTING, env=env, saved=saved).strip().lower()
    if chosen == ScannerChoice.STRUCTURAL:
        return StructuralCheck()
    if chosen == ScannerChoice.CLAMAV:
        where = clamav_address(value_of(CLAMAV_ADDRESS_SETTING, env=env, saved=saved))
        if where is not None:
            return Layered(first=StructuralCheck(), then=ClamavScanner(link=make_link(*where)))
    log.warning("knowledge.scanner_not_set_up", setting=SCANNER_SETTING)
    return NotSetUp()


def checked_by(
    *, env: Mapping[str, str] | None = None, saved: Mapping[str, str] | None = None
) -> str:
    """What a page says checks a file before it is read, from the same setting the scan reads."""
    chosen = value_of(SCANNER_SETTING, env=env, saved=saved).strip().lower()
    if chosen == ScannerChoice.STRUCTURAL:
        return STRUCTURAL_CHECK
    if chosen == ScannerChoice.CLAMAV and clamav_address(
        value_of(CLAMAV_ADDRESS_SETTING, env=env, saved=saved)
    ):
        return f"{STRUCTURAL_CHECK} and {CLAMAV}"
    return NOT_SET_UP
