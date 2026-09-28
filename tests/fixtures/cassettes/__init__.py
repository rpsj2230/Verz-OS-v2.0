"""Recorded connector responses, so connectors can be built before credentials exist.

This is what makes the thirty-day plan possible. Every connector is written and tested
against these, and wired to real credentials at go-live, otherwise the whole build waits
on someone finding a Xero API key.

A cassette is not a convenience mock. It records three things a hand-written mock always
gets wrong, and each has caused a real outage somewhere:

**The failure responses, not just the happy one.** Xero returns 429 with a Retry-After
header, and the correct behaviour is to say "I could not reach Xero" rather than answer
from memory. A mock that only knows success produces a connector that has never once been
compiled against failure.

**The real limits, verified rather than assumed.** Freshdesk search returns at most 300
records *ever*: not per page, not per request, but as a hard ceiling on the result set.
A connector written against a mock that pages forever will silently under-report and look
correct doing it.

**The pagination shape.** Every one of these APIs pages differently, and the difference is
where "we only ever saw the first 100 clients" comes from.

**Not one of these was captured from a live account, and each says so.** `Origin` is a
required field rather than a comment: every cassette here is `DOCUMENTED_SHAPE`, written to
the response shape the vendor's own API reference publishes and naming that page in
`reference`. The values inside (a client name, an id, a canary) are invented; the envelope,
the field names, the status and the headers are the documentation's. A `LIVE_CAPTURE` is a
claim that a real account answered this, and it must name when; nothing here makes that
claim, and `tests/unit/test_cassette_replay.py` refuses one that names no capture time.

**Every cassette says what it covers and what replaying it must produce.** `kind`, `tools`,
`projects` and `expect` are what the replay test and the coverage sweep read: a connector
that declares a tool no cassette answers, or a projection no cassette feeds, fails there
rather than being described as tested.

**One file per source, found rather than listed.** Until 2026-09-28 this was one module of
twelve hundred lines with a closed `Source` enum, and the replay that drives each recording
through its connector was a table in a test file. Now each source's recordings, its documented
ceiling, its replay and the manifest its tests build are one file here, named after the
connector's module and declaring `CASSETTE_FILE`, and `FILES` finds every one. With the
connector's own `CONNECTOR` declaration, that file is the whole of adding a connector:
`tests/invariants/test_cassettes.py` fails a connector whose file is missing, and nothing else
names it.

Task ids: M0.6.5, M38.4.1.1, M38.4.1.2
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from tests.fixtures.cassettes._types import (
    DOCUMENTED as DOCUMENTED,
)
from tests.fixtures.cassettes._types import (
    FETCHED_AT as FETCHED_AT,
)
from tests.fixtures.cassettes._types import (
    SEEN_AT as SEEN_AT,
)
from tests.fixtures.cassettes._types import (
    Cassette as Cassette,
)
from tests.fixtures.cassettes._types import (
    CassetteFile as CassetteFile,
)
from tests.fixtures.cassettes._types import (
    Expect as Expect,
)
from tests.fixtures.cassettes._types import (
    Kind as Kind,
)
from tests.fixtures.cassettes._types import (
    Origin as Origin,
)
from tests.fixtures.cassettes._types import (
    Protocol as Protocol,
)
from tests.fixtures.cassettes._types import (
    RateLimit as RateLimit,
)
from tests.fixtures.cassettes._types import (
    Replayed as Replayed,
)
from tests.fixtures.cassettes._types import (
    Source as Source,
)
from tests.fixtures.cassettes.google_drive import DRIVE_FOLDER as DRIVE_FOLDER
from tests.fixtures.cassettes.laravel import LARAVEL_RECORDED_CAP as LARAVEL_RECORDED_CAP
from tests.fixtures.cassettes.lark_wiki import WIKI_SPACE as WIKI_SPACE

#: The name each source's file declares its recordings under.
FILE_ATTRIBUTE: Final = "CASSETTE_FILE"


def _discover() -> Mapping[str, CassetteFile]:
    found: dict[str, CassetteFile] = {}
    for info in pkgutil.iter_modules(__path__):
        if info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{__name__}.{info.name}")
        declared = getattr(module, FILE_ATTRIBUTE, None)
        assert isinstance(declared, CassetteFile), (
            f"{module.__name__} declares no {FILE_ATTRIBUTE}, so its recordings are replayed by "
            "nothing"
        )
        assert declared.source == info.name, (
            f"{module.__name__} files its recordings under {declared.source!r}; a cassette file is "
            "named after the connector module it records"
        )
        wrong = [c.cid for c in declared.cassettes if c.source != info.name]
        assert not wrong, f"{module.__name__} holds recordings of another source: {wrong}"
        found[info.name] = declared
    return MappingProxyType(dict(sorted(found.items())))


#: Every source's cassette file, by the connector module it records.
FILES: Final[Mapping[str, CassetteFile]] = _discover()

#: Every recording, source by source in name order, each source's in its file's order.
CASSETTES: Final[tuple[Cassette, ...]] = tuple(
    one for file in FILES.values() for one in file.cassettes
)

#: Every source's documented ceiling.
RATE_LIMITS: Final[tuple[RateLimit, ...]] = tuple(file.rate_limit for file in FILES.values())


def for_source(source: str) -> tuple[Cassette, ...]:
    return tuple(c for c in CASSETTES if c.source == source)


def failures() -> tuple[Cassette, ...]:
    """Everything that is not a plain success, including the 200s that carry errors."""
    return tuple(
        c
        for c in CASSETTES
        if c.status >= 400
        or (isinstance(c.body, dict) and c.body.get("code", 0) not in (0, None))
        or (c.protocol is Protocol.DATABASE and isinstance(c.body, dict) and "errno" in c.body)
    )


def limit_for(source: str) -> RateLimit:
    return next(r for r in RATE_LIMITS if r.source == source)
