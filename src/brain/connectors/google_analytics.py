"""Google Analytics: one property, its name kept, and its traffic read from Google when asked.

The owner asked for a connector that reads one property's traffic and conversion figures for a
named date range, read-only, and that an agent without that property bound gets nothing from. This
is it, in the shape every connector here takes: a module declaring `CONNECTOR` at its foot, a
cassette file of recordings in Google's documented envelope, and nothing else in the repository
that names it.

**This connector keeps a minimal index and reads every value live.** What the worker keeps is the
one property it was connected to: its id, its display name, when it was created and when it last
changed, and the department its readers are in. That row is what a question finds the property
by. Every figure (sessions, users, conversions) is read from Google's Data API while the asker
waits and is never stored, embedded or logged; the canary a recorded report carries as a figure is
looked for in every place a copy could be, and found in none. See
`brain.connectors.declaration.CONNECTORS_NEVER_BULK_SYNC`.

**A figure is a report, not the property read again, so it is declared as one.** The index is read
from the Admin API's `properties.get`, and the figures from the Data API's `runReport`, which is a
POST with a body naming the date ranges and the metrics. `AnalyticsReport` is this connector's
`declaration.LiveReport`: the one call and its interpretation into one record carrying the
property's id, which the answer lane lays over the index row exactly as it lays a live record's
fields. See `declaration.A_FIGURE_IS_READ_BY_A_REPORT_AND_A_RECORD_BY_ITS_OWN_ENDPOINT`.

**A question on Ask names its range from a closed set of four, and all four are one call.**
`yesterday`, `last_7_days`, `last_28_days` and `last_90_days`, each Google's own relative dates
resolved in the property's time zone. A report takes at most four date ranges, so one call answers
every range and every figure, which is what fits a question's live read budget
(`brain.connectors.live_read.LIVE_READ_TIMEOUT_MS`) with a token exchange in front of it. The
fields are named `<figure>_<range>`, so "what is the sessions last 28 days of <property>" is a
question the answer lane already knows how to ask (`brain.knowledge.connector_rows`). See
`THE_DATE_RANGE_IS_ONE_OF_FOUR_AND_ALL_FOUR_ARE_ONE_REPORT`.

**Any other range is a tool argument (M11.7.1's "a named date range").** A workflow or an agent's
step asks `google_analytics.read_traffic` with a first and last day or a period (last month, since
a date, last N days), held to `brain.connectors.date_range`'s grammar and to sixteen months back;
the report is then that one range (`range_body`), read with the task lane's patience, and answers
`sessions`, `users` and `conversions` beside the range's own days. See
`brain.knowledge.connector_figures`.

**Conversions are what Google now calls key events.** Google renamed the metric in 2024 and the
Data API reads it as `keyEvents`; the field a person asks for is `conversions`, in the owner's
word, and the mapping is `FIGURES`, one line, where a reviewer sees it.

**An agent without the property bound gets nothing, and is told what an absent property is told.**
Every read of the index is through the row plane at the reader's reach, and the row is reached only
through `read:analytics_property` in the department the connection names; the data steward is
granted it when the property is connected, and anybody else only by a grant somebody holding it
made. An agent runs at its caller's reach narrowed by its own ceiling, so an agent whose ceiling
does not bind the property compiles its read to nothing, which is the same object, in the same
time, as a property that does not exist. There is no second rule here and no list of agents: the
permission is decided where every permission is.

**Read as the service account, never as a person, and never with more than read.** The key is a
service account's key file, kept whole in the vault; each read exchanges it for a token carrying
`analytics.readonly` and nothing else, and the account is added to the one property as a Viewer.
Domain-wide delegation is refused in the guide and impossible in the exchange, which names no
subject (`brain.connectors.google_token`).

**The visibility rule is the department named at connect, as Freshdesk's is.** The row plane can
only test an equality a kept row carries, and a property has no finer-grained reader list this
connector could read without a scope it does not ask for. See
`ONE_DEPARTMENT_READS_A_CONNECTED_PROPERTY`.

Rejected, and each looks tidier:

*Keeping the figures in the index, refreshed daily.* That is the bulk sync the owner's rule forbids,
arriving as a cache: yesterday's sessions quoted as today's, and every figure a copy somebody could
read from a database backup.

*`google-analytics-data`, Google's client library.* It opens its own sockets over gRPC, outside the
pinned, address-checked caller every other source is read through, and brings its own credentials
machinery, which would be a second place a key file is read.

*The Data API's `getMetadata` in place of the Admin API for the index.* It lists the property's
dimensions and metrics and not its name, so a question could not name the property.

Scope: domain logic. Nothing here opens a socket, resolves a name, reads a clock or holds a key.

Task ids: M11.7.1
"""

from __future__ import annotations

import json
import re
import secrets
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from types import MappingProxyType
from typing import Any, Final, Self

