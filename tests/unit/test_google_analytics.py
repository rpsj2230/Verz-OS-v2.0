"""Google Analytics over its recordings: one property kept, its figures read live, and nothing else.

The recordings are `tests/fixtures/cassettes/google_analytics.py`, written to the shapes Google's
Admin and Data API references document, so the property and the report come out of the connector's
own reading and report exactly as a scheduled read and a question's live read would take them. The
live read runs through `brain.ops.live_read_run.ConnectedSources` with a key file generated here, a
token endpoint and a Data API that record what they were sent, and nothing contacts Google.

Task ids: M11.7.1
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from brain.connectors import google_analytics
from brain.connectors.contract import ConnectorContractError, FetchRequest
from brain.connectors.declaration import KeyScheme, SettingRefusedError, shipped
from brain.connectors.google_analytics import (
    A_FIGURE_IS_A_NUMBER,
    A_PROPERTY_READ_CANNOT_PROVE_ABSENCE,
    A_REPORT_READS_ONLY_THE_CONNECTED_PROPERTY,
    CEILING_NAME,
    CONNECTOR_NAME,
    DATA_API_URL,
    DEPARTMENT_SETTING,
    ENTITY_PROPERTY,
    FIGURE_FIELDS,
    FIGURES,
    MAX_DATE_RANGES_PER_REPORT,
    PROPERTY_SETTING,
    RANGE_FIGURE_FIELDS,
    RANGES,
    REPORT_BODY,
    SCOPE,
    AnalyticsConnection,
    AnalyticsReading,
    AnalyticsReport,
    AnalyticsShapeError,
    Reply,
    figures_of,
    operation_for,
    property_id_of,
    read_back_reading,
    retry_after,
)
from brain.connectors.google_token import GOOGLE_TOKEN_URL, checked_scopes
from brain.connectors.live_read import LiveReply
from brain.connectors.manifest import ConnectorManifest, manifest_digest
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
from tests.fixtures.cassettes.google_analytics import PROPERTY
from tests.unit.test_google_service_account import key_file

#: Far outside any plausible wall clock. See `CLAUDE.md` on a fixture with a date in it.
NOW: Final = datetime(2999, 1, 1, 9, 0, tzinfo=UTC)

#: The department the recordings' property is connected for.
DEPARTMENT: Final = "marketing"

SETTINGS: Final = {PROPERTY_SETTING: PROPERTY, DEPARTMENT_SETTING: DEPARTMENT}


def a_manifest() -> ConnectorManifest:
    """The manifest the recordings' property is connected with, as the console builds it."""
    return manifest_for(CONNECTOR_NAME, SETTINGS)


def recorded(cid: str) -> Any:
    return next(one for one in for_source(CONNECTOR_NAME) if one.cid == cid)


def answer_for(cid: str) -> SourceAnswer:
    one = recorded(cid)
    return SourceAnswer(
        status=one.status, headers=dict(one.headers), body=json.dumps(one.body).encode()
    )


@pytest.fixture(scope="module")
def key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


# ------------------------------------------------------------------------ the connection
@pytest.mark.parametrize("typed", [PROPERTY, f"properties/{PROPERTY}", f"  {PROPERTY} "])
def test_a_property_is_connected_by_its_id_as_google_shows_it(typed: str) -> None:
    """The positive case: the digits, or the resource name the Admin API and the address bar use,
    each connect the same one property, pinned as the scope, read by the named department.

    Delete this and a property id pasted from the address bar is refused, or pinned as a different
    selector from the same id typed."""
    built = manifest_for(CONNECTOR_NAME, {**SETTINGS, PROPERTY_SETTING: typed})

    assert built.scope.selectors == (PROPERTY,)
    (projection,) = built.projections
    assert projection.visibility == Scope.department(DEPARTMENT)
    assert built.credential.ref == key_reference(CONNECTOR_NAME)


