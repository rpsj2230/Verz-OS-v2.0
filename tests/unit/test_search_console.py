"""Search Console over its recordings: one site kept, its figures read live in four calls at once.

The recordings are `tests/fixtures/cassettes/search_console.py`, written to the shapes Google's
Search Console API reference documents, so the site list and the report's four answers come out of
the connector's own reading and report as a scheduled read and a question's live read take them.
The live read runs through `brain.ops.live_read_run.ConnectedSources` with a key file generated
here and a Google that records what it was sent, and nothing contacts Google.

Task ids: M11.7.2
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, Final

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from brain.connectors import search_console
from brain.connectors.contract import FetchRequest
from brain.connectors.date_range import DateWindow, RangeRequest
from brain.connectors.declaration import KeyScheme, SettingRefusedError
from brain.connectors.google_token import GOOGLE_TOKEN_URL, checked_scopes
from brain.connectors.live_read import LiveReply
from brain.connectors.manifest import ConnectorManifest, manifest_digest
from brain.connectors.search_console import (
    A_COUNT_IS_A_NUMBER,
    A_REPORT_READS_ONLY_THE_CONNECTED_SITE,
    A_SITE_LIST_CANNOT_PROVE_ABSENCE,
    CEILING_NAME,
    CONNECTOR_NAME,
    DEPARTMENT_SETTING,
    ENTITY_SITE,
    FIGURE_FIELDS,
    ONE_SITE_IS_KEPT_WHATEVER_THE_ACCOUNT_CAN_SEE,
    RANGE_FIGURE_FIELDS,
    RANGES,
    SCOPE,
    SEARCH_CONSOLE_API_URL,
    SITE_SETTING,
    THE_TOP_TEN_ARE_GOOGLE_S_ORDER_FOR_THE_RANGE_ASKED,
    TOP_ROWS,
    Reply,
    SearchConsoleConnection,
    SearchConsoleReading,
    SearchConsoleReport,
    SearchConsoleShapeError,
    figures_of,
    listing_for,
    range_figures_of,
    read_back_reading,
    site_id_of,
    site_name_of,
    site_of,
)
from brain.connectors.throttle import CallOutcome
from brain.connectors.write_verification import verdict
from brain.core.envelope import IdentityMode, SideEffect
from brain.core.scope import Scope
from brain.ops.connectable import key_reference, manifest_for
from brain.ops.connector_slots import SLOT_SCOPES
from brain.ops.connector_store import Connection
from brain.ops.connector_sync_run import SourceAnswer
from brain.ops.idempotency import Verification
from brain.ops.limits import connector_ceiling
from brain.ops.live_read_run import ConnectedSources
from tests.fixtures.cassettes import FETCHED_AT, SEEN_AT, for_source
from tests.fixtures.cassettes.search_console import ASKED_ON, SITE
from tests.unit.test_google_service_account import key_file

#: Far outside any plausible wall clock. See `CLAUDE.md` on a fixture with a date in it.
NOW: Final = datetime(2999, 1, 1, 9, 0, tzinfo=UTC)

SETTINGS: Final = {SITE_SETTING: SITE, DEPARTMENT_SETTING: "marketing"}

#: The instant the live read is asked at: the start of the day the recordings count back from.
ASKED_AT: Final = datetime.combine(ASKED_ON, datetime.min.time(), tzinfo=UTC)


def a_manifest() -> ConnectorManifest:
    """The manifest the recordings' site is connected with, as the console builds it."""
    return manifest_for(CONNECTOR_NAME, SETTINGS)


def recorded(cid: str) -> Any:
    return next(one for one in for_source(CONNECTOR_NAME) if one.cid == cid)


def answer_for(cid: str) -> SourceAnswer:
    one = recorded(cid)
    return SourceAnswer(
        status=one.status, headers=dict(one.headers), body=json.dumps(one.body).encode()
    )


def the_two(**changed: Any) -> tuple[Any, ...]:
    """A question's two recorded answers in the order `request_for` asks, any of them replaced."""
    answers = {
        "days": recorded("SC-200-days").body,
        "sitemaps": recorded("SC-200-sitemaps").body,
        **changed,
    }
    return (answers["days"], answers["sitemaps"])


