"""Search Console: one verified site, its name kept, and its search figures read when asked.

The owner asked for a connector that reads one verified site's queries, pages, clicks, impressions
and indexing issues for a named date range, read-only. This is it, in the shape
`brain.connectors.google_analytics` set for a Google source: a key file exchanged for a read-only
token per read (`brain.connectors.google_token`), a minimal index of the one thing connected, and a
`declaration.LiveReport` for every figure.

**This connector keeps a minimal index and reads every value live.** What the worker keeps is the
one site it was connected to: its address, the name a person asks for it by, the permission the
service account holds on it, and the department its readers are in. Clicks, impressions, the top
queries and pages and the sitemaps' errors and warnings are read from the Search Console API when
they are asked for, and are never stored, embedded or logged.

**The index is read from the account's site list, and only the connected site is kept.** A service
account can be added to several properties, and the list is the one call that says both that the
connected site is there and with what permission. Every other site it names is dropped before a
row is built, which is why the recorded list carries the canary as another site's address. See
`ONE_SITE_IS_KEPT_WHATEVER_THE_ACCOUNT_CAN_SEE`.

**A question's report is two calls, and a figure tool's is four, each made at once.** On Ask the
day-by-day totals over the last 90 days (summed into the last 7, 28 and 90 days, each ending
yesterday) and the site's sitemaps, which is where the API reports indexing errors and warnings.
Through `search_console.read_performance`, for the one range a workflow or an agent's step names
(`brain.connectors.date_range`, within sixteen months): that range's clicks and impressions, its
ten most clicked queries and its ten most clicked pages in the order Google gave, and the sitemaps.
They are sent together, so a read waits for the slowest after one token exchange, and a report any
of whose calls did not answer is not answered
(`declaration.A_REPORT_S_CALLS_ARE_MADE_AT_ONCE_AND_ANSWER_TOGETHER`). See
`THE_RANGES_ARE_THREE_AND_ONE_CALL_ANSWERS_ALL_THREE` and
`THE_TOP_TEN_ARE_GOOGLE_S_ORDER_FOR_THE_RANGE_ASKED`.

**Indexing issues are the sitemaps' own counts, and that is Google's limit, not this module's
choice.** The Search Console API exposes no Page indexing report; the one per-page source is URL
inspection, one call per address, which no question's budget holds. So the indexing issues read
are the errors and warnings Search Console reports for each submitted sitemap, and whether that is
enough is put to the owner as needs-rupash 133.

**The site's record is named by a digest of its address.** A record id's grammar has no room for a
colon or a slash, so the index keeps the site under a digest of its Search Console name and keeps
the name a person asks by beside it. See `A_SITE_IS_NAMED_BY_A_DIGEST_OF_ITS_ADDRESS`.

**Days are the install's days, and Google's are Pacific.** A window is counted back from the day
the question is asked on this server, while Search Console dates its data in Pacific time and
finishes a day about two days late, so the latest days of a window may be missing or provisional.
The answer is what Google had; nothing fills a missing day.

**Read as the service account, restricted, and never with more than read.** The key file is
exchanged for a token carrying `webmasters.readonly` only; the account is added to the one
property as a user with restricted permission; domain-wide delegation is refused in the guide and
impossible in the exchange. The visibility rule is the department named at connect, for
`google_analytics.ONE_DEPARTMENT_READS_A_CONNECTED_PROPERTY`'s reason.

Rejected: keeping the day-by-day figures in the index and summing them at question time. It is the
bulk sync the owner's rule forbids, and a figure kept is a figure quoted after Google revised it.
Rejected: URL inspection for indexing issues, one call per page, as above.

Scope: domain logic. Nothing here opens a socket, resolves a name, reads a clock or holds a key.

Task ids: M11.7.2
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from types import MappingProxyType
from typing import Any, Final, Self
from urllib.parse import quote

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
from brain.connectors.google_analytics import SERVICE_ACCOUNTS_URL, retry_after
from brain.connectors.google_analytics import Reply as Reply
from brain.connectors.manifest import (
    ChangeSignal,
    ConnectorManifest,
    FieldShape,
    HotUse,
    ProjectedEntity,
    ProjectedField,
    ToolDeclaration,
)
from brain.connectors.projection import ProjectedRecord
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
#: Why only the connected site is kept from the account's list.
ONE_SITE_IS_KEPT_WHATEVER_THE_ACCOUNT_CAN_SEE: Final = (
    "The service account may have been added to more than one Search Console property, and the "
    "list it reads names every one. Only the site the connection names is kept; every other site "
    "is dropped before a row is built, so the index holds what an administrator connected and "
    "nothing the account happens to reach besides."
)

#: Why three ranges, and why one call answers all three.
THE_RANGES_ARE_THREE_AND_ONE_CALL_ANSWERS_ALL_THREE: Final = (
    "A question names its range from a closed set: the last 7, 28 or 90 days, each ending "
    "yesterday. Clicks and impressions for all three are summed from one call reading the last 90 "
    "days day by day, so a question's report is that call and the sitemaps whichever range it "
    "names. Any other range is a figure tool's argument, never a question's."
)

#: Why a report is only ever asked of the connected site.
A_REPORT_READS_ONLY_THE_CONNECTED_SITE: Final = (
    "An index row names the site a report is asked of. A report for any site other than the one "
    "the connection was made with is refused before anything is sent."
)

#: Why a site's record is named by a digest of its name rather than by the name itself.
A_SITE_IS_NAMED_BY_A_DIGEST_OF_ITS_ADDRESS: Final = (
    "A record's id is what the redactor, a citation and a later read name it by, and its grammar "
    "admits letters, digits and . _ @ - and nothing else, so a site's own name, with its colon and "
    "slashes, cannot be one. The index names the site by a digest of its Search Console name, "
    "which no two sites share, and keeps the name a person asks by beside it; the report is built "
    "from the connection's own site, never from an id."
)

#: Why the top queries and pages are ten, in Google's order, for the range a tool asked for.
THE_TOP_TEN_ARE_GOOGLE_S_ORDER_FOR_THE_RANGE_ASKED: Final = (
    "The owner asked for a site's queries and pages, in the plural, for a named date range. A "
    "figure tool asks Search Console for the ten most clicked of each over the window it was "
    "given and hands them back in the order Google gave, each with its clicks, so the first is "
    "the most clicked and nothing is re-ranked here."
)

#: Why a figure that is not a count is refused.
A_COUNT_IS_A_NUMBER: Final = (
    "Search Console sends clicks and impressions as numbers and a sitemap's errors and warnings as "
    "whole numbers in strings. A value that is not one is a reply this does not read, and it is "
    "refused rather than shown to a person as a count."
)

# ---------------------------------------------------------------------------- the names
#: The connector's name, and the key `brain.ops.limits` records the verified ceiling under.
SEARCH_CONSOLE: Final = "search_console"
CONNECTOR_NAME: Final = SEARCH_CONSOLE
CEILING_NAME: Final = SEARCH_CONSOLE

#: The one entity kind: the site. Its figures are fields of it read live.
ENTITY_SITE: Final = "search_site"

#: This connector's own version, which moves when anything in the manifest moves.
VERSION: Final = "1.0.0"

#: What the field mapping names its specification.
SPEC_REF: Final = "search_console.webmasters_v3"

#: Google's address for the Search Console API, for every install.
SEARCH_CONSOLE_API_URL: Final = "https://www.googleapis.com/webmasters/v3"

#: Where Google documents the Search Console API's usage limits.
USAGE_LIMITS_URL: Final = "https://developers.google.com/webmaster-tools/limits"

#: The one scope a token for this source carries. Read-only, and Google's own name for it.
SCOPE: Final = "https://www.googleapis.com/auth/webmasters.readonly"

#: The two settings a connection is made with.
SITE_SETTING: Final = "site"
DEPARTMENT_SETTING: Final = "department"

#: How Search Console names a Domain property before its domain.
DOMAIN_PROPERTY_PREFIX: Final = "sc-domain:"

_LABEL: Final = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
#: A domain property, `sc-domain:example.com`, and a URL-prefix property, an http or https address
#: ending in a slash. Nothing else is a site, and nothing else is laid into an address.
DOMAIN_PROPERTY_RE: Final = re.compile(rf"^sc-domain:{_LABEL}(?:\.{_LABEL})+$")
URL_PREFIX_PROPERTY_RE: Final = re.compile(
    rf"^https?://{_LABEL}(?:\.{_LABEL})+(?::[0-9]{{1,5}})?/(?:[A-Za-z0-9._~-]+/)*$"
)

#: How often the worker reads the site list into the index. It changes when a person changes it.
READING_INTERVAL: Final = timedelta(hours=24)


# ------------------------------------------------------------------------ the figures
@dataclass(frozen=True)
class NamedWindow:
    """One range a question may name: the days back from the day asked, ending yesterday."""

    name: str
    days: int

    def first_day(self, today: date) -> date:
        return today - timedelta(days=self.days)


#: Every range a question may name. See `THE_RANGES_ARE_THREE_AND_ONE_CALL_ANSWERS_ALL_THREE`.
RANGES: Final[tuple[NamedWindow, ...]] = (
    NamedWindow("last_7_days", 7),
    NamedWindow("last_28_days", 28),
    NamedWindow("last_90_days", 90),
)

#: The longest range, which is how far back the one day-by-day call reads.
LONGEST: Final = max(RANGES, key=lambda one: one.days)

#: The most days one day-by-day call returns, which the call's row limit must hold.
DAY_ROWS: Final = LONGEST.days


def figure_field(label: str, named: str) -> str:
    """The field one count over one range is answered as: `clicks_last_28_days`."""
    return f"{label}_{named}"


#: The counts summed per range, by the name Search Console gives them.
COUNTS: Final[tuple[str, ...]] = ("clicks", "impressions")

#: Every figure a question on Ask can be answered with: each count over each named range, and the
#: sitemaps' own problems. The top queries and pages are a list, which no one field answers, so they
#: are a figure tool's (`RANGE_FIGURE_FIELDS`).
FIGURE_FIELDS: Final[tuple[str, ...]] = (
    *(figure_field(label, one.name) for label in COUNTS for one in RANGES),
    "sitemap_errors",
    "sitemap_warnings",
)

#: How many queries and pages a figure tool hands back, most clicked first: Search Console's own
#: performance report opens on ten rows. See `THE_TOP_TEN_ARE_GOOGLE_S_ORDER_FOR_THE_RANGE_ASKED`.
TOP_ROWS: Final = 10


def top_field(label: str, rank: int) -> str:
    """The field one ranked query or page is answered as: `top_query_1`, and its clicks beside."""
    return f"{label}_{rank}"


#: Every figure a figure tool answers for the window it was asked for.
RANGE_FIGURE_FIELDS: Final[tuple[str, ...]] = (
    "start_date",
    "end_date",
    *COUNTS,
    *(
        name
        for label in ("top_query", "top_page")
        for rank in range(1, TOP_ROWS + 1)
        for name in (top_field(label, rank), f"{top_field(label, rank)}_clicks")
    ),
    "sitemap_errors",
    "sitemap_warnings",
)

#: What each kind of report asks, in order: a question's two calls, a figure tool's four.
ASK_CALLS: Final = ("days", "sitemaps")
RANGE_CALLS: Final = ("totals", "queries", "pages", "sitemaps")

_WHOLE_RE: Final = re.compile(r"^[0-9]{1,18}$")
_DAY_RE: Final = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")


class SearchConsoleShapeError(ConnectorContractError):
    """A reply that is not the shape Google documents for it. Carries no value from the reply."""


# ------------------------------------------------------------------------ the site
def site_of(given: str) -> str:
    """The site as Search Console names it, out of what was typed, or empty when it is not one.

    The host is lower-cased, because a host name is not case-sensitive and the pin is compared
    exactly; a URL-prefix property's path is kept as typed.
    """
    text = given.strip()
    if text.casefold().startswith(DOMAIN_PROPERTY_PREFIX):
        text = text.casefold()
        return text if DOMAIN_PROPERTY_RE.match(text) else ""
    scheme, _, rest = text.partition("://")
    host, slash, path = rest.partition("/")
    text = f"{scheme.casefold()}://{host.casefold()}{slash}{path}"
    return text if URL_PREFIX_PROPERTY_RE.match(text) else ""


def site_name_of(site: str) -> str:
    """How a person names the site in a question: its domain, or its host and path.

    `sc-domain:example.com` is `example.com`, and `https://www.example.com/blog/` is
    `www.example.com/blog`.
    """
    if site.startswith(DOMAIN_PROPERTY_PREFIX):
        return site.removeprefix(DOMAIN_PROPERTY_PREFIX)
    return site.partition("://")[2].rstrip("/")


#: How many hexadecimal characters of the digest name a site's record.
SITE_ID_CHARS: Final = 32


def site_id_of(site: str) -> str:
    """The id a site's record is kept and read by.

    See `A_SITE_IS_NAMED_BY_A_DIGEST_OF_ITS_ADDRESS`.
    """
    return hashlib.sha256(site.encode("utf-8")).hexdigest()[:SITE_ID_CHARS]


def _encoded(site: str) -> str:
    """The site as one path segment. Checked first, so it is a site and nothing else."""
    if not site_of(site) or site_of(site) != site:
        msg = "a site is a Search Console property's own name, and only that is laid into a path"
        raise SearchConsoleShapeError(msg)
    return quote(site, safe="")


# ------------------------------------------------------------------------ the index
#: What is kept about the site, each earning its place under the twelve-field cap.
SITE_FIELDS: Final[tuple[ProjectedField, ...]] = (
    ProjectedField(name="site_name", shape=FieldShape.LABEL, uses=(HotUse.IDENTIFY,)),
    ProjectedField(name="permission_level", shape=FieldShape.STATUS, uses=(HotUse.FILTER,)),
)

#: The field a person names the site by.
LABEL_FIELD: Final = "site_name"

#: The index mapping, from the site list's `siteEntry` resource.
SITE_MAPPING: Final[tuple[FieldMapping, ...]] = (
    FieldMapping(target="id", source_path="siteUrl"),
    FieldMapping(target="permission_level", source_path="permissionLevel"),
)


def site_projection(*, visibility: Scope) -> ProjectedEntity:
    """What is kept about the site, and who may be granted it.

    The change signal is `UPDATED_SINCE` in the only sense one site allows: every read reads the
    whole of what is kept, so a change can never be missed between reads.
    """
    return ProjectedEntity(
        entity=ENTITY_SITE,
        fields=SITE_FIELDS,
        change_signal=ChangeSignal.UPDATED_SINCE,
        visibility=visibility,
    )


@dataclass(frozen=True)
class SiteListing(RestOperation):
    """The account's site list, carrying the one site the connection keeps from it.

    See `ONE_SITE_IS_KEPT_WHATEVER_THE_ACCOUNT_CAN_SEE`. An empty list is answered by Google with
    no `siteEntry` at all, as its JSON leaves out an empty repeated field, so that is read as no
    sites rather than as a reply in the wrong shape.
    """

    connected_site: str = ""

    def project(self, body: Any) -> tuple[Mapping[str, Any], ...]:
        if isinstance(body, Mapping) and "siteEntry" not in body:
            return ()
        return super().project(body)


def listing_for(site: str) -> SiteListing:
    """The Search Console API's site list, keeping `site` and nothing else."""
    spec = OperationSpec(
        operation_id="sites.list", method="get", path="/sites", records_at="siteEntry"
    )
    return SiteListing(
        base_url=SEARCH_CONSOLE_API_URL,
        operation=spec,
        transport=RestTransport(
            spec_ref=SPEC_REF, operation=spec.operation_id, entity=ENTITY_SITE, fields=SITE_MAPPING
        ),
        connected_site=site,
    )