@pytest.mark.parametrize(
    ("setting", "typed"),
    [
        (PROPERTY_SETTING, "UA-12345-1"),
        (PROPERTY_SETTING, "properties/"),
        (PROPERTY_SETTING, "0123"),
        (PROPERTY_SETTING, "123/../456"),
        (PROPERTY_SETTING, "all"),
        (DEPARTMENT_SETTING, "Marketing Team"),
        (DEPARTMENT_SETTING, ""),
    ],
)
def test_a_setting_that_is_not_a_property_or_a_department_is_refused_by_name(
    setting: str, typed: str
) -> None:
    """Each refusal names its setting, so the screen marks the one that was wrong. A property id
    that is not digits is never laid into an address.

    Delete this and a slash in a typed id could choose another endpoint, or a department nobody
    can be granted could be connected and read by nobody."""
    with pytest.raises(SettingRefusedError) as refused:
        AnalyticsConnection.from_settings({**SETTINGS, setting: typed})
    assert refused.value.setting == setting
    assert property_id_of(f"properties/{PROPERTY}") == PROPERTY


def test_the_manifest_declares_read_only_service_reads_of_one_property_and_its_own_ceiling() -> (
    None
):
    """Both tools read, as the service, the property entity the steward is granted; the ceiling
    is this connector's own name and has a verified row; the key is a key file whose slot asks for
    the scope the reading's token carries.

    Delete this and the connector could run against another source's measured ceiling, as
    HubSpot's once could, or declare a tool that writes."""
    built = a_manifest()

    assert {one.name for one in built.tools} == {
        "google_analytics.read_property",
        "google_analytics.read_traffic",
    }
    assert all(one.side_effect is SideEffect.NONE for one in built.tools)
    assert all(one.identity_mode is IdentityMode.SERVICE for one in built.tools)
    assert {one.entity for one in built.tools} == {ENTITY_PROPERTY}
    assert CEILING_NAME == CONNECTOR_NAME == built.ceiling == "google_analytics"
    ceiling = connector_ceiling(CEILING_NAME)
    assert ceiling is not None and ceiling.per_minute > 0
    assert "analytics.readonly" in SLOT_SCOPES[CONNECTOR_NAME].request
    assert SCOPE.endswith("/" + SLOT_SCOPES[CONNECTOR_NAME].request[0])
    assert shipped()[CONNECTOR_NAME].console is not None


# ------------------------------------------------------------------------ the index
def test_the_worker_keeps_the_property_s_id_name_and_dates_and_nothing_else_it_sent() -> None:
    """The recorded property through the reading: the id is the digits, the name and the two dates
    are kept, and the industry, time zone and currency, sent in the same answer, are not.

    Delete this and the index could start carrying whatever the Admin API adds to a property."""
    reading = AnalyticsReading()
    operation = reading.operation(ENTITY_PROPERTY, settings=SETTINGS, resolver=_Unused())
    one = recorded("GA-200-property")

    reply = reading.interpret(operation, status=200, body=one.body, fetched_at=FETCHED_AT)
    assert reply.rows is not None
    (row,) = reply.rows.records
    kept = reading.projected(ENTITY_PROPERTY, row.model_dump(), seen_at=SEEN_AT)

    assert kept is not None
    assert kept.source_id == PROPERTY
    assert kept.fields == {
        "display_name": "Example Store",
        "create_time": "2019-03-01T10:00:00.000Z",
        "update_time": "2019-03-02T10:00:00.000Z",
    }
    assert operation.url_for({}) == f"{google_analytics.ADMIN_API_URL}/v1beta/properties/{PROPERTY}"
    assert reading.next_page(ENTITY_PROPERTY, {}, one.body, 1) is None


def test_an_answer_naming_no_property_keeps_nothing() -> None:
    """A row whose name is not `properties/<digits>` is not a property this can refresh or match,
    so nothing is kept for it, beside the positive case above.

    Delete this and a row with no usable id could be kept under an id nobody can read back."""
    reading = AnalyticsReading()
    assert reading.projected(ENTITY_PROPERTY, {"id": "accounts/1"}, seen_at=SEEN_AT) is None
    assert reading.projected(ENTITY_PROPERTY, {"display_name": "x"}, seen_at=SEEN_AT) is None
    kept = reading.projected(ENTITY_PROPERTY, {"id": f"properties/{PROPERTY}"}, seen_at=SEEN_AT)
    assert kept is not None and kept.source_id == PROPERTY


