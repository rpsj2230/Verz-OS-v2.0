"""What a recording is, what replaying one concludes, and what one source's cassette file declares.

Separate from `__init__.py` so a source's file can import these while the package is still being
discovered: the package imports every source file, and a source file importing the package it is
being imported by would find it half built.

Task ids: M38.4.1.1, M38.4.1.2
"""

from __future__ import annotations

import enum
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final

from brain.connectors.manifest import ConnectorManifest
from brain.connectors.projection import ProjectedRecord
from brain.connectors.throttle import CallOutcome
from brain.ops.idempotency import Verification


class Source(enum.StrEnum):
    """The names the first seven sources' recordings were filed under, for their tests' spelling.

    **Not the list of sources, and a new source needs no member here.** A recording's `source` is
    a plain string, the connector's module name, and the corpus is whatever cassette files
    `tests/fixtures/cassettes/` holds; `tests/invariants/test_cassettes.py` iterates the files,
    never this enum. It stays because a member equals its string, so `for_source(Source.XERO)`
    and a test comparing with one keep working.
    """

    XERO = "xero"
    LARK_BASE = "lark_base"
    FRESHDESK = "freshdesk"
    LARAVEL = "laravel"
    HUBSPOT = "hubspot"
    LARK_WIKI = "lark_wiki"
    GOOGLE_DRIVE = "google_drive"


class Origin(enum.StrEnum):
    """Where a recording's shape came from. Two, and the difference is what a console may say."""

    #: Written to the shape the vendor's published API reference documents. Not a live read.
    DOCUMENTED_SHAPE = "documented_shape"
    #: Captured from a real account's answer. Requires `captured_at`.
    LIVE_CAPTURE = "live_capture"


class Kind(enum.StrEnum):
    """What a recording is an example of, as the coverage sweep counts it."""

    LIST = "list"
    READ = "read"
    PAGINATION = "pagination"
    RATE_LIMIT = "rate_limit"
    ERROR = "error"


class Expect(enum.StrEnum):
    """What the connector's own code must conclude when this recording is replayed through it."""

    ANSWERED = "answered"
    ABSENT = "absent"
    #: Answered, and the source said there is more than this reply holds.
    MORE_TO_READ = "more_to_read"
    RATE_LIMITED = "rate_limited"
    REFUSED = "refused"
    UNREACHABLE = "unreachable"
    #: Drive's 404: absent, or present and not visible to this credential. The source does not say.
    NOT_FOUND = "not_found"


class Protocol(enum.StrEnum):
    """How the exchange travelled. Laravel is read through database views, not over HTTP."""

    HTTP = "http"
    #: `status` is 0, `request` is the statement's shape, and `body` holds `rows` or the
    #: server's documented `errno`, `sqlstate` and `message`.
    DATABASE = "database"


@dataclass(frozen=True)
class RateLimit:
    """Verified against the vendor's documentation, not guessed.

    These numbers are why the architecture federates instead of syncing: a realistic day
    touches 5-20 records per question, and syncing everything would need 15,000-60,000
    Xero calls against a ceiling of 5,000.
    """

    source: str
    calls: int
    per: str
    note: str
    raisable: bool


@dataclass(frozen=True, kw_only=True)
class Cassette:
    """One recorded exchange, what it is an example of, and where its shape came from."""

    cid: str
    #: The connector's module name, which is also its cassette file's name.
    source: str
    request: str
    status: int
    headers: dict[str, str] = field(default_factory=dict)
    body: Any = None
    why: str = ""
    kind: Kind
    #: The declared tool names this exchange answers. Lark Base names its tools after the table,
    #: so its recordings write the table as `{entity}`.
    tools: tuple[str, ...] = ()
    #: The projected entity a successful reply's rows are kept as, or empty.
    projects: str = ""
    expect: Expect
    origin: Origin
    #: The vendor documentation page the shape was written to, or what a capture was taken from.
    reference: str
    #: When a live capture was taken, as ISO 8601. Empty for a documented shape.
    captured_at: str = ""
    protocol: Protocol = Protocol.HTTP


DOCUMENTED: Final = Origin.DOCUMENTED_SHAPE

#: When every replay says a call was answered. Pinned: nothing replayed is about the present.
FETCHED_AT: Final = "2026-09-06T09:00:00+00:00"
#: When every replay says a kept record was last seen. Far from any wall clock, deliberately.
SEEN_AT: Final = datetime(2019, 6, 1, 12, 0, tzinfo=UTC)


@dataclass(frozen=True)
class Replayed:
    """What the connector's own code concluded, and the index entries it kept."""

    outcome: Expect
    kept: tuple[ProjectedRecord, ...] = ()

    @property
    def projected(self) -> int:
        return len(self.kept)


def unreachable_or_quota(call_outcome: CallOutcome) -> Expect:
    """What a failure the connector did not read as a refusal replays as."""
    return Expect.RATE_LIMITED if call_outcome is CallOutcome.QUOTA else Expect.UNREACHABLE


@dataclass(frozen=True)
class CassetteFile:
    """Everything one source's cassette file declares, found by `tests.fixtures.cassettes`.

    With the connector's own `CONNECTOR` declaration, this is the whole of adding a connector:
    the recordings, the vendor's documented ceiling, a replay that drives a recording through
    the connector's own code, and the manifest its tests build. Nothing else in the repository
    lists a connector.
    """

    source: str
    cassettes: tuple[Cassette, ...]
    rate_limit: RateLimit
    #: Drives one recording through the connector's own reader, interpreter or walk.
    replay: Callable[[Cassette], Replayed]
    #: The manifest this connector's tests connect with.
    manifest: Callable[[], ConnectorManifest]
    #: Kinds this source cannot have, and why.
    not_recordable: Mapping[Kind, str] = field(default_factory=dict)
    #: Projected entities whose positive path no documented shape can replay, and why.
    projection_not_replayable: Mapping[str, str] = field(default_factory=dict)
    #: Whether the connector names its tools after a table a deployment chooses.
    tools_named_after_the_table: bool = False
    #: How each recording the connector's read-back names is answered, by recording id, written
    #: beside the recordings rather than read from the connector, so the two are two accounts.
    read_back: Mapping[str, Verification] = field(default_factory=dict)
    #: Drives one of those recordings through the read-back reading, in the connector's own reply.
    read_back_answer: Callable[[Cassette], Verification] | None = None
    #: Where this vendor's own documentation states the wait on a refusal, when it is not
    #: `Retry-After`, or that it states none. Empty for a vendor that sends `Retry-After`. Declared
    #: rather than inferred: a recording that dropped the header to match a connector would
    #: otherwise pass as a vendor that never sends one (`tests/invariants/test_cassettes.py`).
    wait_not_in_retry_after: str = ""