def connected_rows(
    operation: RestOperation, body: Any, *, fetched_at: str
) -> TypedResult[SourceRecord]:
    """The site list's rows, the connected site's alone. See `SiteListing`."""
    site = operation.connected_site if isinstance(operation, SiteListing) else ""
    listed = operation.records(body, fetched_at=fetched_at) if operation.project(body) else None
    kept = () if listed is None else tuple(one for one in listed.records if one.id == site)
    return TypedResult[SourceRecord](records=kept, source=SPEC_REF, fetched_at=fetched_at)


# --------------------------------------------------------------------- the connection
@dataclass(frozen=True)
class SearchConsoleConnection:
    """One site and the one department that reads it, decided at connect, and nothing else."""

    site: str
    department: str

    def __post_init__(self) -> None:
        assert_holds_no_credential(type(self))
        if not self.site or site_of(self.site) != self.site:
            msg = "not a Search Console property"
            raise SettingRefusedError(msg, setting=SITE_SETTING)
        if not SLUG_RE.fullmatch(self.department):
            msg = "not a department's short name"
            raise SettingRefusedError(msg, setting=DEPARTMENT_SETTING)
        self.scope()

    @classmethod
    def from_settings(cls, settings: Mapping[str, str]) -> Self:
        return cls(
            site=site_of(settings.get(SITE_SETTING, "")),
            department=settings.get(DEPARTMENT_SETTING, "").strip(),
        )

    def scope(self) -> ConnectorScope:
        """What this connector was connected to: one site, by its Search Console name."""
        return ConnectorScope(resource_kind=ENTITY_SITE, selectors=(self.site,))

    def visibility(self) -> Scope:
        return Scope.department(self.department)