def test_the_reading_is_a_google_service_account_s_with_a_read_only_scope() -> None:
    """The key is a key file exchanged for a token, and the token's scope is Google's read-only
    Analytics scope, which the exchange's own rule admits.

    Delete this and the reading could ask for `analytics.edit`, or present the key file as it is."""
    reading = AnalyticsReading()
    assert reading.key_scheme() is KeyScheme.GOOGLE_SERVICE_ACCOUNT
    assert reading.token_scopes() == (SCOPE,) == checked_scopes(reading.token_scopes())
    assert SCOPE == "https://www.googleapis.com/auth/analytics.readonly"


def test_a_property_id_that_is_not_digits_is_never_laid_into_an_address() -> None:
    """`operation_for` refuses an id the connection would also refuse, as a second lock on the
    one value that is put into a path.

    Delete this and a reading handed settings that bypassed the connection could build an address
    out of anything."""
    with pytest.raises(AnalyticsShapeError):
        operation_for("1/../2")
    assert operation_for(PROPERTY).operation.path == f"/v1beta/properties/{PROPERTY}"


# ------------------------------------------------------------------------ the report
def test_the_date_ranges_are_four_and_one_report_carries_them_all() -> None:
    """`THE_DATE_RANGE_IS_ONE_OF_FOUR_AND_ALL_FOUR_ARE_ONE_REPORT`, against Google's documented
    ceiling of four ranges a report rather than against itself, and every range ends yesterday.

    Delete this and a fifth range could be added, which Google refuses, and every question would
    fail at the report."""
    assert MAX_DATE_RANGES_PER_REPORT == 4
    assert len(RANGES) <= MAX_DATE_RANGES_PER_REPORT
    assert [one["name"] for one in REPORT_BODY["dateRanges"]] == [one.name for one in RANGES]
    assert {one.end for one in RANGES} == {"yesterday"}
    assert [one["name"] for one in REPORT_BODY["metrics"]] == list(FIGURES)
    assert REPORT_BODY["keepEmptyRows"] is True
    assert len(FIGURE_FIELDS) == len(FIGURES) * len(RANGES)


def test_a_report_is_asked_of_the_data_api_for_the_connected_property_only() -> None:
    """`A_REPORT_READS_ONLY_THE_CONNECTED_PROPERTY`, with its positive case: the connected id is a
    POST to the Data API's `runReport` with the one body, and any other id is refused.

    Delete this and an index row naming another property the account can reach would be read."""
    report = AnalyticsReport()
    (call,) = report.request_for(
        ENTITY_PROPERTY, PROPERTY, settings=SETTINGS, today=NOW.date(), window=None
    )

    assert call.url == f"{DATA_API_URL}/v1beta/properties/{PROPERTY}:runReport"
    assert call.body is not None
    assert json.loads(call.body) == json.loads(json.dumps(dict(REPORT_BODY)))
    with pytest.raises(AnalyticsShapeError, match="connected"):
        report.request_for(
            ENTITY_PROPERTY, "987654321", settings=SETTINGS, today=NOW.date(), window=None
        )
    assert "connected" in A_REPORT_READS_ONLY_THE_CONNECTED_PROPERTY


def test_a_recorded_report_is_one_record_of_every_figure_for_every_range_named_as_asked() -> None:
    """The recorded report: one record carrying the property's id and twelve figures, conversions
    read from Google's `keyEvents`, each named `<figure>_<range>`.

    Delete this and the figures could be attached to the wrong range or the wrong word."""
    reply = AnalyticsReport().interpret(
        ENTITY_PROPERTY,
        PROPERTY,
        answers=(recorded("GA-200-report").body,),
        today=NOW.date(),
        window=None,
        fetched_at=FETCHED_AT,
    )

    assert reply.call is CallOutcome.OK and reply.rows is not None
    (row,) = reply.rows.records
    figures = row.model_dump(exclude={"entity", "id"})
    assert row.id == PROPERTY
    assert set(figures) == set(FIGURE_FIELDS)
    assert figures["sessions_last_28_days"] == "1204"
    assert figures["users_yesterday"] == "37"
    assert figures["conversions_last_90_days"] == "117"