def the_four(**changed: Any) -> tuple[Any, ...]:
    """A figure tool's four recorded answers in the order `request_for` asks, any replaced."""
    answers = {
        "totals": recorded("SC-200-totals").body,
        "queries": recorded("SC-200-top-queries").body,
        "pages": recorded("SC-200-top-pages").body,
        "sitemaps": recorded("SC-200-sitemaps").body,
        **changed,
    }
    return (answers["totals"], answers["queries"], answers["pages"], answers["sitemaps"])


#: The window the recorded figure-tool searches stand for.
WINDOW: Final = DateWindow(start=date(2019, 5, 1), end=date(2019, 5, 28))


@pytest.fixture(scope="module")
def key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


# ------------------------------------------------------------------------ the connection
@pytest.mark.parametrize(
    ("typed", "site", "name"),
    [
        ("sc-domain:example.com", "sc-domain:example.com", "example.com"),
        ("SC-Domain:Example.COM", "sc-domain:example.com", "example.com"),
        ("https://www.example.com/", "https://www.example.com/", "www.example.com"),
        ("HTTPS://WWW.Example.com/Blog/", "https://www.example.com/Blog/", "www.example.com/Blog"),
        ("  http://example.com:8080/ ", "http://example.com:8080/", "example.com:8080"),
    ],
)
def test_a_site_is_connected_as_search_console_names_it_and_asked_for_by_its_domain(
    typed: str, site: str, name: str
) -> None:
    """The positive case: a domain property or a URL-prefix property, typed in any case, connects
    one site pinned as Search Console names it, read by the named department, and a person asks
    for it by its domain or host.

    Delete this and a property pasted with a capital letter is a second site, or the name a
    question uses is one nobody would type."""
    built = manifest_for(CONNECTOR_NAME, {**SETTINGS, SITE_SETTING: typed})

    assert built.scope.selectors == (site,)
    (projection,) = built.projections
    assert projection.visibility == Scope.department("marketing")
    assert built.credential.ref == key_reference(CONNECTOR_NAME)
    assert site_name_of(site) == name


@pytest.mark.parametrize(
    ("setting", "typed"),
    [
        (SITE_SETTING, "example.com"),
        (SITE_SETTING, "https://example.com"),
        (SITE_SETTING, "ftp://example.com/"),
        (SITE_SETTING, "sc-domain:"),
        (SITE_SETTING, "sc-domain:example"),
        (SITE_SETTING, "https://exa mple.com/"),
        (SITE_SETTING, "https://example.com/a?b=c/"),
        (SITE_SETTING, "all"),
        (DEPARTMENT_SETTING, "Marketing Team"),
    ],
)
def test_a_setting_that_is_not_a_site_or_a_department_is_refused_by_name(
    setting: str, typed: str
) -> None:
    """Each refusal names its setting. A site that is not a property's own name is never laid into
    an address, so a query string or a space cannot choose another endpoint.

    Delete this and a mistyped site is connected and read as nothing, or a typed value reaches a
    path."""
    with pytest.raises(SettingRefusedError) as refused:
        SearchConsoleConnection.from_settings({**SETTINGS, setting: typed})
    assert refused.value.setting == setting
    assert site_of(typed) == "" or setting == DEPARTMENT_SETTING


def test_the_manifest_declares_read_only_service_reads_of_one_site_and_its_own_ceiling() -> None:
    """Both tools read, as the service, the site entity the steward is granted; the ceiling is the
    connector's own name with a verified row that cannot be bought higher; the slot asks for the
    scope the reading's token carries.

    Delete this and the connector could run against another source's measured ceiling, or declare
    a tool that writes."""
    built = a_manifest()

    assert {one.name for one in built.tools} == {
        "search_console.read_site",
        "search_console.read_performance",
    }
    assert all(one.side_effect is SideEffect.NONE for one in built.tools)
    assert all(one.identity_mode is IdentityMode.SERVICE for one in built.tools)
    assert CEILING_NAME == CONNECTOR_NAME == built.ceiling == "search_console"
    ceiling = connector_ceiling(CEILING_NAME)
    assert ceiling is not None and ceiling.per_minute == 200 and not ceiling.raisable
    assert SCOPE.endswith("/" + SLOT_SCOPES[CONNECTOR_NAME].request[0])


