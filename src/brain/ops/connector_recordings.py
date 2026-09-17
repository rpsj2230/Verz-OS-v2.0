"""What each connector in this release was tested against, as the Connectors screen says it.

The question the owner asks of a connector before any company has a key for it is two
questions, and the screen answers them apart: **was it tested against recorded responses**,
which is a fact about this release and the same on every install, and **is there a live
credential for it**, which is a fact about one install's vault. Neither implies the other, and
the second never implies a live read: `brain.console.connector_trust.ConnectedRow` carries when
the worker last read a source to the end, and a source nobody has read is said to be unread.

**The record is written here and held true by a test, not computed at start.** The recordings
are `tests/fixtures/cassettes.py`, which is not shipped in the image, so nothing on a server can
count them. `tests/unit/test_cassette_replay.py` replays every recording through its connector,
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

Task ids: M0.6.5, M38.4.1.1
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

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


@dataclass(frozen=True)
class Recorded:
    """What one connector was tested against in this release."""

    tested: bool
    live_capture: bool = False
    #: Declared behaviour no recording can replay yet, each with the reason.
    not_replayed: tuple[str, ...] = ()
    #: What replaying the recordings found the connector does with them, when a reader who saw
    #: only "tested" would expect otherwise. Pinned by a test in the replay file.
    finding: str = ""

    def sentence(self) -> str:
        """The whole statement, in the order a reader needs it."""
        if not self.tested:
            return UNTESTED
        parts = [TESTED, SOME_LIVE if self.live_capture else DOCUMENTED_ONLY]
        parts.extend(f"Not replayed: {gap}." for gap in self.not_replayed)
        if self.finding:
            parts.append(f"Found by replay: {self.finding}.")
        return " ".join(parts)


#: Every connector in this release. Total over `brain.ops.connectable`'s two lists, which are
#: total over the connector package; `tests/unit/test_cassette_replay.py` holds both.
RECORDINGS: Final[Mapping[str, Recorded]] = MappingProxyType(
    {
        "freshdesk": Recorded(tested=True),
        "google_drive": Recorded(
            tested=True,
            not_replayed=(
                "a file is kept only with a sharing state, which is reduced from the permissions "
                "Drive returns; the connector has no function reading them out of a response, and "
                "Google's documentation does not say whether a user grant carries the domain that "
                "reduction needs, so only a live capture can settle it",
            ),
        ),
        "hubspot": Recorded(tested=True),
        "laravel": Recorded(tested=True),
        "lark_base": Recorded(tested=True),
        "lark_wiki": Recorded(
            tested=True,
            finding=(
                "the documented node listing carries no has_member_setting, so every page "
                "reads as having undetermined permissions and is withheld; until a live capture "
                "shows the key, or the connector reads permissions another way, it stores no page"
            ),
        ),
        "xero": Recorded(tested=True),
    }
)


def recorded_in_words(name: str) -> str:
    """What this release was tested against for one connector, or that it was not."""
    found = RECORDINGS.get(name)
    return UNTESTED if found is None else found.sentence()