def test_figures_are_read_by_the_names_the_report_states_and_not_by_position() -> None:
    """A report whose metrics come back in another order is read by the headers, so a figure is
    never answered under another figure's name.

    Delete this and a reply that reorders its metrics would report users as sessions."""
    body = {
        "dimensionHeaders": [{"name": "dateRange"}],
        "metricHeaders": [{"name": "keyEvents"}, {"name": "sessions"}, {"name": "totalUsers"}],
        "rows": [
            {
                "dimensionValues": [{"value": "yesterday"}],
                "metricValues": [{"value": "2"}, {"value": "41"}, {"value": "37"}],
            }
        ],
    }
    (row,) = figures_of(body, source_id=PROPERTY, fetched_at=FETCHED_AT).records
    assert row.model_dump(exclude={"entity", "id"}) == {
        "conversions_yesterday": "2",
        "sessions_yesterday": "41",
        "users_yesterday": "37",
    }


@pytest.mark.parametrize(
    "changed",
    [
        {"metricHeaders": [{"name": "sessions"}, {"name": "totalUsers"}, {"name": "revenue"}]},
        {"dimensionHeaders": [{"name": "country"}]},
        {
            "rows": [
                {
                    "dimensionValues": [{"value": "last_year"}],
                    "metricValues": [{"value": "1"}, {"value": "1"}, {"value": "1"}],
                }
            ]
        },
        {
            "rows": [
                {
                    "dimensionValues": [{"value": "yesterday"}],
                    "metricValues": [{"value": "1"}, {"value": "1"}],
                }
            ]
        },
        {
            "rows": [
                {
                    "dimensionValues": [{"value": "yesterday"}],
                    "metricValues": [{"value": "1"}, {"value": "a lot"}, {"value": "1"}],
                }
            ]
        },
        {"rows": [{"dimensionValues": []}]},
    ],
)
def test_a_report_this_does_not_read_is_refused_whole_and_never_partly_shown(
    changed: Mapping[str, Any],
) -> None:
    """A metric or a range nobody asked for, a row short of a figure, a figure that is not a number
    (`A_FIGURE_IS_A_NUMBER`) and a row missing its range are each a shape the declaration does not
    describe, and nothing of the reply is answered.

    Delete this and a reply naming revenue, or a value that is not a figure, could reach a person
    under a figure's name."""
    body = {**recorded("GA-200-report").body, **changed}
    with pytest.raises(AnalyticsShapeError):
        figures_of(body, source_id=PROPERTY, fetched_at=FETCHED_AT)
    assert "decimal" in A_FIGURE_IS_A_NUMBER


def test_a_range_the_report_leaves_out_contributes_nothing_rather_than_a_nought() -> None:
    """A report with no rows answers the property with no figures, which the lane says is not
    known, rather than zeros nobody sent.

    Delete this and a quiet property would be reported as having had no visitors."""
    body = {**recorded("GA-200-report").body, "rows": []}
    (row,) = figures_of(body, source_id=PROPERTY, fetched_at=FETCHED_AT).records
    assert row.id == PROPERTY
    assert row.model_dump(exclude={"entity", "id"}) == {}


@pytest.mark.parametrize(
    ("cid", "call"),
    [
        ("GA-429-report", CallOutcome.QUOTA),
        ("GA-401", CallOutcome.REJECTED),
        ("GA-500-report", CallOutcome.UNAVAILABLE),
    ],
)
def test_a_refused_or_failed_report_carries_no_rows(
    key: rsa.RSAPrivateKey, cid: str, call: CallOutcome
) -> None:
    """Absent, refused and unreachable stay three answers: a recorded failure read live is its
    outcome and no rows, and a report answered as more than one call is not read at all.

    Delete this and a quota refusal could be answered as a property with no traffic."""
    reply = read(connected(Google(report=cid), KeyFiles(key_file(key))))
    assert (reply.outcome, reply.rows) == (call, None)
    with pytest.raises(AnalyticsShapeError):
        AnalyticsReport().interpret(
            ENTITY_PROPERTY,
            PROPERTY,
            answers=({}, {}),
            today=NOW.date(),
            window=None,
            fetched_at=FETCHED_AT,
        )


def test_a_wait_google_states_is_read_in_any_case_and_a_missing_or_bad_one_is_none() -> None:
    """Google documents no wait for these APIs, so None is the ordinary answer; a stated one is
    honoured whatever case its header name arrives in.

    Delete this and a lower-cased header from the worker's caller would be ignored."""
    assert retry_after({"retry-after": "30"}) == 30.0
    assert retry_after({"Retry-After": "2.5"}) == 2.5
    assert retry_after({}) is None
    assert retry_after({"retry-after": "soon"}) is None
    assert retry_after({"retry-after": "-1"}) is None