from brain.connectors.ask import AskEntity, AskRows, each_behind_its_own
from brain.connectors.contract import (
    ConnectorContractError,
    ConnectorScope,
    CredentialBinding,
    TransportKind,
    assert_holds_no_credential,
)
from brain.connectors.date_range import DateWindow
from brain.connectors.declaration import (
    CREDENTIAL_ASK,
    ConnectExample,
    ConnectorDeclaration,
    ConsoleForm,
    CredentialShape,
    KeyScheme,
    KeyScopes,
    PageReply,
    Recorded,
    ReportCall,
    Setting,
    SettingRefusedError,
)
from brain.connectors.manifest import (
    ChangeSignal,
    ConnectorManifest,
    FieldShape,
    HotUse,
    ProjectedEntity,
    ProjectedField,
    ToolDeclaration,
)
from brain.connectors.projection import ProjectedRecord, ProjectedValue
from brain.connectors.rest import OperationSpec, RestOperation
from brain.connectors.throttle import CallOutcome, classify
from brain.connectors.transports import FieldMapping, RestTransport, SourceRecord, normalise
from brain.connectors.write_verification import ReadBack, Reading, unreadable
from brain.core.department import SLUG_RE
from brain.core.envelope import IdentityMode, TypedResult
from brain.core.projection import MAX_LABEL_CHARS
from brain.core.scope import Scope
from brain.ops.connect_steps import GuideStep, LineKind, Sketch, SketchLine, keyed
from brain.ops.limits import ConnectorLimit
from brain.ops.secrets import SecretRef
from brain.tools.fetch import Resolver

# ------------------------------------------------------------------ written-down reasons
#: Why the date range is a closed set, and why four.
THE_DATE_RANGE_IS_ONE_OF_FOUR_AND_ALL_FOUR_ARE_ONE_REPORT: Final = (
    "A question names its date range from a closed set: yesterday, the last 7, 28 or 90 days, "
    "each Google's own relative dates in the property's time zone. A report takes at most four "
    "date ranges, so one call reads every range and every figure, and one call after a token "
    "exchange is what a question's live read budget holds. A range outside the four is not a "
    "field, so it cannot be asked for and is never guessed at."
)

#: Why a connected property is read by one department.
ONE_DEPARTMENT_READS_A_CONNECTED_PROPERTY: Final = (
    "Google Analytics decides who sees a property by the users added to it, and reading that list "
    "would need a scope this connector does not ask for. The row plane tests an equality a kept "
    "row carries, so the connection names one department, the kept property carries it, and a "
    "person reaches the property and its figures only through a grant of read:analytics_property "
    "in that department. A property shared by two departments is read by the one named."
)

#: Why a report is only ever asked of the property the connection names.
A_REPORT_READS_ONLY_THE_CONNECTED_PROPERTY: Final = (
    "The service account may have been added to more than one property, and an index row names "
    "the property a report is asked of. A report for an id other than the one the connection was "
    "made with is refused before anything is sent, so what a question reads is what an "
    "administrator connected and nothing the account happens to reach besides."
)

#: Why a figure that is not a number is refused rather than shown.
A_FIGURE_IS_A_NUMBER: Final = (
    "Google sends every metric value as a decimal string. A value that is not one is a reply this "
    "does not read, and it is refused as a shape the declaration does not describe rather than "
    "shown to a person as a figure."
)

# ---------------------------------------------------------------------------- the names
#: The connector's name, and the key `brain.ops.limits` records the verified ceiling under.
GOOGLE_ANALYTICS: Final = "google_analytics"

#: The same string under the names every connectable module's tests read it by.
CONNECTOR_NAME: Final = GOOGLE_ANALYTICS
CEILING_NAME: Final = GOOGLE_ANALYTICS

#: The one entity kind: the property. Its figures are fields of it read live, not a second entity.
ENTITY_PROPERTY: Final = "analytics_property"

#: This connector's own version, which moves when anything in the manifest moves.
VERSION: Final = "1.0.0"

#: What the field mapping names its specification. A reference and not a document.
SPEC_REF: Final = "google_analytics.admin_v1beta"

#: Google's two addresses for every install: the Admin API for the index, the Data API for figures.
ADMIN_API_URL: Final = "https://analyticsadmin.googleapis.com"
DATA_API_URL: Final = "https://analyticsdata.googleapis.com"

#: Where Google documents the Data API's quotas, which `brain.ops.limits` records the ceiling from.
QUOTAS_URL: Final = "https://developers.google.com/analytics/devguides/reporting/data/v1/quotas"

#: The one scope a token for this source carries. Read-only, and Google's own name for it.
SCOPE: Final = "https://www.googleapis.com/auth/analytics.readonly"

#: What a property id is: the digits Google shows under Property details. Nothing else is laid
#: into an address, so a value with a slash or a colon in it could never choose another endpoint.
PROPERTY_ID_RE: Final = re.compile(r"^[1-9][0-9]{0,19}$")

#: How the Admin API names a property in its answer, before its id.
PROPERTY_RESOURCE_PREFIX: Final = "properties/"

#: How often the worker reads the property's name into the index. A name changes rarely, and one
#: call a day is nothing against the ceiling.
READING_INTERVAL: Final = timedelta(hours=24)

#: The two settings a connection is made with.
PROPERTY_SETTING: Final = "property"
DEPARTMENT_SETTING: Final = "department"


