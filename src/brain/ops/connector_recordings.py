"""What each connector in this release was tested against, as the Connectors screen says it.

The question the owner asks of a connector before any company has a key for it is two
questions, and the screen answers them apart: **was it tested against recorded responses**,
which is a fact about this release and the same on every install, and **is there a live
credential for it**, which is a fact about one install's vault. Neither implies the other, and
the second never implies a live read: `brain.console.connector_trust.ConnectedRow` carries when
the worker last read a source to the end, and a source nobody has read is said to be unread.

**The record is declared by each connector and held true by a test, not computed from the
recordings.** The recordings are `tests/fixtures/cassettes/`, which is not shipped in the image,
so nothing on a server can count them. Each connector states what it was tested against as the
`recorded` of its own `CONNECTOR` (`brain.connectors.declaration.Recorded`), and `RECORDINGS` is
read off those declarations at start-up, so a new connector needs no edit here.
`tests/unit/test_cassette_replay.py` replays every recording through its connector,
fails when a declared tool or projection has none, and compares this table with the corpus:
`tested` is true only for a connector with recordings, `live_capture` only when one of them was
captured from a real account, and `not_replayed` names exactly the gaps that file exempts. So
the sentence on the screen cannot outlive the evidence behind it without a red build.

**Every recording today is a documented shape, and the sentence says so.** A connector tested
against the shapes a vendor publishes is tested against the vendor's statement of its API, not
against the vendor. Saying "tested against recorded responses" with no qualifier would read as
a live account having answered, which none has.

Rejected: listing the recordings, or counting them, on the screen. A count reads as a score and
invites a reader to compare connectors by it; what matters is whether every declared tool is
covered, which the build enforces and the sentence states.

Task ids: M0.6.5, M38.4.1.1, M38.4.1.2
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from brain.connectors.declaration import Recorded, shipped

#: Why the screen says a documented shape is not a live read.
A_DOCUMENTED_SHAPE_IS_NOT_A_LIVE_READ: Final = (
    "A recording written to the response shape a vendor's documentation publishes shows the "
    "connector reads that shape correctly. It does not show that a live account answers that "
    "way, so the screen names which kind of recording it was and never calls it a live read."
)

TESTED: Final = (
    "Tested against recorded responses on every build: every tool it declares, a page with more "
    "to read, and its error responses are replayed through its own code."
)
UNTESTED: Final = (
    "Not tested against recorded responses: no recording of this source exists in this release."
)
DOCUMENTED_ONLY: Final = (
    "The recordings are the response shapes the vendor's published documentation describes, "
    "not answers captured from a live account."
)
SOME_LIVE: Final = "Some of the recordings were captured from a live account."


def sentence(recorded: Recorded) -> str:
    """The whole statement about one connector's recordings, in the order a reader needs it."""
    if not recorded.tested:
        return UNTESTED
    parts = [TESTED, SOME_LIVE if recorded.live_capture else DOCUMENTED_ONLY]
    parts.extend(f"Not replayed: {gap}." for gap in recorded.not_replayed)
    if recorded.finding:
        parts.append(f"Found by replay: {recorded.finding}.")
    return " ".join(parts)


#: Every connector in this release, read off each one's declaration. Total over the shipped
#: connectors by construction; `tests/unit/test_cassette_replay.py` holds it to the corpus.
RECORDINGS: Final[Mapping[str, Recorded]] = MappingProxyType(
    {name: one.recorded for name, one in shipped().items()}
)


def recorded_in_words(name: str) -> str:
    """What this release was tested against for one connector, or that it was not."""
    found = RECORDINGS.get(name)
    return UNTESTED if found is None else sentence(found)