def test_the_read_back_finds_the_property_and_never_reads_an_answer_as_its_absence() -> None:
    """`A_PROPERTY_READ_CANNOT_PROVE_ABSENCE`: the property found, a report or token answer that
    holds no property unreadable, and a refusal inconclusive, never absent.

    Delete this and a read-back could report a property gone because an answer held nothing."""
    operation = operation_for(PROPERTY)

    def said(cid: str) -> Verification:
        one = recorded(cid)
        return verdict(read_back_reading(operation, Reply(status=one.status, body=one.body)))

    assert said("GA-200-property") is Verification.FOUND
    assert said("GA-200-report") is Verification.INCONCLUSIVE
    assert said("GA-403-property") is Verification.INCONCLUSIVE
    assert "never absent" in A_PROPERTY_READ_CANNOT_PROVE_ABSENCE


# ------------------------------------------------------------------ the live read
@dataclass
class Leased:
    given: str = field(repr=False)
    closed: list[datetime] = field(default_factory=list)

    def key(self) -> str:
        return self.given

    def close(self, now: datetime) -> Any:
        from brain.ops.connector_lease import LeaseOutcome

        self.closed.append(now)
        return LeaseOutcome.REVOKED


@dataclass
class KeyFiles:
    """`ConnectorKeys` leasing one key file, and noting each lease."""

    given: str = field(repr=False)
    leases: list[Leased] = field(default_factory=list)

    def lease(self, ref: Any, *, now: datetime) -> Leased:
        del ref, now
        self.leases.append(Leased(self.given))
        return self.leases[-1]


@dataclass
class Google:
    """Google's token endpoint and Data API as recordings, noting every post it is sent."""

    report: str = "GA-200-report"
    posts: list[tuple[str, dict[str, str], bytes]] = field(default_factory=list)

    def post(
        self, url: str, *, address: str, headers: Mapping[str, str], body: bytes, max_bytes: int
    ) -> SourceAnswer:
        del address, max_bytes
        self.posts.append((url, dict(headers), body))
        if url == GOOGLE_TOKEN_URL:
            return answer_for("GA-200-token")
        return answer_for(self.report)

    def get(
        self, url: str, *, address: str, headers: Mapping[str, str], max_bytes: int
    ) -> SourceAnswer:
        raise AssertionError(f"a figure was read with a GET to {url}")


class _Resolver:
    def resolve(self, host: str) -> list[str]:
        del host
        return ["2000::1"]


class _Unused:
    def resolve(self, host: str) -> list[str]:
        raise AssertionError(f"resolved {host} while building an operation")


def connected(google: Google, keys: KeyFiles, *, poster: bool = True) -> ConnectedSources:
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
        clock=lambda: NOW,
        poster=google if poster else None,
    )


def read(sources: ConnectedSources, record_id: str = PROPERTY) -> LiveReply:
    source = sources.source_for(CONNECTOR_NAME, mode=IdentityMode.SERVICE, asker="p_reader")
    assert source is not None
    request = FetchRequest(entity=ENTITY_PROPERTY, filters=(("id", record_id),), limit=1)

    async def once() -> LiveReply:
        return await source(request)

    return asyncio.run(once())


def test_a_question_reads_the_figures_live_with_a_token_the_key_file_bought_for_that_read(
    key: rsa.RSAPrivateKey,
) -> None:
    """End to end over the recordings: the key file is borrowed for the read, exchanged at Google's
    token endpoint, and the token (never the file) goes in the one header of the one report, whose
    figures come back as the property's record; the lease is given back when the read ends.

    Delete this and a question could read the figures with the key file as a bearer, keep the key
    past the read, or answer from something other than the report."""
    google, keys = Google(), KeyFiles(key_file(key))
    sources = connected(google, keys)

    reply = read(sources)

    assert sources.reads(CONNECTOR_NAME, ENTITY_PROPERTY) is IdentityMode.SERVICE
    assert reply.outcome is CallOutcome.OK and reply.rows is not None
    (row,) = reply.rows.records
    assert (row.id, row.model_dump()["sessions_last_28_days"]) == (PROPERTY, "1204")
    (token, report) = google.posts
    assert token[0] == GOOGLE_TOKEN_URL
    assert report[0] == f"{DATA_API_URL}/v1beta/properties/{PROPERTY}:runReport"
    assert report[1]["Authorization"] == "Bearer ya29.recorded-shape"
    assert "PRIVATE KEY" not in json.dumps(report[1])
    assert json.loads(report[2]) == json.loads(json.dumps(dict(REPORT_BODY)))
    assert [lease.closed for lease in keys.leases] == [[NOW]]