# ------------------------------------------------------------------------ the figures
@dataclass(frozen=True)
class NamedRange:
    """One date range a question may name, as Google's relative dates."""

    name: str
    start: str
    end: str


#: Every range a question may name, in Google's relative dates, each ending yesterday because
#: today's figures are still arriving. See
#: `THE_DATE_RANGE_IS_ONE_OF_FOUR_AND_ALL_FOUR_ARE_ONE_REPORT`.
RANGES: Final[tuple[NamedRange, ...]] = (
    NamedRange("yesterday", "yesterday", "yesterday"),
    NamedRange("last_7_days", "7daysAgo", "yesterday"),
    NamedRange("last_28_days", "28daysAgo", "yesterday"),
    NamedRange("last_90_days", "90daysAgo", "yesterday"),
)

#: Google's ceiling on the date ranges one report may carry, from the Data API reference for
#: `RunReportRequest.dateRanges` (https://developers.google.com/analytics/devguides/reporting/
#: data/v1/rest/v1beta/properties/runReport). `RANGES` must fit in one report.
MAX_DATE_RANGES_PER_REPORT: Final = 4

#: The metrics read, by Google's name, and the word a person asks for each by.
FIGURES: Final[Mapping[str, str]] = MappingProxyType(
    {"sessions": "sessions", "totalUsers": "users", "keyEvents": "conversions"}
)

#: The dimension Google adds to a report's rows when it carries more than one date range.
DATE_RANGE_DIMENSION: Final = "dateRange"

#: A metric value as Google sends it: a decimal number in a string. See `A_FIGURE_IS_A_NUMBER`.
_FIGURE_RE: Final = re.compile(r"^-?[0-9]+(\.[0-9]+)?([eE][+-]?[0-9]+)?$")


def figure_field(label: str, named: str) -> str:
    """The field one figure over one range is answered as: `sessions_last_28_days`."""
    return f"{label}_{named}"


#: Every figure field a report can answer, figure by figure and range by range.
FIGURE_FIELDS: Final[tuple[str, ...]] = tuple(
    figure_field(label, one.name) for label in FIGURES.values() for one in RANGES
)

#: What a report asks for, the same for every property: every range and every figure, and the rows
#: whose figures are all zero kept, so a quiet day is answered as nought rather than as unknown.
REPORT_BODY: Final[Mapping[str, Any]] = MappingProxyType(
    {
        "dateRanges": [{"startDate": r.start, "endDate": r.end, "name": r.name} for r in RANGES],
        "metrics": [{"name": name} for name in FIGURES],
        "keepEmptyRows": True,
    }
)


#: What a figure tool answers for one range: the range's days, and each figure over them.
RANGE_FIGURE_FIELDS: Final[tuple[str, ...]] = ("start_date", "end_date", *FIGURES.values())


def range_body(window: DateWindow) -> dict[str, Any]:
    """The report for one window: its two days as Google's dates, and every figure over them."""
    return {
        "dateRanges": [{"startDate": window.start.isoformat(), "endDate": window.end.isoformat()}],
        "metrics": [{"name": name} for name in FIGURES],
        "keepEmptyRows": True,
    }


class AnalyticsShapeError(ConnectorContractError):
    """A reply that is not the shape Google documents for it. Carries no value from the reply."""


# ------------------------------------------------------------------------ the index
#: What is kept about the property, each earning its place under the twelve-field cap.
PROPERTY_FIELDS: Final[tuple[ProjectedField, ...]] = (
    ProjectedField(name="display_name", shape=FieldShape.LABEL, uses=(HotUse.IDENTIFY,)),
    ProjectedField(
        name="create_time", shape=FieldShape.TIMESTAMP, uses=(HotUse.FILTER, HotUse.SORT)
    ),
    ProjectedField(
        name="update_time", shape=FieldShape.TIMESTAMP, uses=(HotUse.FILTER, HotUse.SORT)
    ),
)

#: The field a person names the property by, cut to a label's length when it is kept.
LABEL_FIELD: Final = "display_name"

#: The index mapping: our names, from the Admin API's `Property` resource.
PROPERTY_MAPPING: Final[tuple[FieldMapping, ...]] = (
    FieldMapping(target="id", source_path="name"),
    FieldMapping(target="display_name", source_path="displayName"),
    FieldMapping(target="create_time", source_path="createTime"),
    FieldMapping(target="update_time", source_path="updateTime"),
)


def property_projection(*, visibility: Scope) -> ProjectedEntity:
    """What is kept about the property, and who may be granted it.

    The change signal is `UPDATED_SINCE`: the property carries its own `updateTime`, and every read
    reads the whole of what is kept, one property, so a change can never be missed between reads.
    """
    return ProjectedEntity(
        entity=ENTITY_PROPERTY,
        fields=PROPERTY_FIELDS,
        change_signal=ChangeSignal.UPDATED_SINCE,
        visibility=visibility,
    )