def manifest(
    connection: SearchConsoleConnection, *, ref: SecretRef, version: str = VERSION
) -> ConnectorManifest:
    """Everything this connector declares, for one connection (M11.7.2)."""
    return ConnectorManifest(
        name=SEARCH_CONSOLE,
        version=version,
        transport=TransportKind.REST,
        scope=connection.scope(),
        credential=CredentialBinding(ref=ref),
        tools=(
            ToolDeclaration(
                name="search_console.read_site",
                description=(
                    "Read the connected Search Console site: its name and the permission this "
                    "system holds on it."
                ),
                entity=ENTITY_SITE,
                identity_mode=IdentityMode.SERVICE,
            ),
            ToolDeclaration(
                name="search_console.read_performance",
                description=(
                    "Read the connected site's clicks, impressions, top ten queries and top ten "
                    "pages for any range within the last sixteen months, and its sitemaps' errors "
                    "and warnings, live from Search Console. Nothing is stored."
                ),
                entity=ENTITY_SITE,
                identity_mode=IdentityMode.SERVICE,
            ),
        ),
        projections=(site_projection(visibility=connection.visibility()),),
        ceiling=CEILING_NAME,
    )


def built_from_the_console(settings: Mapping[str, str], ref: SecretRef) -> ConnectorManifest:
    """The manifest a connection made on the Connectors screen declares."""
    return manifest(SearchConsoleConnection.from_settings(settings), ref=ref)