# ------------------------------------------------------------------------ the index
def test_only_the_connected_site_is_kept_from_the_account_s_list() -> None:
    """`ONE_SITE_IS_KEPT_WHATEVER_THE_ACCOUNT_CAN_SEE`: the recorded list names two sites, and
    what is kept is the connected one, named as a person asks for it, with its permission.

    Delete this and every property the service account was ever added to lands in the index."""
    reading = SearchConsoleReading()
    operation = reading.operation(ENTITY_SITE, settings=SETTINGS, resolver=_Unused())

    reply = reading.interpret(
        operation, status=200, body=recorded("SC-200-sites").body, fetched_at=FETCHED_AT
    )
    assert reply.rows is not None
    (row,) = reply.rows.records
    kept = reading.projected(ENTITY_SITE, row.model_dump(), seen_at=SEEN_AT)

    assert kept is not None
    assert (kept.source_id, kept.fields) == (
        site_id_of(SITE),
        {"site_name": "example.com", "permission_level": "siteRestrictedUser"},
    )
    assert operation.url_for({}) == f"{SEARCH_CONSOLE_API_URL}/sites"
    assert "dropped" in ONE_SITE_IS_KEPT_WHATEVER_THE_ACCOUNT_CAN_SEE


def test_a_list_without_the_site_keeps_nothing_and_an_empty_one_is_not_a_bad_reply() -> None:
    """Google leaves an empty list's key out, which is no sites rather than a reply in the wrong
    shape, and a list naming only other sites keeps nothing.

    Delete this and an account taken off its only site reads as a source that disagrees with its
    declaration, or another site is kept in the connected one's place."""
    operation = listing_for(SITE)
    others = {"siteEntry": [{"siteUrl": "sc-domain:example.org", "permissionLevel": "siteOwner"}]}

    for body in ({}, others):
        reply = SearchConsoleReading().interpret(
            operation, status=200, body=body, fetched_at=FETCHED_AT
        )
        assert reply.rows is not None and reply.rows.records == ()
    assert operation.project({}) == ()


def test_the_reading_is_a_google_service_account_s_with_a_read_only_scope() -> None:
    """The key file is exchanged for a token whose scope is Google's read-only Search Console
    scope, which the exchange's own rule admits.

    Delete this and the reading could ask for `webmasters`, which can change a property."""
    reading = SearchConsoleReading()
    assert reading.key_scheme() is KeyScheme.GOOGLE_SERVICE_ACCOUNT
    assert reading.token_scopes() == (SCOPE,) == checked_scopes(reading.token_scopes())
    assert SCOPE == "https://www.googleapis.com/auth/webmasters.readonly"


# ------------------------------------------------------------------------ the report
def test_a_question_s_report_is_two_calls_and_a_tool_s_four_for_the_connected_site_only() -> None:
    """`A_REPORT_READS_ONLY_THE_CONNECTED_SITE`, with its positive cases: a question's report is the
    last 90 days by day and the sitemaps; a figure tool's is the window's totals, its ten top
    queries and ten top pages, and the sitemaps, each at the site's own address; any other site is
    refused.

    Delete this and an index row naming another site the account can reach would be read, or a
    tool's window be read as the last 90 days."""
    today = date(2999, 1, 1)
    site = site_id_of(SITE)
    ask = SearchConsoleReport().request_for(
        ENTITY_SITE, site, settings=SETTINGS, today=today, window=None
    )
    ranged = SearchConsoleReport().request_for(
        ENTITY_SITE, site, settings=SETTINGS, today=today, window=WINDOW
    )

    base = f"{SEARCH_CONSOLE_API_URL}/sites/sc-domain%3Aexample.com"
    query, sitemaps = f"{base}/searchAnalytics/query", f"{base}/sitemaps"
    assert [one.url for one in ask] == [query, sitemaps]
    assert [one.url for one in ranged] == [query, query, query, sitemaps]
    assert ask[1].body is None and ranged[3].body is None
    days = json.loads(ask[0].body or b"")
    assert (days["dimensions"], days["rowLimit"]) == (["date"], 90)
    assert (days["startDate"], days["endDate"]) == ("2998-10-03", "2998-12-31")
    searched = [json.loads(one.body or b"") for one in ranged[:3]]
    assert [one.get("dimensions") for one in searched] == [None, ["query"], ["page"]]
    assert [one["rowLimit"] for one in searched] == [1, 10, 10]
    assert {(one["startDate"], one["endDate"]) for one in searched} == {
        ("2019-05-01", "2019-05-28")
    }
    with pytest.raises(SearchConsoleShapeError, match="connection was made with"):
        SearchConsoleReport().request_for(
            ENTITY_SITE,
            site_id_of("sc-domain:example.org"),
            settings=SETTINGS,
            today=today,
            window=None,
        )
    assert "connection" in A_REPORT_READS_ONLY_THE_CONNECTED_SITE