def test_a_process_given_no_poster_reads_no_report_and_sends_nothing(
    key: rsa.RSAPrivateKey,
) -> None:
    """The report and the token are both posts, so a process wired without a poster refuses the
    read rather than making it some other way, and still gives the key back.

    Delete this and a process with no poster could fall back to a GET with the key file."""
    google, keys = Google(), KeyFiles(key_file(key))

    reply = read(connected(google, keys, poster=False))

    assert (reply.outcome, reply.rows) == (CallOutcome.REJECTED, None)
    assert google.posts == []
    assert [lease.closed for lease in keys.leases] == [[NOW]]


def test_a_report_google_refuses_is_the_refusal_and_another_property_is_never_asked(
    key: rsa.RSAPrivateKey,
) -> None:
    """A recorded refusal comes back as the refusal with no rows, and a record naming a property
    other than the connected one is refused before any report is posted.

    Delete this and a refused report could read as a property with no traffic, or an index row
    could steer a read to another property."""
    google, keys = Google(report="GA-401"), KeyFiles(key_file(key))
    refused = read(connected(google, keys))
    assert (refused.outcome, refused.rows) == (CallOutcome.REJECTED, None)

    other = Google()
    elsewhere = read(connected(other, KeyFiles(key_file(key))), record_id="987654321")
    assert elsewhere.outcome is CallOutcome.REJECTED
    assert [url for url, _, _ in other.posts] == [GOOGLE_TOKEN_URL]


def test_a_declaration_with_a_report_and_a_live_lookup_for_one_entity_is_refused() -> None:
    """One entity is read live one way. A declaration naming the property as both a record and a
    report is refused at start-up, which is the rule's other half; the shipped declaration, which
    names only the report, is the positive case.

    Delete this and a question could read the property two ways and answer from whichever
    returned first."""
    from dataclasses import replace

    from brain.connectors.declaration import DeclarationError

    shipped_one = google_analytics.CONNECTOR

    class Both:
        def entities(self) -> tuple[str, ...]:
            return (ENTITY_PROPERTY,)

        def identity_mode(self, entity: str) -> IdentityMode:
            return IdentityMode.SERVICE

        def arguments_for(self, entity: str, source_id: str) -> Mapping[str, str]:
            return {}

        def operation(self, entity: str, *, settings: Mapping[str, str], resolver: Any) -> None:
            return None

    with pytest.raises(DeclarationError, match="both as a record and as a report"):
        replace(shipped_one, live=Both())
    with pytest.raises(DeclarationError, match="report and no reading"):
        replace(shipped_one, reading=None, live=None)
    assert shipped_one.report is not None and shipped_one.live is None


def test_every_figure_a_report_answers_is_classified_for_the_redactor() -> None:
    """A figure read live is a field of the property's record by the time the redactor sees it, and
    a field nothing classifies is withheld from everybody, so every figure is classified.

    Delete this and a figure added to the report would be read and then shown to nobody."""
    from brain.knowledge.connector_rows import CONNECTOR_ROW_ENTITIES, NAMED_BY

    (classification,) = CONNECTOR_ROW_ENTITIES[CONNECTOR_NAME]
    assert classification.entity == ENTITY_PROPERTY
    assert set(FIGURE_FIELDS) <= set(classification.columns())
    assert NAMED_BY[(CONNECTOR_NAME, ENTITY_PROPERTY)] == "display_name"


def test_the_recordings_name_nothing_that_is_not_a_documented_shape() -> None:
    """Every recording names a reference, and the token recordings are Google's documented answer
    to a JWT bearer grant.

    Delete this and the recordings could be edited to fit the code rather than the vendor."""
    for one in for_source(CONNECTOR_NAME):
        assert one.reference.startswith("https://")
    assert recorded("GA-200-token").body["token_type"] == "Bearer"
    with pytest.raises(ConnectorContractError):
        AnalyticsReading().projected("site", {}, seen_at=SEEN_AT)