def property_id_of(given: str) -> str:
    """The property's id out of what was typed or answered, or empty when there is none.

    The digits alone, or Google's resource name `properties/<digits>`, which is how the Admin API
    names a property and how its address bar shows it.
    """
    text = given.strip()
    if text.startswith(PROPERTY_RESOURCE_PREFIX):
        text = text.removeprefix(PROPERTY_RESOURCE_PREFIX)
    return text if PROPERTY_ID_RE.match(text) else ""


def projected_fields(row: Mapping[str, Any]) -> dict[str, ProjectedValue]:
    """One property as the fields the index may hold, built from the declared names.

    The label is cut to `MAX_LABEL_CHARS` for Freshdesk's reason: a long name would otherwise be
    refused at the write and the property would be missing from the index.
    """
    built: dict[str, ProjectedValue] = {}
    for one in PROPERTY_FIELDS:
        if one.name not in row:
            continue
        value = row[one.name]
        if one.name == LABEL_FIELD and isinstance(value, str):
            value = value[:MAX_LABEL_CHARS]
        built[one.name] = value
    return built


def operation_for(property_id: str) -> RestOperation:
    """The Admin API's read of the one property, with its id already in the path.

    The id is laid into the path here rather than passed as an argument, because the worker's
    first page carries no settings; it is checked against `PROPERTY_ID_RE` first, so it is digits.
    """
    if not PROPERTY_ID_RE.match(property_id):
        msg = "a property id is digits, and only digits are laid into an address"
        raise AnalyticsShapeError(msg)
    spec = OperationSpec(
        operation_id="properties.get",
        method="get",
        path=f"/v1beta/properties/{property_id}",
        returns_list=False,
    )
    return RestOperation(
        base_url=ADMIN_API_URL,
        operation=spec,
        transport=RestTransport(
            spec_ref=SPEC_REF,
            operation=spec.operation_id,
            entity=ENTITY_PROPERTY,
            fields=PROPERTY_MAPPING,
        ),
    )


# --------------------------------------------------------------------- the connection
@dataclass(frozen=True)
class AnalyticsConnection:
    """One property and the one department that reads it, decided at connect, and nothing else.

    No client and no credential: `assert_holds_no_credential` runs on the class at construction.
    Each refusal names its setting through `SettingRefusedError`, so the Connectors screen marks the
    one that was wrong.
    """

    property_id: str
    department: str

    def __post_init__(self) -> None:
        assert_holds_no_credential(type(self))
        if not PROPERTY_ID_RE.match(self.property_id):
            msg = "not a Google Analytics property id"
            raise SettingRefusedError(msg, setting=PROPERTY_SETTING)
        if not SLUG_RE.fullmatch(self.department):
            msg = f"not a department's short name. {ONE_DEPARTMENT_READS_A_CONNECTED_PROPERTY}"
            raise SettingRefusedError(msg, setting=DEPARTMENT_SETTING)
        self.scope()

    @classmethod
    def from_settings(cls, settings: Mapping[str, str]) -> Self:
        """The connection a stored row's settings describe."""
        return cls(
            property_id=property_id_of(settings.get(PROPERTY_SETTING, "")),
            department=settings.get(DEPARTMENT_SETTING, "").strip(),
        )

    def scope(self) -> ConnectorScope:
        """What this connector was connected to: one property, by its id."""
        return ConnectorScope(resource_kind=ENTITY_PROPERTY, selectors=(self.property_id,))

    def visibility(self) -> Scope:
        """Who may be granted the property. See `ONE_DEPARTMENT_READS_A_CONNECTED_PROPERTY`."""
        return Scope.department(self.department)


# ---------------------------------------------------------------------- the manifest
def manifest(
    connection: AnalyticsConnection, *, ref: SecretRef, version: str = VERSION
) -> ConnectorManifest:
    """Everything this connector declares, for one connection (M11.7.1).

    Both tools are SERVICE reads: the source enforces nothing on our behalf past the one property
    the account was added to, so ours are the only permissions there are, and the row plane's
    predicate is what `brain.tools.registry` asks a service tool for.
    """
    return ConnectorManifest(
        name=GOOGLE_ANALYTICS,
        version=version,
        transport=TransportKind.REST,
        scope=connection.scope(),
        credential=CredentialBinding(ref=ref),
        tools=(
            ToolDeclaration(
                name="google_analytics.read_property",
                description=(
                    "Read the connected Google Analytics property: its name and when it was "
                    "created and last changed."
                ),
                entity=ENTITY_PROPERTY,
                identity_mode=IdentityMode.SERVICE,
            ),
            ToolDeclaration(
                name="google_analytics.read_traffic",
                description=(
                    "Read the connected property's sessions, users and conversions for any range "
                    "within the last sixteen months, live from Google Analytics. Nothing is stored."
                ),
                entity=ENTITY_PROPERTY,
                identity_mode=IdentityMode.SERVICE,
            ),
        ),
        projections=(property_projection(visibility=connection.visibility()),),
        ceiling=CEILING_NAME,
    )


def built_from_the_console(settings: Mapping[str, str], ref: SecretRef) -> ConnectorManifest:
    """The manifest a connection made on the Connectors screen declares."""
    return manifest(AnalyticsConnection.from_settings(settings), ref=ref)