def test_the_recorded_answers_are_one_record_of_every_figure_counted_into_its_range() -> None:
    """A question's two recorded answers: clicks and impressions summed into each range by the day
    each row names, and the sitemaps' errors and warnings.

    Delete this and a day could be counted into the wrong range, or a count read as text."""
    (row,) = figures_of(the_two(), source_id=SITE, today=ASKED_ON, fetched_at=FETCHED_AT).records
    figures = row.model_dump(exclude={"entity", "id"})

    assert row.id == SITE
    assert set(figures) == set(FIGURE_FIELDS)
    assert (figures["clicks_last_7_days"], figures["impressions_last_7_days"]) == ("12", "300")
    assert (figures["clicks_last_28_days"], figures["impressions_last_28_days"]) == ("42", "1200")
    assert (figures["clicks_last_90_days"], figures["impressions_last_90_days"]) == ("142", "5200")
    assert (figures["sitemap_errors"], figures["sitemap_warnings"]) == ("1", "2")
    assert [one.days for one in RANGES] == [7, 28, 90]


def test_a_day_is_counted_from_the_first_day_of_its_range_to_yesterday_and_not_today() -> None:
    """The range's edges: the day seven days back is in the last 7 days, today is in none, and a day
    older than 90 is in none.

    Delete this and a range could count eight days, or today's unfinished figures."""

    def day(back: int) -> dict[str, Any]:
        stamp = (ASKED_ON - timedelta(days=back)).isoformat()
        return {"keys": [stamp], "clicks": 1, "impressions": 1}

    days = {"rows": [day(0), day(7), day(8), day(91)]}
    (row,) = figures_of(
        the_two(days=days), source_id=SITE, today=ASKED_ON, fetched_at=FETCHED_AT
    ).records
    figures = row.model_dump()
    assert (figures["clicks_last_7_days"], figures["clicks_last_90_days"]) == ("1", "2")


@pytest.mark.parametrize(
    "changed",
    [
        {"days": {"rows": [{"keys": ["2019-05-30"], "clicks": "many", "impressions": 1}]}},
        {"days": {"rows": [{"keys": ["2019-05-30"], "clicks": True, "impressions": 1}]}},
        {"days": {"rows": [{"keys": ["2019-05-30"], "clicks": -1, "impressions": 1}]}},
        {"days": {"rows": [{"keys": ["2019-05-30"], "clicks": 1.5, "impressions": 1}]}},
        {"days": {"rows": [{"keys": ["yesterday"], "clicks": 1, "impressions": 1}]}},
        {"days": {"rows": [{"keys": ["2019-02-30"], "clicks": 1, "impressions": 1}]}},
        {"sitemaps": {"sitemap": [{"errors": "one", "warnings": "0"}]}},
    ],
)
def test_a_report_this_does_not_read_is_refused_whole(changed: Mapping[str, Any]) -> None:
    """A count that is not a whole number (`A_COUNT_IS_A_NUMBER`), a day that is not a date, and a
    top row with no key are each a shape the declaration does not describe, and nothing of the
    report is answered. A whole number sent as a float, which the positive case below holds, is not.

    Delete this and a malformed count could be shown to a person as a figure."""
    with pytest.raises(SearchConsoleShapeError):
        figures_of(the_two(**changed), source_id=SITE, today=ASKED_ON, fetched_at=FETCHED_AT)
    whole = {"rows": [{"keys": ["2019-05-30"], "clicks": 3.0, "impressions": 4}]}
    (row,) = figures_of(
        the_two(days=whole), source_id=SITE, today=ASKED_ON, fetched_at=FETCHED_AT
    ).records
    assert row.model_dump()["clicks_last_7_days"] == "3"
    assert "whole" in A_COUNT_IS_A_NUMBER
    with pytest.raises(SearchConsoleShapeError):
        figures_of(the_two()[:1], source_id=SITE, today=ASKED_ON, fetched_at=FETCHED_AT)