# ------------------------------------------------------------------ the figure tool
@dataclass
class IndexedProperty:
    """A row source holding the connected property's index row, noting whether it was asked."""

    asked: list[Any] = field(default_factory=list)

    async def rows(self, query: Any) -> list[dict[str, Any]]:
        self.asked.append(query)
        row = {
            "entity": ENTITY_PROPERTY,
            "id": PROPERTY,
            "display_name": "Example Store",
            "department": "marketing",
        }
        return [{name: row.get(name) for name in ("entity", "id", *query.columns, *query.carried)}]


def a_reader(*reads: str, department: str = "marketing") -> Any:
    from brain.core.entitlement import Capability, EntitlementSet, Grant

    return EntitlementSet(
        principal_id="p_reader",
        grants=tuple(
            Grant(capability=Capability(value=one), scope=Scope.department(department))
            for one in reads
        ),
    )


GRANTED: Final = (
    f"read:{ENTITY_PROPERTY}",
    f"read:{ENTITY_PROPERTY}.display_name",
    *(f"read:{ENTITY_PROPERTY}.{name}" for name in RANGE_FIGURE_FIELDS),
)


def the_tool(google: Google, keys: KeyFiles, rows: IndexedProperty) -> Any:
    from brain.ops.live_records import SourceRecords
    from brain.tools.startup import build_registry

    sources = connected(google, keys)

    async def connected_now() -> Any:
        return sources

    figures = SourceRecords(connected=connected_now, clock=lambda: NOW)
    registry = build_registry(source="local", records=rows, figures=figures)
    return registry.get("google_analytics.read_traffic").handler


def asked_range(google: Google) -> list[dict[str, str]]:
    """The date ranges of the first report Google was asked for."""
    body = next(body for url, _, body in google.posts if url.endswith(":runReport"))
    ranges: list[dict[str, str]] = json.loads(body)["dateRanges"]
    return ranges


@pytest.mark.parametrize(
    ("asked", "start", "end"),
    [
        ({"start": "2998-11-01", "end": "2998-11-30"}, "2998-11-01", "2998-11-30"),
        ({"period": "last month"}, "2998-12-01", "2998-12-31"),
        ({"period": "since 2998-10-05"}, "2998-10-05", "2999-01-01"),
    ],
)
def test_a_figure_tool_reads_the_range_it_is_asked_for_live_from_google(
    key: rsa.RSAPrivateKey, asked: dict[str, str], start: str, end: str
) -> None:
    """The tool path, end to end: a first and last day, "last month" and "since a date" each reach
    the report as its one date range, and the figures come back laid over the property the reader
    reaches, with the range's days beside them.

    Delete this and a workflow's range could be dropped on the way to Google and answered for the
    last 28 days instead, with nothing saying so."""
    from brain.connectors.date_range import RangeRequest

    google, rows = Google(report="GA-200-range-report"), IndexedProperty()
    read = the_tool(google, KeyFiles(key_file(key)), rows)

    request = RangeRequest.model_validate(asked)
    result = asyncio.run(read(request, entitlement=a_reader(*GRANTED), now=NOW))

    assert asked_range(google) == [{"startDate": start, "endDate": end}]
    (row,) = result.records
    figures = row.model_dump()
    assert (row.id, figures["display_name"]) == (PROPERTY, "Example Store")
    assert (figures["start_date"], figures["end_date"]) == (start, end)
    assert (figures["sessions"], figures["users"], figures["conversions"]) == (
        "5120",
        "4033",
        "161",
    )


def test_a_range_past_sixteen_months_is_refused_before_anything_is_read(
    key: rsa.RSAPrivateKey,
) -> None:
    """The cap on the tool path: a range starting a day before the earliest is refused in the
    range module's sentence, before the index is read or Google is asked, and the earliest start
    itself is read.

    Delete this and a range Google does not hold could be asked for and answered with noughts."""
    from brain.connectors.date_range import (
        A_RANGE_STARTS_WITHIN_SIXTEEN_MONTHS,
        RangeRefusedError,
        RangeRequest,
        earliest_start,
    )

    edge = earliest_start(NOW.date())
    google, rows = Google(report="GA-200-range-report"), IndexedProperty()
    read = the_tool(google, KeyFiles(key_file(key)), rows)
    too_far = RangeRequest(start=edge - timedelta(days=1), end=edge)

    with pytest.raises(RangeRefusedError) as refused:
        asyncio.run(read(too_far, entitlement=a_reader(*GRANTED), now=NOW))
    assert refused.value.public_message == A_RANGE_STARTS_WITHIN_SIXTEEN_MONTHS
    assert (rows.asked, google.posts) == ([], [])

    asyncio.run(read(RangeRequest(start=edge, end=edge), entitlement=a_reader(*GRANTED), now=NOW))
    assert asked_range(google) == [{"startDate": edge.isoformat(), "endDate": edge.isoformat()}]