# ------------------------------------------------------------------------ the replies
@dataclass(frozen=True)
class Reply:
    """One answered call as the read-back reads it: the status, the headers and the decoded body."""

    status: int
    headers: Mapping[str, str] = field(default_factory=dict)
    body: Any = None


def retry_after(headers: Mapping[str, str]) -> float | None:
    """The wait Google stated, in seconds, or None. Google documents none for these APIs.

    Read without regard to case, because the worker's caller lower-cases every header name.
    """
    for name, value in headers.items():
        if name.casefold() != "retry-after":
            continue
        try:
            seconds = float(value.strip())
        except ValueError:
            return None
        return seconds if seconds >= 0 else None
    return None


#: Why the read-back never reads a Google Analytics reply as an absence.
A_PROPERTY_READ_CANNOT_PROVE_ABSENCE: Final = (
    "The property is read by its id, and Google answers a property that is gone, or that the "
    "account was taken off, with a refusal rather than an empty answer. So an answered read holds "
    "the property or it holds something that is not one, and neither is evidence that the "
    "property is not there: the read-back is found or inconclusive, never absent."
)


def read_back_reading(operation: RestOperation, reply: Reply) -> Reading:
    """The property read back: found, or the refusal or outage the status says, or unreadable.

    An answer carrying no property is unreadable rather than empty. See
    `A_PROPERTY_READ_CANNOT_PROVE_ABSENCE`.
    """
    call = classify(status=reply.status)
    if call is not CallOutcome.OK:
        return Reading(outcome=call, matched=0, complete=False)
    try:
        found = operation.records(reply.body, fetched_at="").records
    except ConnectorContractError:
        return unreadable()
    if not found:
        return unreadable()
    return Reading(outcome=CallOutcome.OK, matched=len(found), complete=True)


# ------------------------------------------------------------------------ the reading
class AnalyticsReading:
    """The connected property, read once a day into the minimal index and nothing else.

    A `declaration.ScopedReading`: its key is a key file, exchanged for a token carrying `SCOPE`.
    """

    def entities(self) -> tuple[str, ...]:
        return (ENTITY_PROPERTY,)

    def refresh_interval(self) -> timedelta:
        return READING_INTERVAL

    def operation(
        self, entity: str, *, settings: Mapping[str, str], resolver: Resolver
    ) -> RestOperation:
        # The address is Google's constant, checked when the call is prepared.
        del resolver
        _assert_property(entity)
        return operation_for(AnalyticsConnection.from_settings(settings).property_id)

    def key_scheme(self) -> KeyScheme:
        return KeyScheme.GOOGLE_SERVICE_ACCOUNT

    def token_scopes(self) -> tuple[str, ...]:
        return (SCOPE,)

    def first_page(self, entity: str) -> Mapping[str, str]:
        _assert_property(entity)
        return MappingProxyType({})

    def next_page(
        self, entity: str, asked: Mapping[str, str], body: Any, returned: int
    ) -> Mapping[str, str] | None:
        # One property is one object: there is never a second page.
        del entity, asked, body, returned
        return None

    def call_headers(self, settings: Mapping[str, str]) -> Mapping[str, str]:
        # Built for its refusal of a setting that is not a property; Google needs no header here.
        AnalyticsConnection.from_settings(settings)
        return MappingProxyType({})

    def interpret(
        self, operation: RestOperation, *, status: int, body: Any, fetched_at: str
    ) -> PageReply:
        call = classify(status=status)
        if call is not CallOutcome.OK:
            return PageReply(call=call, rows=None)
        return PageReply(call=call, rows=operation.records(body, fetched_at=fetched_at))

    def retry_after(self, headers: Mapping[str, str]) -> float | None:
        return retry_after(headers)

    def allowance_spent(self, headers: Mapping[str, str]) -> bool:
        del headers
        return False

    def projected(
        self, entity: str, row: Mapping[str, Any], *, seen_at: datetime
    ) -> ProjectedRecord | None:
        """The property's index entry, or None for a row that names no property."""
        _assert_property(entity)
        raw = row.get("id")
        property_id = property_id_of(raw) if isinstance(raw, str) else ""
        if not property_id:
            return None
        return ProjectedRecord(
            source=GOOGLE_ANALYTICS,
            entity=ENTITY_PROPERTY,
            source_id=property_id,
            last_seen_at=seen_at,
            fields=projected_fields(row),
        )


def _assert_property(entity: str) -> None:
    if entity != ENTITY_PROPERTY:
        msg = f"this connector reads {ENTITY_PROPERTY!r} and was asked for {entity!r}"
        raise ConnectorContractError(msg)