def test_answers_with_no_rows_and_no_sitemaps_contribute_nothing_rather_than_noughts() -> None:
    """A site Google has no data for is answered with no figures, which the lane says is not known,
    rather than zeros nobody sent.

    Delete this and a site nobody has searched for yet would be reported as having had none."""
    (row,) = figures_of(({}, {}), source_id=SITE, today=ASKED_ON, fetched_at=FETCHED_AT).records
    assert row.model_dump(exclude={"entity", "id"}) == {}


def test_the_read_back_finds_the_site_and_never_reads_an_answer_as_its_absence() -> None:
    """`A_SITE_LIST_CANNOT_PROVE_ABSENCE`: the site found in the list, and a report's answer or a
    refusal inconclusive, never absent.

    Delete this and a read-back could report a site gone because a list did not name it."""

    def said(cid: str) -> Verification:
        one = recorded(cid)
        return verdict(
            read_back_reading(listing_for(SITE), Reply(status=one.status, body=one.body))
        )

    assert said("SC-200-sites") is Verification.FOUND
    assert said("SC-200-days") is Verification.INCONCLUSIVE
    assert said("SC-403-site") is Verification.INCONCLUSIVE
    assert "never absent" in A_SITE_LIST_CANNOT_PROVE_ABSENCE


# ------------------------------------------------------------------ the live read
@dataclass
class Leased:
    given: str = field(repr=False)
    closed: list[datetime] = field(default_factory=list)

    def key(self) -> str:
        return self.given

    def user(self) -> str:
        # A key file is one key; the database branch that asks for a user is tested in its own file.
        raise AssertionError("a Google source's lease was asked for a user")

    def close(self, now: datetime) -> Any:
        from brain.ops.connector_lease import LeaseOutcome

        self.closed.append(now)
        return LeaseOutcome.REVOKED


@dataclass
class KeyFiles:
    given: str = field(repr=False)
    leases: list[Leased] = field(default_factory=list)

    def lease(self, ref: Any, *, now: datetime) -> Leased:
        del ref, now
        self.leases.append(Leased(self.given))
        return self.leases[-1]


@dataclass
class Google:
    """Google's token endpoint and Search Console as recordings, a report's calls held at a
    barrier that opens only when all of them are in flight together."""

    sitemaps: str = "SC-200-sitemaps"
    together: int = 2
    asked: list[tuple[str, str, dict[str, str]]] = field(default_factory=list)
    searched: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.barrier = threading.Barrier(self.together, timeout=5)

    def _meet(self) -> None:
        self.barrier.wait()

    def post(
        self, url: str, *, address: str, headers: Mapping[str, str], body: bytes, max_bytes: int
    ) -> SourceAnswer:
        del address, max_bytes
        self.asked.append(("POST", url, dict(headers)))
        if url == GOOGLE_TOKEN_URL:
            return SourceAnswer(
                status=200,
                headers={},
                body=json.dumps({"access_token": "ya29.sc", "token_type": "Bearer"}).encode(),
            )
        self._meet()
        asked = json.loads(body)
        self.searched.append(asked)
        dimension = (asked.get("dimensions") or [None])[0]
        cid = {
            "date": "SC-200-days",
            None: "SC-200-totals",
            "query": "SC-200-top-queries",
            "page": "SC-200-top-pages",
        }
        return answer_for(cid[dimension])

    def get(
        self, url: str, *, address: str, headers: Mapping[str, str], max_bytes: int
    ) -> SourceAnswer:
        del address, max_bytes
        self.asked.append(("GET", url, dict(headers)))
        self._meet()
        return answer_for(self.sitemaps)


class _Resolver:
    def resolve(self, host: str) -> list[str]:
        del host
        return ["2000::1"]


class _Unused:
    def resolve(self, host: str) -> list[str]:
        raise AssertionError(f"resolved {host} while building an operation")


def connected(google: Google, keys: KeyFiles) -> ConnectedSources:
    settings = dict(SETTINGS)
    connection = Connection(
        connector=CONNECTOR_NAME,
        settings=settings,
        digest=manifest_digest(manifest_for(CONNECTOR_NAME, settings)),
        connected_by="u_admin",
        connected_at=NOW,
    )
    return ConnectedSources(
        {CONNECTOR_NAME: connection},
        keys=keys,
        caller=google,
        resolver=_Resolver(),
        clock=lambda: ASKED_AT,
        poster=google,
    )


