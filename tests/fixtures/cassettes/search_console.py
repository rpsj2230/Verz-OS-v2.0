"""Search Console's recordings: the site list, the four calls of a report, and failures.

The site list names a second site the account can see, and its address carries the canary: only
the connected site is kept. A report's figures are kept by nothing, so they need no marker; the
install check plants its own canary as a count and looks for it in every table.

Task ids: M11.7.2
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, timedelta
from types import MappingProxyType
from typing import Any, Final

from brain.connectors import search_console
from brain.connectors.date_range import DateWindow
from brain.connectors.manifest import ConnectorManifest
from brain.connectors.throttle import CallOutcome, classify
from brain.ops.idempotency import Verification
from tests.fixtures.cassettes._read_back import answered
from tests.fixtures.cassettes._types import (
    DOCUMENTED,
    FETCHED_AT,
    SEEN_AT,
    Cassette,
    CassetteFile,
    Expect,
    Kind,
    RateLimit,
    Replayed,
    unreachable_or_quota,
)

SOURCE: Final = "search_console"

SITES_DOC = "https://developers.google.com/webmaster-tools/v1/sites/list"
QUERY_DOC = "https://developers.google.com/webmaster-tools/v1/searchanalytics/query"
SITEMAPS_DOC = "https://developers.google.com/webmaster-tools/v1/sitemaps/list"
LIMITS_DOC = "https://developers.google.com/webmaster-tools/limits"
ERRORS_DOC = "https://cloud.google.com/apis/design/errors"

#: The made-up site every recording is of. The replay reads it as the connected one.
SITE: Final = "sc-domain:example.com"

#: The day the replay's report is asked on, far from any wall clock.
ASKED_ON: Final = SEEN_AT.date()

#: Where the report's three searches and the sitemaps are asked, for the recordings' requests.
QUERY: Final = "POST /webmasters/v3/sites/sc-domain%3Aexample.com/searchAnalytics/query"
SITEMAPS: Final = "GET /webmasters/v3/sites/sc-domain%3Aexample.com/sitemaps"


def _day(back: int, clicks: int, impressions: int) -> dict[str, Any]:
    """One row of the day-by-day search, `back` days before the day asked."""
    return {
        "keys": [(ASKED_ON - timedelta(days=back)).isoformat()],
        "clicks": clicks,
        "impressions": impressions,
        "ctr": clicks / impressions,
        "position": 8.4,
    }


def _ranked(key: str, clicks: int) -> dict[str, Any]:
    """One row of a search by query or by page."""
    return {"keys": [key], "clicks": clicks, "impressions": clicks * 20, "ctr": 0.05, "position": 4}


def _error(code: int, status: str, message: str) -> dict[str, object]:
    """Google's error envelope, as its API design guide documents it."""
    return {"error": {"code": code, "message": message, "status": status}}