# ------------------------------------------------------------------------ the report
def figures_of(body: Any, *, source_id: str, fetched_at: str) -> TypedResult[SourceRecord]:
    """One report as one record: the property's id and every figure the report answered.

    Read by the metric names the reply states rather than by position, and refused whole when the
    reply names a metric or a range that was not asked for, or carries a figure that is not a
    number: a reply this does not read is never partly shown. A range the reply leaves out
    contributes nothing, rather than a nought nobody sent.
    """
    try:
        headers = [one["name"] for one in body.get("metricHeaders", ())]
        dimensions = [one["name"] for one in body.get("dimensionHeaders", ())]
        rows = body.get("rows", ())
        if sorted(headers) != sorted(FIGURES):
            msg = "the report names metrics other than the ones asked for"
            raise AnalyticsShapeError(msg)
        if rows and dimensions != [DATE_RANGE_DIMENSION]:
            msg = "the report's rows are not one per date range"
            raise AnalyticsShapeError(msg)
        named = {one.name for one in RANGES}
        figures: dict[str, str] = {}
        for row in rows:
            range_name = row["dimensionValues"][0]["value"]
            values = [one["value"] for one in row["metricValues"]]
            if range_name not in named or len(values) != len(headers):
                msg = "a report row names a range that was not asked for"
                raise AnalyticsShapeError(msg)
            for header, value in zip(headers, values, strict=True):
                if not isinstance(value, str) or not _FIGURE_RE.match(value):
                    raise AnalyticsShapeError(A_FIGURE_IS_A_NUMBER)
                figures[figure_field(FIGURES[header], range_name)] = value
    except (AttributeError, KeyError, IndexError, TypeError):
        msg = "the report is not the shape Google documents"
        raise AnalyticsShapeError(msg) from None
    return normalise(
        ENTITY_PROPERTY,
        ({"id": source_id, **figures},),
        source=GOOGLE_ANALYTICS,
        fetched_at=fetched_at,
    )


def range_figures_of(
    body: Any, *, source_id: str, window: DateWindow, fetched_at: str
) -> TypedResult[SourceRecord]:
    """One window's report as one record: the property's id, the window's days and each figure.

    One date range carries no `dateRange` dimension, so the report is at most one row of metrics,
    read by the names its headers state; no row is the window's days and no figure, rather than
    noughts nobody sent. A reply this does not read is refused whole, as `figures_of` refuses one.
    """
    figures: dict[str, str] = {
        "start_date": window.start.isoformat(),
        "end_date": window.end.isoformat(),
    }
    try:
        headers = [one["name"] for one in body.get("metricHeaders", ())]
        rows = body.get("rows", ())
        if sorted(headers) != sorted(FIGURES) or len(rows) > 1 or body.get("dimensionHeaders"):
            msg = "the report is not one row of the figures asked for"
            raise AnalyticsShapeError(msg)
        for row in rows:
            values = [one["value"] for one in row["metricValues"]]
            for header, value in zip(headers, values, strict=True):
                if not isinstance(value, str) or not _FIGURE_RE.match(value):
                    raise AnalyticsShapeError(A_FIGURE_IS_A_NUMBER)
                figures[FIGURES[header]] = value
    except (AttributeError, KeyError, IndexError, TypeError, ValueError):
        msg = "the report is not the shape Google documents"
        raise AnalyticsShapeError(msg) from None
    return normalise(
        ENTITY_PROPERTY,
        ({"id": source_id, **figures},),
        source=GOOGLE_ANALYTICS,
        fetched_at=fetched_at,
    )


class AnalyticsReport:
    """The property's figures for every named range, read by one report while somebody waits.

    The service's credentials, declared: a connection holds one key file, issued for the account
    added to the property, and there is no person's own Analytics key for a read to run under.
    """

    def entities(self) -> tuple[str, ...]:
        return (ENTITY_PROPERTY,)

    def identity_mode(self, entity: str) -> IdentityMode:
        del entity
        return IdentityMode.SERVICE

    def request_for(
        self,
        entity: str,
        source_id: str,
        *,
        settings: Mapping[str, str],
        today: date,
        window: DateWindow | None,
    ) -> tuple[ReportCall, ...]:
        """The one report, for the connected property only: every named range for a question on
        Ask, or the one window a figure tool asked for. See
        `A_REPORT_READS_ONLY_THE_CONNECTED_PROPERTY`. `today` is unused: Google resolves relative
        dates in the property's own time zone, and a window is already its days."""
        del today
        _assert_property(entity)
        connected = AnalyticsConnection.from_settings(settings).property_id
        if source_id != connected:
            raise AnalyticsShapeError(A_REPORT_READS_ONLY_THE_CONNECTED_PROPERTY)
        body = dict(REPORT_BODY) if window is None else range_body(window)
        return (
            ReportCall(
                url=f"{DATA_API_URL}/v1beta/properties/{connected}:runReport",
                body=json.dumps(body, separators=(",", ":")).encode("utf-8"),
            ),
        )

    def interpret(
        self,
        entity: str,
        source_id: str,
        *,
        answers: tuple[Any, ...],
        today: date,
        window: DateWindow | None,
        fetched_at: str,
    ) -> PageReply:
        """The one report's body as the property's figures. A report is one call here, and
        `today` is unused, for `request_for`'s reason."""
        del today
        _assert_property(entity)
        if len(answers) != 1:
            msg = "a Google Analytics report is one call, and this was answered as several"
            raise AnalyticsShapeError(msg)
        rows = (
            figures_of(answers[0], source_id=source_id, fetched_at=fetched_at)
            if window is None
            else range_figures_of(
                answers[0], source_id=source_id, window=window, fetched_at=fetched_at
            )
        )
        return PageReply(call=CallOutcome.OK, rows=rows)