#: Why the read-back never reads a Search Console reply as an absence.
A_SITE_LIST_CANNOT_PROVE_ABSENCE: Final = (
    "The connected site is kept from the account's list, and a list without it says the account "
    "was taken off the site or the site was never added, which is a person to ask rather than a "
    "site that is gone. So the read-back is found or inconclusive, never absent."
)


def read_back_reading(operation: RestOperation, reply: Reply) -> Reading:
    """The site read back from the list: found, or the refusal or outage, or unreadable."""
    call = classify(status=reply.status)
    if call is not CallOutcome.OK:
        return Reading(outcome=call, matched=0, complete=False)
    try:
        found = connected_rows(operation, reply.body, fetched_at="").records
    except ConnectorContractError:
        return unreadable()
    if not found:
        return unreadable()
    return Reading(outcome=CallOutcome.OK, matched=len(found), complete=True)


# ------------------------------------------------------------------------ the reading
class SearchConsoleReading:
    """The connected site, read once a day from the account's list, into the index alone.

    A `declaration.ScopedReading`: its key is a key file, exchanged for a token carrying `SCOPE`.
    """

    def entities(self) -> tuple[str, ...]:
        return (ENTITY_SITE,)

    def refresh_interval(self) -> timedelta:
        return READING_INTERVAL

    def operation(
        self, entity: str, *, settings: Mapping[str, str], resolver: Resolver
    ) -> RestOperation:
        del resolver
        _assert_site(entity)
        return listing_for(SearchConsoleConnection.from_settings(settings).site)

    def key_scheme(self) -> KeyScheme:
        return KeyScheme.GOOGLE_SERVICE_ACCOUNT

    def token_scopes(self) -> tuple[str, ...]:
        return (SCOPE,)

    def first_page(self, entity: str) -> Mapping[str, str]:
        _assert_site(entity)
        return MappingProxyType({})

    def next_page(
        self, entity: str, asked: Mapping[str, str], body: Any, returned: int
    ) -> Mapping[str, str] | None:
        # The site list is one page: Google documents no paging on it.
        del entity, asked, body, returned
        return None

    def call_headers(self, settings: Mapping[str, str]) -> Mapping[str, str]:
        SearchConsoleConnection.from_settings(settings)
        return MappingProxyType({})

    def interpret(
        self, operation: RestOperation, *, status: int, body: Any, fetched_at: str
    ) -> PageReply:
        call = classify(status=status)
        if call is not CallOutcome.OK:
            return PageReply(call=call, rows=None)
        return PageReply(call=call, rows=connected_rows(operation, body, fetched_at=fetched_at))

    def retry_after(self, headers: Mapping[str, str]) -> float | None:
        return retry_after(headers)

    def allowance_spent(self, headers: Mapping[str, str]) -> bool:
        del headers
        return False

    def projected(
        self, entity: str, row: Mapping[str, Any], *, seen_at: datetime
    ) -> ProjectedRecord | None:
        """The site's index entry, named as a person asks for it, or None for a row naming none."""
        _assert_site(entity)
        raw = row.get("id")
        site = site_of(raw) if isinstance(raw, str) else ""
        if not site or site != raw:
            return None
        fields: dict[str, str | int | float | bool | datetime | None] = {
            LABEL_FIELD: site_name_of(site)[:MAX_LABEL_CHARS]
        }
        if isinstance(row.get("permission_level"), str):
            fields["permission_level"] = row["permission_level"]
        return ProjectedRecord(
            source=SEARCH_CONSOLE,
            entity=ENTITY_SITE,
            source_id=site_id_of(site),
            last_seen_at=seen_at,
            fields=fields,
        )