CASSETTES: Final[tuple[Cassette, ...]] = (
    Cassette(
        cid="SC-200-sites",
        source=SOURCE,
        request="GET /webmasters/v3/sites",
        status=200,
        body={
            "siteEntry": [
                {"siteUrl": SITE, "permissionLevel": "siteRestrictedUser"},
                {"siteUrl": "CANARY-OTHER-SITE", "permissionLevel": "siteOwner"},
            ]
        },
        why="The account's site list names every property it was added to; only the connected one "
        "is kept, and the other's address never reaches the index.",
        kind=Kind.LIST,
        tools=("search_console.read_site",),
        projects=search_console.ENTITY_SITE,
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference=SITES_DOC,
    ),
    Cassette(
        cid="SC-200-days",
        source=SOURCE,
        request=f"{QUERY} dimensions=date",
        status=200,
        body={
            "rows": [_day(2, 12, 300), _day(10, 30, 900), _day(60, 100, 4000)],
            "responseAggregationType": "byProperty",
        },
        why="Clicks and impressions day by day over 90 days, which the three ranges are summed "
        "from. Days with no impressions are left out by Google rather than sent as nought.",
        kind=Kind.READ,
        tools=("search_console.read_performance",),
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference=QUERY_DOC,
    ),
    Cassette(
        cid="SC-200-totals",
        source=SOURCE,
        request=f"{QUERY} no dimension",
        status=200,
        body={
            "rows": [{"clicks": 1840, "impressions": 52000, "ctr": 0.035, "position": 9.1}],
            "responseAggregationType": "byProperty",
        },
        why="A search with no dimension is one row of the window's totals, with no keys.",
        kind=Kind.READ,
        tools=("search_console.read_performance",),
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference=QUERY_DOC,
    ),
    Cassette(
        cid="SC-200-top-queries",
        source=SOURCE,
        request=f"{QUERY} dimensions=query",
        status=200,
        body={
            "rows": [_ranked(f"example query {rank}", 400 - rank * 30) for rank in range(1, 11)],
            "responseAggregationType": "byProperty",
        },
        why="The ten most clicked queries in the window, most first, which is Google's own order "
        "for a search's rows.",
        kind=Kind.READ,
        tools=("search_console.read_performance",),
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference=QUERY_DOC,
    ),
    Cassette(
        cid="SC-200-top-pages",
        source=SOURCE,
        request=f"{QUERY} dimensions=page",
        status=200,
        body={
            "rows": [
                _ranked(f"https://www.example.com/page-{rank}/", 300 - rank * 20)
                for rank in range(1, 11)
            ],
            "responseAggregationType": "byPage",
        },
        why="The ten most clicked pages in the window, aggregated by page as Google does for a "
        "page dimension, most first.",
        kind=Kind.READ,
        tools=("search_console.read_performance",),
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference=QUERY_DOC,
    ),
    Cassette(
        cid="SC-200-sitemaps",
        source=SOURCE,
        request=SITEMAPS,
        status=200,
        body={
            "sitemap": [
                {
                    "path": "https://www.example.com/sitemap.xml",
                    "lastSubmitted": "2019-05-01T10:00:00.000Z",
                    "isPending": False,
                    "isSitemapsIndex": False,
                    "type": "sitemap",
                    "lastDownloaded": "2019-05-30T10:00:00.000Z",
                    "warnings": "2",
                    "errors": "1",
                    "contents": [{"type": "web", "submitted": "120", "indexed": "0"}],
                }
            ]
        },
        why="The site's sitemaps with their own error and warning counts, which is where the API "
        "reports indexing problems; the counts are whole numbers sent as strings.",
        kind=Kind.READ,
        tools=("search_console.read_performance",),
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference=SITEMAPS_DOC,
    ),
    Cassette(
        cid="SC-403-site",
        source=SOURCE,
        request=SITEMAPS,
        status=403,
        body=_error(
            403,
            "PERMISSION_DENIED",
            "User does not have sufficient permission for site 'sc-domain:example.com'.",
        ),
        why="The account was never added to the property, or was taken off it: a refusal, never "
        "a site with no problems.",
        kind=Kind.ERROR,
        tools=("search_console.read_performance",),
        expect=Expect.REFUSED,
        origin=DOCUMENTED,
        reference=ERRORS_DOC,
    ),
    Cassette(
        cid="SC-429-query",
        source=SOURCE,
        request=f"{QUERY} dimensions=query",
        status=429,
        body=_error(429, "RESOURCE_EXHAUSTED", "Search Analytics load quota exceeded."),
        why="The site's load quota is spent. Google states no wait, so the connector waits its "
        "own long end rather than anything the source said.",
        kind=Kind.RATE_LIMIT,
        tools=("search_console.read_performance",),
        expect=Expect.RATE_LIMITED,
        origin=DOCUMENTED,
        reference=LIMITS_DOC,
    ),
    Cassette(
        cid="SC-503-query",
        source=SOURCE,
        request=f"{QUERY} dimensions=date",
        status=503,
        body=_error(503, "UNAVAILABLE", "The service is currently unavailable."),
        why="Google's own outage: unreachable, and the answer says so rather than guessing.",
        kind=Kind.ERROR,
        tools=("search_console.read_performance",),
        expect=Expect.UNREACHABLE,
        origin=DOCUMENTED,
        reference=ERRORS_DOC,
    ),
)

RATE_LIMIT: Final = RateLimit(
    SOURCE,
    200,
    "minute",
    "Per user for the site list and sitemaps, 1,200 a minute per site for search analytics; "
    "`brain.ops.limits` records the same figure. Not raised by any plan.",
    False,
)

#: Where each kind of report call sits among the calls `request_for` builds: a question's two, and a
#: figure tool's four.
ASK_SLOTS: Final = {"dimensions=date": 0, "/sitemaps": 1}
RANGE_SLOTS: Final = {"no dimension": 0, "dimensions=query": 1, "dimensions=page": 2}