def test_a_reader_without_the_property_is_handed_what_a_reader_of_nothing_is_handed(
    key: rsa.RSAPrivateKey,
) -> None:
    """`connector_figures.A_FIGURE_TOOL_READS_ONLY_WHAT_ITS_CALLER_REACHES`: a reader holding every
    figure's grant but not the property's own read, and one holding nothing, find no row, ask
    Google nothing, and get the same empty result, which is what an agent whose ceiling does not
    bind the property gets. The granted reader above is the positive case; a reader granted the
    property in another department is the install check's, where the row plane runs its SQL.

    Delete this and a caller without the property could read its traffic through the tool."""
    from brain.connectors.date_range import RangeRequest

    asked = RangeRequest(period="last month")
    answers = []
    for reader in (a_reader(*GRANTED[1:]), a_reader()):
        google = Google(report="GA-200-range-report")
        read = the_tool(google, KeyFiles(key_file(key)), IndexedProperty())
        result = asyncio.run(read(asked, entitlement=reader, now=NOW))
        answers.append(result.records)
        assert google.posts == []
    assert answers == [(), ()]


def test_the_figure_tool_is_registered_beside_the_row_tool_and_is_not_a_row_reader(
    key: rsa.RSAPrivateKey,
) -> None:
    """The figure tool shares its row tool's source and entity, requires the property's own read,
    and is told apart from the row tool by name, so the fast lane and the records route keep
    calling the row tool with a row request.

    Delete this and the fast lane could call the figure tool with a row request, or the records
    route read two tools for one entity as a misconfigured install."""
    from brain.api_routes import row_readers
    from brain.knowledge.rows import is_row_tool
    from brain.ops.live_records import SourceRecords
    from brain.tools.startup import build_registry

    async def nothing() -> Any:
        return connected(Google(), KeyFiles(key_file(key)))

    registry = build_registry(
        source="local", records=IndexedProperty(), figures=SourceRecords(connected=nothing)
    )
    figure = registry.get("google_analytics.read_traffic").definition
    row = registry.get(f"google_analytics.read_{ENTITY_PROPERTY}").definition

    assert (figure.source, figure.entity) == (row.source, row.entity)
    assert figure.required_capability == f"read:{ENTITY_PROPERTY}"
    assert (is_row_tool(figure), is_row_tool(row)) == (False, True)
    assert row_readers(registry)[(CONNECTOR_NAME, ENTITY_PROPERTY)] is (
        registry.get(row.name).handler
    )
    assert not build_registry(source="local", records=IndexedProperty()).has(figure.name)


def test_a_one_range_report_is_one_record_of_the_range_s_days_and_figures() -> None:
    """The recorded one-range report through the connector: the range's days and each figure by
    the name its header states, and a report of more than one row refused.

    Delete this and a one-range report could be read as the four-range one and answer nothing."""
    from datetime import date

    from brain.connectors.date_range import DateWindow
    from brain.connectors.google_analytics import AnalyticsShapeError, range_figures_of

    one = DateWindow(start=date(2998, 1, 1), end=date(2998, 1, 31))
    body = recorded("GA-200-range-report").body
    (row,) = range_figures_of(body, source_id=PROPERTY, window=one, fetched_at=FETCHED_AT).records
    assert row.model_dump(exclude={"entity", "id"}) == {
        "start_date": "2998-01-01",
        "end_date": "2998-01-31",
        "sessions": "5120",
        "users": "4033",
        "conversions": "161",
    }
    with pytest.raises(AnalyticsShapeError):
        range_figures_of(
            {**body, "rows": body["rows"] * 2}, source_id=PROPERTY, window=one, fetched_at=""
        )