def read(sources: ConnectedSources) -> LiveReply:
    source = sources.source_for(CONNECTOR_NAME, mode=IdentityMode.SERVICE, asker="p_reader")
    assert source is not None
    request = FetchRequest(entity=ENTITY_SITE, filters=(("id", site_id_of(SITE)),), limit=1)

    async def once() -> LiveReply:
        return await source(request)

    return asyncio.run(once())


def test_a_question_reads_the_site_s_figures_in_two_calls_made_at_once(
    key: rsa.RSAPrivateKey,
) -> None:
    """End to end over the recordings: one token for the read, then the two calls, which reach
    the barrier together (a report made one call at a time never opens it), each carrying the
    token and never the key file, and the figures come back as the site's record.

    Delete this and a report could cost the sum of its calls, which no question's budget holds,
    or send the key file itself."""
    google, keys = Google(), KeyFiles(key_file(key))

    reply = read(connected(google, keys))

    assert reply.outcome is CallOutcome.OK and reply.rows is not None
    (row,) = reply.rows.records
    assert (row.id, row.model_dump()["clicks_last_28_days"]) == (site_id_of(SITE), "42")
    token, *calls = google.asked
    assert token[1] == GOOGLE_TOKEN_URL
    assert sorted(method for method, _, _ in calls) == ["GET", "POST"]
    assert {headers["Authorization"] for _, _, headers in calls} == {"Bearer ya29.sc"}
    assert [lease.closed for lease in keys.leases] == [[ASKED_AT]]


def test_a_report_one_of_whose_calls_is_refused_is_the_refusal_with_no_figures(
    key: rsa.RSAPrivateKey,
) -> None:
    """`A_REPORT_S_CALLS_ARE_MADE_AT_ONCE_AND_ANSWER_TOGETHER`: the sitemaps refused and the search
    answered is the refusal, with none of the search's figures shown.

    Delete this and a report could be shown with its sitemaps' counts missing, which reads as a
    site with no indexing problems."""
    reply = read(connected(Google(sitemaps="SC-403-site"), KeyFiles(key_file(key))))
    assert (reply.outcome, reply.rows) == (CallOutcome.REJECTED, None)


def test_every_figure_a_report_answers_is_classified_for_the_redactor() -> None:
    """A figure read live is a field of the site's record by the time the redactor sees it, and a
    field nothing classifies is withheld from everybody, so every figure is classified.

    Delete this and a figure added to the report would be read and then shown to nobody."""
    from brain.knowledge.connector_rows import CONNECTOR_ROW_ENTITIES, NAMED_BY

    (classification,) = CONNECTOR_ROW_ENTITIES[CONNECTOR_NAME]
    assert classification.entity == ENTITY_SITE
    assert set(FIGURE_FIELDS) <= set(classification.columns())
    assert NAMED_BY[(CONNECTOR_NAME, ENTITY_SITE)] == "site_name"
    assert search_console.CONNECTOR.report is not None and search_console.CONNECTOR.live is None


def test_a_site_s_record_is_named_by_a_digest_the_redactor_admits_and_no_two_sites_share() -> None:
    """`A_SITE_IS_NAMED_BY_A_DIGEST_OF_ITS_ADDRESS`: a site's own name has a colon and slashes a
    record id may not carry, so the record is named by a digest in the redactor's own id grammar,
    one per site.

    Delete this and a connected site is dropped by the redactor as unidentified, which is how the
    first run of the install check read: every figure read and none shown."""
    import re

    from brain.core.redaction import _RECORD_ID_RE

    names = ("sc-domain:example.com", "https://www.example.com/", "https://www.example.com/blog/")
    ids = [site_id_of(one) for one in names]
    assert all(re.match(_RECORD_ID_RE, one) for one in ids)
    assert not any(re.match(_RECORD_ID_RE, one) for one in names)
    assert len(set(ids)) == len(names)


