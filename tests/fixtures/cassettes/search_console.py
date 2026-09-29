"""Search Console's recordings: the site list, the four calls of a report, and failures.

The site list names a second site the account can see, and its address carries the canary: only
the connected site is kept. A report's figures are kept by nothing, so they need no marker; the
install check plants its own canary as a count and looks for it in every table.

Task ids: M11.7.2
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Final

from brain.connectors import search_console
from brain.connectors.manifest import ConnectorManifest
from brain.connectors.throttle import CallOutcome, classify
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
        cid="SC-200-top-query",
        source=SOURCE,
        request=f"{QUERY} dimensions=query",
        status=200,
        body={
            "rows": [
                {
                    "keys": ["example widgets"],
                    "clicks": 40,
                    "impressions": 900,
                    "ctr": 0.044,
                    "position": 3.1,
                }
            ],
            "responseAggregationType": "byProperty",
        },
        why="The top query over 28 days: Google orders rows by clicks, and one row is asked for.",
        kind=Kind.READ,
        tools=("search_console.read_performance",),
        expect=Expect.ANSWERED,
        origin=DOCUMENTED,
        reference=QUERY_DOC,
    ),
    Cassette(
        cid="SC-200-top-page",
        source=SOURCE,
        request=f"{QUERY} dimensions=page",
        status=200,
        body={
            "rows": [
                {
                    "keys": ["https://www.example.com/widgets/"],
                    "clicks": 35,
                    "impressions": 700,
                    "ctr": 0.05,
                    "position": 2.7,
                }
            ],
            "responseAggregationType": "byPage",
        },
        why="The top page over 28 days, aggregated by page as Google does for a page dimension.",
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

#: Where each kind of report call sits among the four `request_for` builds.
SLOTS: Final = {"dimensions=date": 0, "dimensions=query": 1, "dimensions=page": 2, "/sitemaps": 3}


def _slot(request: str) -> int:
    return next(index for marker, index in SLOTS.items() if marker in request)


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
    answers: list[Any] = [{}, {}, {}, {}]
    answers[_slot(recorded.request)] = recorded.body
    page = search_console.SearchConsoleReport().interpret(
        search_console.ENTITY_SITE,
        SITE,
        answers=tuple(answers),
        today=ASKED_ON,
        window=None,
        fetched_at=FETCHED_AT,
    )
    assert page.rows is not None
    (row,) = page.rows.records
    figures = row.model_dump(exclude={"entity", "id"})
    return Replayed(Expect.ANSWERED if figures else Expect.ABSENT)


def _failed(call: CallOutcome) -> Expect:
    return Expect.REFUSED if call is CallOutcome.REJECTED else unreachable_or_quota(call)


def manifest() -> ConnectorManifest:
    from tests.unit import test_search_console

    built: ConnectorManifest = test_search_console.a_manifest()
    return built


CASSETTE_FILE: Final = CassetteFile(
    source=SOURCE,
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