# ------------------------------------------------- connecting from the console (M11.7.1)
#: Google Cloud console's service accounts page, and the two APIs' library pages. Google's own.
SERVICE_ACCOUNTS_URL: Final = "https://console.cloud.google.com/iam-admin/serviceaccounts"
DATA_API_LIBRARY_URL: Final = (
    "https://console.cloud.google.com/apis/library/analyticsdata.googleapis.com"
)
ADMIN_API_LIBRARY_URL: Final = (
    "https://console.cloud.google.com/apis/library/analyticsadmin.googleapis.com"
)
#: Google Analytics itself, where a property's access and details are.
ANALYTICS_URL: Final = "https://analytics.google.com/analytics/web/"

#: The screens that prepare a property for this system, ending with the form that connects it.
GUIDE: Final = keyed(
    (
        GuideStep(
            key="service_account",
            title="Create a service account",
            text=(
                "In Google Cloud console open IAM & Admin, Service Accounts, and click Create "
                "service account. Name it after this system and give it no role. Never grant it "
                "domain-wide delegation: it reads one property as itself and needs nothing more."
            ),
            sketch=Sketch(
                place="Google Cloud console",
                heading="Service accounts",
                menu=("IAM", "Service Accounts", "Roles"),
                menu_mark="Service Accounts",
                lines=(SketchLine(LineKind.TEXT, "No domain-wide delegation"),),
                button="Create service account",
            ),
            link=SERVICE_ACCOUNTS_URL,
            link_label="Open Service Accounts",
        ),
        GuideStep(
            key="data_api",
            title="Switch on the Google Analytics Data API",
            text=(
                "In the same project open APIs & Services, Library, search for Google Analytics "
                "Data API and click Enable. It is what the figures are read from."
            ),
            sketch=Sketch(
                place="Google Cloud console",
                heading="Google Analytics Data API",
                button="Enable",
            ),
            link=DATA_API_LIBRARY_URL,
            link_label="Open the Google Analytics Data API",
        ),
        GuideStep(
            key="admin_api",
            title="Switch on the Google Analytics Admin API",
            text=(
                "Search the Library again for Google Analytics Admin API and click Enable. It is "
                "what the property's name is read from, so a question can name the property."
            ),
            sketch=Sketch(
                place="Google Cloud console",
                heading="Google Analytics Admin API",
                button="Enable",
            ),
            link=ADMIN_API_LIBRARY_URL,
            link_label="Open the Google Analytics Admin API",
        ),
        GuideStep(
            key="key_file",
            title="Create a key file for it",
            text=(
                "Back in Service Accounts, open the account, choose the Keys tab, click Add key, "
                "Create new key, choose JSON and click Create. A key file downloads. Keep it only "
                "until the last step: this system keeps it in its vault and never shows it again."
            ),
            sketch=Sketch(
                place="Google Cloud console",
                heading="Keys",
                menu=("Details", "Permissions", "Keys"),
                menu_mark="Keys",
                lines=(SketchLine(LineKind.ITEM, "Key type", "JSON", mark=True),),
                button="Create",
            ),
            link=SERVICE_ACCOUNTS_URL,
            link_label="Open Service Accounts",
        ),
        GuideStep(
            key="property_access",
            title="Add it to the one property as a Viewer",
            text=(
                "In Google Analytics open Admin, choose the one property this system should read, "
                "open Property access management, click the plus and Add users, paste the service "
                "account's email address and give it the Viewer role. Add it to nothing else."
            ),
            sketch=Sketch(
                place="Google Analytics",
                heading="Property access management",
                lines=(
                    SketchLine(LineKind.ITEM, "Service account's address", "Viewer", mark=True),
                ),
                button="Add",
            ),
            link=ANALYTICS_URL,
            link_label="Open Google Analytics",
        ),
        GuideStep(
            key="property_id",
            title="Copy the property's id",
            text=(
                "Still in Admin, open Property details and copy the Property ID, which is a "
                "number. It is the one property this connection reads."
            ),
            sketch=Sketch(
                place="Google Analytics",
                heading="Property details",
                lines=(SketchLine(LineKind.FIELD, "Property ID", "123456789", mark=True),),
            ),
            link=ANALYTICS_URL,
            link_label="Open Google Analytics",
        ),
        GuideStep(
            key="connect",
            title="Name the property and the department, and choose the key file",
            text=(
                "Type the property's id, the short name of the one department whose people may be "
                "granted its figures, choose the key file, then press Connect Google Analytics. "
                "The worker then keeps the property's name; every figure is read from Google when "
                "somebody asks, and never kept."
            ),
            sketch=Sketch(
                place="Company Brain",
                heading="Connect Google Analytics",
                lines=(
                    SketchLine(LineKind.FIELD, "Property ID", "123456789", mark=True),
                    SketchLine(LineKind.FIELD, "Department", "marketing", mark=True),
                    SketchLine(LineKind.FIELD, "Key file", "company-brain.json", mark=True),
                ),
                button="Connect Google Analytics",
            ),
            asks=(PROPERTY_SETTING, DEPARTMENT_SETTING, CREDENTIAL_ASK),
        ),
    )
)