def _assert_site(entity: str) -> None:
    if entity != ENTITY_SITE:
        msg = f"this connector reads {ENTITY_SITE!r} and was asked for {entity!r}"
        raise ConnectorContractError(msg)


# ------------------------------------------------------------------------ the report
def _query(start: date, end: date, dimension: str | None, rows: int) -> bytes:
    """One search: its days, the one dimension its rows are by (none for totals), and its rows."""
    body: dict[str, Any] = {
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "rowLimit": rows,
    }
    if dimension is not None:
        body["dimensions"] = [dimension]
    return json.dumps(body, separators=(",", ":")).encode("utf-8")


def _count(value: Any) -> int:
    """A count as Google sends it: a number, or a whole number in a string. See
    `A_COUNT_IS_A_NUMBER`."""
    if isinstance(value, bool):
        raise SearchConsoleShapeError(A_COUNT_IS_A_NUMBER)
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, float) and value >= 0 and value.is_integer():
        return int(value)
    if isinstance(value, str) and _WHOLE_RE.match(value):
        return int(value)
    raise SearchConsoleShapeError(A_COUNT_IS_A_NUMBER)


def _sitemap_counts(sitemaps: Any) -> dict[str, str]:
    """The sitemaps' own errors and warnings, summed, or nothing when the site has none."""
    listed = sitemaps.get("sitemap", ())
    if not listed:
        return {}
    return {
        "sitemap_errors": str(sum(_count(one["errors"]) for one in listed)),
        "sitemap_warnings": str(sum(_count(one["warnings"]) for one in listed)),
    }