# ------------------------------------------------------------------ the figure tool
def test_a_window_s_ten_top_queries_and_pages_come_back_in_the_order_google_gave() -> None:
    """`THE_TOP_TEN_ARE_GOOGLE_S_ORDER_FOR_THE_RANGE_ASKED`: the recorded searches' ten rows each
    become ranked fields in the order they came, each with its clicks, beside the window's totals,
    its days and the sitemaps; a ranked row with no key refuses the report.

    Delete this and the queries could be re-ranked, cut short, or answered for another range."""
    (row,) = range_figures_of(
        the_four(), source_id=SITE, window=WINDOW, fetched_at=FETCHED_AT
    ).records
    figures = row.model_dump(exclude={"entity", "id"})

    assert TOP_ROWS == 10
    assert set(figures) == set(RANGE_FIGURE_FIELDS)
    assert [figures[f"top_query_{rank}"] for rank in range(1, 11)] == [
        f"example query {rank}" for rank in range(1, 11)
    ]
    assert [figures[f"top_page_{rank}"] for rank in range(1, 11)] == [
        f"https://www.example.com/page-{rank}/" for rank in range(1, 11)
    ]
    assert (figures["top_query_1_clicks"], figures["top_query_10_clicks"]) == ("370", "100")
    assert (figures["start_date"], figures["end_date"]) == ("2019-05-01", "2019-05-28")
    assert (figures["clicks"], figures["impressions"]) == ("1840", "52000")
    assert "Google gave" in THE_TOP_TEN_ARE_GOOGLE_S_ORDER_FOR_THE_RANGE_ASKED
    with pytest.raises(SearchConsoleShapeError):
        range_figures_of(
            the_four(queries={"rows": [{"keys": [""], "clicks": 1}]}),
            source_id=SITE,
            window=WINDOW,
            fetched_at=FETCHED_AT,
        )


@dataclass
class IndexedSite:
    """A row source holding the connected site's index row."""

    async def rows(self, query: Any) -> list[dict[str, Any]]:
        row = {
            "entity": ENTITY_SITE,
            "id": site_id_of(SITE),
            "site_name": "example.com",
            "department": "marketing",
        }
        return [{name: row.get(name) for name in ("entity", "id", *query.columns, *query.carried)}]


def the_tool(google: Google, keys: KeyFiles) -> Any:
    from brain.ops.live_records import SourceRecords
    from brain.tools.startup import build_registry

    sources = connected(google, keys)

    async def connected_now() -> Any:
        return sources

    figures = SourceRecords(connected=connected_now, clock=lambda: ASKED_AT)
    registry = build_registry(source="local", records=IndexedSite(), figures=figures)
    return registry.get("search_console.read_performance").handler


def a_reader() -> Any:
    from brain.core.entitlement import Capability, EntitlementSet, Grant

    reads = (f"read:{ENTITY_SITE}", f"read:{ENTITY_SITE}.site_name")
    return EntitlementSet(
        principal_id="p_reader",
        grants=tuple(
            Grant(capability=Capability(value=one), scope=Scope.department("marketing"))
            for one in reads
        ),
    )


@pytest.mark.parametrize(
    ("asked", "start", "end"),
    [
        ({"start": "2019-04-01", "end": "2019-04-30"}, "2019-04-01", "2019-04-30"),
        ({"period": "last month"}, "2019-05-01", "2019-05-31"),
        ({"period": "since 2019-03-10"}, "2019-03-10", "2019-06-01"),
    ],
)
def test_a_figure_tool_reads_the_site_for_the_range_it_is_asked_for_in_four_calls_at_once(
    key: rsa.RSAPrivateKey, asked: dict[str, str], start: str, end: str
) -> None:
    """The tool path, end to end: a first and last day, "last month" and "since a date" each reach
    all three searches as their days, the four calls meet at the barrier together, and the site's
    record comes back with its ten top queries for that range.

    Delete this and a workflow's range could be dropped on the way to Search Console, or the
    four calls made one after another."""
    google = Google(together=4)
    read = the_tool(google, KeyFiles(key_file(key)))

    result = asyncio.run(
        read(RangeRequest.model_validate(asked), entitlement=a_reader(), now=ASKED_AT)
    )

    assert {(one["startDate"], one["endDate"]) for one in google.searched} == {(start, end)}
    assert len(google.searched) == 3
    (row,) = result.records
    figures = row.model_dump()
    assert (figures["start_date"], figures["end_date"]) == (start, end)
    assert figures["top_query_1"] == "example query 1"
    assert figures["top_page_10"] == "https://www.example.com/page-10/"