#: The window the recorded figure-tool searches were asked for.
ONE_RANGE: Final = DateWindow(start=date(2019, 5, 1), end=date(2019, 5, 28))


def replay(recorded: Cassette) -> Replayed:
    """A recording through the connector's own reading, or into its slot of a report."""
    if recorded.request == "GET /webmasters/v3/sites":
        reading = search_console.SearchConsoleReading()
        operation = search_console.listing_for(SITE)
        reply = reading.interpret(
            operation, status=recorded.status, body=recorded.body, fetched_at=FETCHED_AT
        )
        if reply.call is not CallOutcome.OK:
            return Replayed(_failed(reply.call))
        assert reply.rows is not None
        kept = tuple(
            one
            for one in (
                reading.projected(search_console.ENTITY_SITE, row.model_dump(), seen_at=SEEN_AT)
                for row in reply.rows.records
            )
            if one is not None
        )
        return Replayed(Expect.ANSWERED if kept else Expect.ABSENT, kept)
    call = classify(status=recorded.status)
    if call is not CallOutcome.OK:
        return Replayed(_failed(call))
    ranged = next(
        (slot for marker, slot in RANGE_SLOTS.items() if marker in recorded.request), None
    )
    answers: list[Any] = [{}] * (4 if ranged is not None else 2)
    if ranged is not None:
        answers[ranged] = recorded.body
    else:
        answers[next(slot for marker, slot in ASK_SLOTS.items() if marker in recorded.request)] = (
            recorded.body
        )
    page = search_console.SearchConsoleReport().interpret(
        search_console.ENTITY_SITE,
        search_console.site_id_of(SITE),
        answers=tuple(answers),
        today=ASKED_ON,
        window=ONE_RANGE if ranged is not None else None,
        fetched_at=FETCHED_AT,
    )
    assert page.rows is not None
    (row,) = page.rows.records
    figures = row.model_dump(exclude={"entity", "id", "start_date", "end_date"})
    return Replayed(Expect.ANSWERED if figures else Expect.ABSENT)


def _failed(call: CallOutcome) -> Expect:
    return Expect.REFUSED if call is CallOutcome.REJECTED else unreachable_or_quota(call)


def manifest() -> ConnectorManifest:
    from tests.unit import test_search_console

    built: ConnectorManifest = test_search_console.a_manifest()
    return built


def read_back_answer(recorded: Cassette) -> Verification:
    """One recording through Search Console's read-back reading, as the site list."""
    reply = search_console.Reply(
        status=recorded.status, headers=recorded.headers, body=recorded.body
    )
    return answered(SOURCE, search_console.listing_for(SITE), reply)


#: How each recording this connector's read-back names is answered. Written here rather than
#: read from the connector, so the expectation and the reading are two accounts that have to
#: agree (`tests/unit/test_write_verification.py`).
READ_BACK: Final[Mapping[str, Verification]] = MappingProxyType(
    {
        "SC-200-sites": Verification.FOUND,
        # A report's calls and every refusal hold no site list, and a list without the connected
        # site never proves it gone: see `search_console.A_SITE_LIST_CANNOT_PROVE_ABSENCE`.
        "SC-200-days": Verification.INCONCLUSIVE,
        "SC-200-totals": Verification.INCONCLUSIVE,
        "SC-200-top-queries": Verification.INCONCLUSIVE,
        "SC-200-top-pages": Verification.INCONCLUSIVE,
        "SC-200-sitemaps": Verification.INCONCLUSIVE,
        "SC-403-site": Verification.INCONCLUSIVE,
        "SC-429-query": Verification.INCONCLUSIVE,
        "SC-503-query": Verification.INCONCLUSIVE,
    }
)


CASSETTE_FILE: Final = CassetteFile(
    source=SOURCE,
    read_back=READ_BACK,
    read_back_answer=read_back_answer,
    wait_not_in_retry_after="none documented; Google asks for exponential backoff",
    cassettes=CASSETTES,
    rate_limit=RATE_LIMIT,
    replay=replay,
    manifest=manifest,
    not_recordable={
        Kind.PAGINATION: (
            "the site list is one page, and a report's four calls are bounded by the row limit "
            "each asks for, so nothing Search Console answers here pages"
        ),
    },
)