def figures_of(
    answers: tuple[Any, ...], *, source_id: str, today: date, fetched_at: str
) -> TypedResult[SourceRecord]:
    """A question's two answers as one record: the site's id, each count in each range, and the
    sitemaps' problems.

    The day-by-day totals are summed into each range by the day each row names, counting back from
    `today`; a range with no row contributes nothing rather than a nought. A reply this does not
    read is refused whole.
    """
    if len(answers) != len(ASK_CALLS):
        msg = "a question's Search Console report is two calls"
        raise SearchConsoleShapeError(msg)
    days, sitemaps = answers
    figures: dict[str, str] = {}
    try:
        rows = days.get("rows", ())
        if rows:
            sums = {figure_field(label, one.name): 0 for label in COUNTS for one in RANGES}
            for row in rows:
                day_text = row["keys"][0]
                if not isinstance(day_text, str) or not _DAY_RE.match(day_text):
                    msg = "a day-by-day row names no day"
                    raise SearchConsoleShapeError(msg)
                day = date.fromisoformat(day_text)
                counts = {label: _count(row[label]) for label in COUNTS}
                for one in RANGES:
                    if one.first_day(today) <= day < today:
                        for label in COUNTS:
                            sums[figure_field(label, one.name)] += counts[label]
            figures.update({name: str(value) for name, value in sums.items()})
        figures.update(_sitemap_counts(sitemaps))
    except (AttributeError, KeyError, IndexError, TypeError, ValueError):
        msg = "the report is not the shape Google documents"
        raise SearchConsoleShapeError(msg) from None
    return normalise(
        ENTITY_SITE, ({"id": source_id, **figures},), source=SEARCH_CONSOLE, fetched_at=fetched_at
    )


def _ranked(body: Any, label: str) -> dict[str, str]:
    """The rows of a search by query or by page, in the order Google gave them, as ranked fields.

    Google orders a search's rows by clicks, most first, and the order is kept as it came: the
    first row is `<label>_1`, and its clicks are `<label>_1_clicks`. A row with no key is refused.
    """
    ranked: dict[str, str] = {}
    for rank, row in enumerate(body.get("rows", ())[:TOP_ROWS], start=1):
        key = row["keys"][0]
        if not isinstance(key, str) or not key:
            msg = "a ranked row names no query or page"
            raise SearchConsoleShapeError(msg)
        ranked[top_field(label, rank)] = key[:MAX_LABEL_CHARS]
        ranked[f"{top_field(label, rank)}_clicks"] = str(_count(row["clicks"]))
    return ranked


def range_figures_of(
    answers: tuple[Any, ...], *, source_id: str, window: DateWindow, fetched_at: str
) -> TypedResult[SourceRecord]:
    """A figure tool's four answers as one record: the window's days, its clicks and impressions,
    its top ten queries and top ten pages in Google's order, and the sitemaps' problems."""
    if len(answers) != len(RANGE_CALLS):
        msg = "a figure tool's Search Console report is four calls"
        raise SearchConsoleShapeError(msg)
    totals, queries, pages, sitemaps = answers
    figures: dict[str, str] = {
        "start_date": window.start.isoformat(),
        "end_date": window.end.isoformat(),
    }
    try:
        rows = totals.get("rows", ())
        if len(rows) > 1:
            msg = "a search with no dimension is one row of totals"
            raise SearchConsoleShapeError(msg)
        for row in rows:
            figures.update({label: str(_count(row[label])) for label in COUNTS})
        figures.update(_ranked(queries, "top_query"))
        figures.update(_ranked(pages, "top_page"))
        figures.update(_sitemap_counts(sitemaps))
    except (AttributeError, KeyError, IndexError, TypeError, ValueError):
        msg = "the report is not the shape Google documents"
        raise SearchConsoleShapeError(msg) from None
    return normalise(
        ENTITY_SITE, ({"id": source_id, **figures},), source=SEARCH_CONSOLE, fetched_at=fetched_at
    )