#: What the Connectors screen asks for. The key is a service account's key file, chosen as a file.
CONSOLE: Final = ConsoleForm(
    settings=(
        Setting(
            name=PROPERTY_SETTING,
            label="Property ID",
            hint=(
                "The number Google Analytics shows under Admin, Property details, Property ID. "
                "This connection reads that one property and no other."
            ),
            refused=(
                "That is not a Google Analytics property id. Copy the Property ID from Admin, "
                "Property details: it is a number, such as 123456789."
            ),
        ),
        Setting(
            name=DEPARTMENT_SETTING,
            label="Department that reads its figures",
            hint=(
                "The short name of the one department whose people may be granted this property's "
                "figures, as the Departments page shows it. Everybody else is not shown them."
            ),
            refused=(
                "That is not a department's short name. Use lower-case letters, digits and "
                "underscores, exactly as the Departments page shows it."
            ),
        ),
    ),
    credential_label="The service account's key file",
    credential_hint=(
        "Choose the JSON key file Google Cloud downloaded for the service account. The account "
        "needs Viewer on the one property and nothing else, and this system asks only for the "
        "analytics.readonly scope, never analytics.edit and never domain-wide delegation. The file "
        "is kept in the vault and never shown again."
    ),
    build=built_from_the_console,
    credential_shape=CredentialShape.KEY_FILE,
    example=ConnectExample(
        settings={PROPERTY_SETTING: "123456789", DEPARTMENT_SETTING: "marketing"},
        fresh=lambda departments: {
            PROPERTY_SETTING: str(10**8 + secrets.randbelow(9 * 10**8)),
            DEPARTMENT_SETTING: departments[0],
        },
        edit=PROPERTY_SETTING,
        edited=lambda: str(10**8 + secrets.randbelow(9 * 10**8)),
    ),
)


#: This source's verified rate ceiling, which `brain.ops.limits.connector_ceiling` finds
#: on this declaration. See `brain.ops.limits.A_CEILING_LIVES_WITH_ITS_CONNECTOR`.
CEILING: Final = ConnectorLimit(
    name="google_analytics",
    per_minute=20,
    per_day=20_000,
    note=(
        "Google counts the Data API in tokens rather than calls: a standard property allows "
        "14,000 tokens an hour to one Cloud project and 200,000 a day, and a simple report "
        "costs about ten (https://developers.google.com/analytics/devguides/reporting/data/v1/"
        "quotas). At ten a report that is 23 calls a minute and 20,000 calls a day, recorded "
        "at 20 a minute. An Analytics 360 property allows ten times as much, which is the "
        "property owner's plan to buy, so the ceiling can be raised."
    ),
)


CONNECTOR: Final = ConnectorDeclaration(
    ceiling=CEILING,
    name=GOOGLE_ANALYTICS,
    label="Google Analytics",
    guide=GUIDE,
    console=CONSOLE,
    read_back=ReadBack(
        reading=read_back_reading,
        recorded=(
            "GA-200-property",
            "GA-200-report",
            "GA-200-range-report",
            "GA-200-token",
            "GA-400-token",
            "GA-401",
            "GA-403-property",
            "GA-429-report",
            "GA-500-report",
        ),
        findings=(A_PROPERTY_READ_CANNOT_PROVE_ABSENCE,),
    ),
    recorded=Recorded(tested=True),
    reading=AnalyticsReading(),
    report=AnalyticsReport(),
    # The fields the index keeps and the figures read live, each behind its own capability, so a
    # reader may be told the property's name and not its traffic, or one range and not another.
    # The figures are classified although never kept, because the redactor withholds a field
    # nothing classifies from everybody. A figure tool's ranged fields are asked by no question.
    ask=AskRows(
        scoped_by=DEPARTMENT_SETTING,
        entities=(
            AskEntity(
                entity=ENTITY_PROPERTY,
                fields=each_behind_its_own(
                    ENTITY_PROPERTY,
                    (
                        *(one.name for one in PROPERTY_FIELDS),
                        *FIGURE_FIELDS,
                        *RANGE_FIGURE_FIELDS,
                    ),
                ),
                description=(
                    "Look up the connected Google Analytics property by name: its sessions, users "
                    "and conversions for yesterday or the last 7, 28 or 90 days, read live from "
                    "Google for a reader allowed them"
                ),
                named_by=LABEL_FIELD,
                live_only=(*FIGURE_FIELDS, *RANGE_FIGURE_FIELDS),
                unasked=frozenset(RANGE_FIGURE_FIELDS),
            ),
        ),
    ),
    scopes=KeyScopes(
        request=("analytics.readonly", "Viewer on the one property"),
        refuse=("analytics.edit", "domain-wide delegation"),
    ),
)