class SearchConsoleReport:
    """The site's figures: for a question, every named range in two calls; for a figure tool, one
    window in four, made at once."""

    def entities(self) -> tuple[str, ...]:
        return (ENTITY_SITE,)

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
        """The calls, for the connected site only (`A_REPORT_READS_ONLY_THE_CONNECTED_SITE`).

        With no window, a question's two: the last 90 days day by day, and the sitemaps. With a
        window, a figure tool's four: the window's totals, its top ten queries, its top ten pages,
        and the sitemaps.
        """
        _assert_site(entity)
        connected = SearchConsoleConnection.from_settings(settings).site
        if source_id != site_id_of(connected):
            raise SearchConsoleShapeError(A_REPORT_READS_ONLY_THE_CONNECTED_SITE)
        base = f"{SEARCH_CONSOLE_API_URL}/sites/{_encoded(connected)}"
        query = f"{base}/searchAnalytics/query"
        sitemaps = ReportCall(url=f"{base}/sitemaps")
        if window is None:
            yesterday = today - timedelta(days=1)
            days = _query(LONGEST.first_day(today), yesterday, "date", DAY_ROWS)
            return (ReportCall(url=query, body=days), sitemaps)
        return (
            ReportCall(url=query, body=_query(window.start, window.end, None, 1)),
            ReportCall(url=query, body=_query(window.start, window.end, "query", TOP_ROWS)),
            ReportCall(url=query, body=_query(window.start, window.end, "page", TOP_ROWS)),
            sitemaps,
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
        """The answers as the site's figures: counted back from the day asked for a question, or
        for the window a figure tool named."""
        _assert_site(entity)
        rows = (
            figures_of(answers, source_id=source_id, today=today, fetched_at=fetched_at)
            if window is None
            else range_figures_of(
                answers, source_id=source_id, window=window, fetched_at=fetched_at
            )
        )
        return PageReply(call=CallOutcome.OK, rows=rows)


# ------------------------------------------------- connecting from the console (M11.7.2)
#: The Search Console API's library page, and Search Console itself. Google's own.
API_LIBRARY_URL: Final = (
    "https://console.cloud.google.com/apis/library/searchconsole.googleapis.com"
)
SEARCH_CONSOLE_URL: Final = "https://search.google.com/search-console"

#: The screens that prepare a site for this system, ending with the form that connects it.
GUIDE: Final = keyed(
    (
        GuideStep(
            key="service_account",
            title="Create a service account",
            text=(
                "In Google Cloud console open IAM & Admin, Service Accounts, and click Create "
                "service account, or use the one made for Google Analytics. Give it no role, and "
                "never domain-wide delegation: it reads one site as itself and needs nothing more."
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
            key="api",
            title="Switch on the Google Search Console API",
            text=(
                "In the same project open APIs & Services, Library, search for Google Search "
                "Console API and click Enable."
            ),
            sketch=Sketch(
                place="Google Cloud console",
                heading="Google Search Console API",
                button="Enable",
            ),
            link=API_LIBRARY_URL,
            link_label="Open the Google Search Console API",
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
            key="site_access",
            title="Add it to the one site with restricted permission",
            text=(
                "In Search Console choose the one verified property this system should read, "
                "open Settings, Users and permissions, click Add user, paste the service "
                "account's email address and choose Restricted. Add it to no other property."
            ),
            sketch=Sketch(
                place="Search Console",
                heading="Users and permissions",
                lines=(
                    SketchLine(LineKind.ITEM, "Service account's address", "Restricted", mark=True),
                ),
                button="Add",
            ),
            link=SEARCH_CONSOLE_URL,
            link_label="Open Search Console",
        ),
        GuideStep(
            key="connect",
            title="Name the site and the department, and choose the key file",
            text=(
                "Type the property exactly as Search Console shows it in its property list, such "
                "as https://www.example.com/ or sc-domain:example.com, the short name of the one "
                "department whose people may be granted its figures, choose the key file, then "
                "press Connect Search Console. Every figure is read from Google when somebody "
                "asks, and never kept."
            ),
            sketch=Sketch(
                place="Company Brain",
                heading="Connect Search Console",
                lines=(
                    SketchLine(LineKind.FIELD, "Site", "sc-domain:example.com", mark=True),
                    SketchLine(LineKind.FIELD, "Department", "marketing", mark=True),
                    SketchLine(LineKind.FIELD, "Key file", "company-brain.json", mark=True),
                ),
                button="Connect Search Console",
            ),
            asks=(SITE_SETTING, DEPARTMENT_SETTING, CREDENTIAL_ASK),
        ),
    )
)

#: What the Connectors screen asks for. The key is a service account's key file, chosen as a file.
CONSOLE: Final = ConsoleForm(
    settings=(
        Setting(
            name=SITE_SETTING,
            label="Site",
            hint=(
                "The property exactly as Search Console lists it: an address ending in a slash, "
                "such as https://www.example.com/, or a domain property, such as "
                "sc-domain:example.com. This connection reads that one site and no other."
            ),
            refused=(
                "That is not a Search Console property. Copy it from the property list: an "
                "address starting with https:// and ending in a slash, or sc-domain: and a domain."
            ),
        ),
        Setting(
            name=DEPARTMENT_SETTING,
            label="Department that reads its figures",
            hint=(
                "The short name of the one department whose people may be granted this site's "
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
        "needs restricted permission on the one property and nothing else, and this system asks "
        "only for the webmasters.readonly scope, never the webmasters scope that can change a "
        "property and never domain-wide delegation. The file is kept in the vault and never shown "
        "again."
    ),
    build=built_from_the_console,
    credential_shape=CredentialShape.KEY_FILE,
    example=ConnectExample(
        settings={SITE_SETTING: "sc-domain:example.com", DEPARTMENT_SETTING: "marketing"},
        fresh=lambda departments: {
            SITE_SETTING: f"sc-domain:acceptance-{secrets.token_hex(4)}.example",
            DEPARTMENT_SETTING: departments[0],
        },
        edit=SITE_SETTING,
        edited=lambda: f"sc-domain:acceptance-{secrets.token_hex(4)}.example",
    ),
)


#: This source's verified rate ceiling, which `brain.ops.limits.connector_ceiling` finds
#: on this declaration. See `brain.ops.limits.A_CEILING_LIVES_WITH_ITS_CONNECTOR`.
CEILING: Final = ConnectorLimit(
    name="search_console",
    per_minute=200,
    raisable=False,
    note=(
        "Google limits the Search Console API per user and per site rather than by plan: "
        "search analytics to 1,200 queries a minute for a site, and the site list and "
        "sitemaps to 200 a minute and 20 a second for a user "
        "(https://developers.google.com/webmaster-tools/limits). Recorded at 200 a minute, the "
        "lowest that governs a report's calls. There is no plan to buy that raises them."
    ),
)


CONNECTOR: Final = ConnectorDeclaration(
    ceiling=CEILING,
    name=SEARCH_CONSOLE,
    label="Search Console",
    guide=GUIDE,
    console=CONSOLE,
    read_back=ReadBack(
        reading=read_back_reading,
        recorded=(
            "SC-200-sites",
            "SC-200-days",
            "SC-200-totals",
            "SC-200-top-queries",
            "SC-200-top-pages",
            "SC-200-sitemaps",
            "SC-403-site",
            "SC-429-query",
            "SC-503-query",
        ),
        findings=(A_SITE_LIST_CANNOT_PROVE_ABSENCE,),
    ),
    recorded=Recorded(tested=True),
    reading=SearchConsoleReading(),
    report=SearchConsoleReport(),
    # The connected site, as Google Analytics' property is: its index fields and its figures,
    # each behind its own capability, the figures read live and the ranged ones asked by nobody.
    ask=AskRows(
        scoped_by=DEPARTMENT_SETTING,
        entities=(
            AskEntity(
                entity=ENTITY_SITE,
                fields=each_behind_its_own(
                    ENTITY_SITE,
                    (*(one.name for one in SITE_FIELDS), *FIGURE_FIELDS, *RANGE_FIGURE_FIELDS),
                ),
                description=(
                    "Look up the connected Search Console site by name: its clicks and "
                    "impressions for the last 7, 28 or 90 days, its top query and page and its "
                    "sitemaps' errors, read live from Google for a reader allowed them"
                ),
                named_by=LABEL_FIELD,
                live_only=(*FIGURE_FIELDS, *RANGE_FIGURE_FIELDS),
                unasked=frozenset(set(RANGE_FIGURE_FIELDS) - set(FIGURE_FIELDS)),
            ),
        ),
    ),
    scopes=KeyScopes(
        request=("webmasters.readonly", "restricted permission on the one property"),
        refuse=("webmasters", "domain-wide delegation"),
    ),
)
