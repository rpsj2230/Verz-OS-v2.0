"""Cloudflare: zones, DNS records and security events, read with a token that cannot change them.

A company's Cloudflare account holds the one thing on this list a mistaken write takes a website
off the internet with, so the shape of this connector is decided by that before anything else.
**The token this connector is connected with can only read.** It is a custom API token with three
permissions, `Zone Read`, `DNS Read` and `Analytics Read`, over the zones of the one account it was
given, and the form, the guide and the vault slot all ask for exactly those words. **A DNS change is
never made with it and never made directly**: it is a prepared action a person approves, held by
the gate like every action with one of the owner's sensitive effects (`DNS_CHANGE_TOOL`,
`prepare_dns_change`). See `A_DNS_CHANGE_IS_ONLY_EVER_PREPARED_FOR_A_PERSON`.

**Sending an approved change is a grant of its own, off until its own key is given** (`DNS_CHANGES`,
the owner's register rows OWN-24, OWN-141 and ARC-A-140). The source's page offers "Allow approved
DNS changes", which asks for a second token with DNS Edit over the same zones and keeps it in a
vault slot of its own; the read token's guidance still refuses every write permission. With the
key, an approved change is sent with it by `brain.ops.connector_write_run`, once, and read back
with the read token by the one-record call before it is reported done (`DnsChangeWrites`). Without
it, the change is held and approved exactly as before and nothing is sent, and the approval card
says `THIS_INSTALL_HAS_NOT_ALLOWED_DNS_CHANGES`. Rejected: one token for both, which makes every
read a call with the power to change DNS.

**This connector keeps a minimal index and reads every value live.** What it keeps of a zone is its
id, its name, its status and the account it belongs to; of a DNS record, its id, its zone, its name
and its type. A record's content, its time to live and whether it is proxied are read from
Cloudflare when a question asks for them, by the one-record call, and are never stored, embedded or
logged: the list the worker reads carries the content, and the mapping here does not name it, so it
never arrives. A security event is not indexed at all: it is read for a named window when a question
asks. The canary planted in every recorded record's content proves the first half on every build.
It is declared as `CONNECTOR` at the foot of this module (`brain.connectors.declaration`).

**A DNS record is listed only under its zone, so the worker reads the zones first and then each
zone's records** (`brain.connectors.declaration.ListedUnder`, M11.7.3). The index names a record by
its zone's id and its own, joined, because neither Cloudflare's list nor its one-record call can be
reached without the zone, and a question has only the index row to start from. Rejected: an index
id of the record's own alone, which is unique at Cloudflare and would leave the live read no way to
address the record it names.

**The account is part of what every kept row is scoped by, so a token wider than the guide asked
for fails a read rather than widening the index.** The zones list takes an account filter, and a
reading's first page is not told its connection's settings, so the filter cannot be sent. Instead
the visibility rule is the department the connection names *and* the account it names
(`CloudflareConnection.visibility`), a zone carries the account Cloudflare says it belongs to, and
the worker refuses to keep a row whose field disagrees with its rule
(`brain.ops.connector_sync.stored_fields`). A token that reaches a second account therefore stops
the read on the page that shows it, with the constant sentence a disagreeing reply leaves. See
`A_ZONE_OF_ANOTHER_ACCOUNT_STOPS_THE_READ`. Rejected: filtering such zones out, which would leave a
token that can read two accounts looking correctly connected.

**The visibility rule is the department named at connect, as Freshdesk's is**, for Freshdesk's
reason: the row plane can only test an equality a kept row carries, and one connection has one
predicate. A person granted `read:zone` or `read:dns_record` in that department reaches the rows;
nobody else does, and they are told what an absent record is told.

**Every read is a full pass, declared as the pull signal the vocabulary has.** Neither list takes
an updated-since filter, so each reading re-reads every zone and record, which is an updated-since
cursor that always starts at the beginning, as Freshdesk's every-ticket read is, and is declared
`ChangeSignal.UPDATED_SINCE` for that reason. It sees every change on each pass and, being a full
enumeration, every deletion too. Rejected: `ChangeSignal.NONE`, which is true of no pull source
and would forbid the index the owner asked for.

**Security events are read for a window from a closed list, never a date somebody typed**
(`SecurityWindow`). Cloudflare's GraphQL Analytics API answers `firewallEventsAdaptive` for a zone
between two instants, and the instants are computed here from the window's name and the moment of
the question. The events a question is told carry what happened, where and to what path, and
deliberately not the visitor's address or user agent: see
`A_SECURITY_EVENT_IS_READ_WITHOUT_ITS_VISITOR`.

**What is not done, stated once.** A security event has no question on Ask yet: the live read
executor calls a source with GET, the GraphQL API takes POST, and a question naming a window has no
question shape; the request and its reading are built and tested here.

Scope: domain logic. Nothing here opens a socket, resolves a name or reads a clock; the instant a
window ends at is a parameter.

Task ids: M11.7.3
"""

from __future__ import annotations

import enum
import ipaddress
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Any, Final

from brain.connectors.contract import (
    ConnectorContractError,
    ConnectorScope,
    CredentialBinding,
    TransportKind,
    assert_holds_no_credential,
)
from brain.connectors.declaration import (
    ConnectorDeclaration,
    ConsoleForm,
    KeyScheme,
    ListedUnder,
    PageReply,
    Recorded,
    Setting,
    SettingRefusedError,
    WriteCall,
    WriteGrant,
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
from brain.connectors.rest import OperationSpec, ParameterSpec, RestOperation
from brain.connectors.throttle import CallOutcome, classify
from brain.connectors.transports import FieldMapping, RestTransport, normalise
from brain.connectors.write_verification import ReadBack, Reading, unreadable
from brain.core.department import SLUG_RE
from brain.core.envelope import IdentityMode, SideEffect, ToolDefinition
from brain.core.projection import MAX_LABEL_CHARS
from brain.core.scope import Clause, Op, Scope
from brain.gate.leash import Action
from brain.ops.connect_steps import GuideStep, LineKind, Sketch, SketchLine, keyed
from brain.ops.secrets import SecretRef
from brain.tools.fetch import Resolver

# ------------------------------------------------------------------ written-down reasons
#: Why a DNS change is a prepared action and never a call with the token this connects with.
A_DNS_CHANGE_IS_ONLY_EVER_PREPARED_FOR_A_PERSON: Final = (
    "The token a Cloudflare connection holds can read zones, DNS records and analytics and can "
    "change nothing, and the guide, the form and the vault slot ask for exactly that. A DNS change "
    "is therefore not a tool on the read manifest, whose read-only binding refuses one, but an "
    "action prepared for a person to approve: a tool that declares a write and the owner's DNS "
    "effect, which caps it below Autonomous whatever its leash says, so the gate suspends it and "
    "an approver who holds write:dns_record in the record's department is shown what would change."
)

#: Why an approved change is sent with a key of its own and read back with the read key.
A_DNS_CHANGE_IS_SENT_WITH_ITS_OWN_KEY_AND_READ_BACK_WITH_THE_READ_KEY: Final = (
    "An approved DNS change is sent with the second token the install gave for DNS changes, never "
    "with the read token, and the record is then read again with the read token by its one-record "
    "call. It is reported done only when every field the change set holds what was approved: the "
    "name, the type, the content, and the time to live and proxying where the change set them. "
    "A record read back otherwise is reported failed, naming the fields that differ."
)

#: Why a zone of another account stops a read rather than being left out.
A_ZONE_OF_ANOTHER_ACCOUNT_STOPS_THE_READ: Final = (
    "The connection names one account, and a zone carries the account Cloudflare says it belongs "
    "to. Every kept row is scoped by that account as well as by the department, so a zone whose "
    "account is another disagrees with its own rule and the worker stops the read on that page. "
    "Leaving the zone out instead would keep a token that can read two accounts looking correctly "
    "connected, and the token is what decides what Cloudflare hands this system."
)

#: Why a security event is read without the visitor's address or user agent.
A_SECURITY_EVENT_IS_READ_WITHOUT_ITS_VISITOR: Final = (
    "A security event says what Cloudflare did, when, where the request came from by country, "
    "which host and path it asked for and which rule matched. It is also a record of a visitor, "
    "and an IP address and a user agent are personal data about somebody who never agreed to be "
    "asked about. So the query names neither, and a question that needs them is answered in "
    "Cloudflare's own dashboard by somebody entitled to it there."
)

#: Why the window is a name from a list rather than two dates.
A_WINDOW_IS_NAMED_FROM_A_CLOSED_LIST: Final = (
    "Cloudflare refuses a window longer than a zone's plan keeps, and answers an empty list for a "
    "window nothing happened in. A date typed into a question can be either, and a question "
    "cannot tell which it got. A window named from a short list is one this connector computes "
    "from the moment of the question and knows the source will answer, so an empty answer means "
    "nothing happened in it."
)

#: Why a reply whose envelope says it failed is never an empty page.
AN_ENVELOPE_THAT_SAYS_IT_FAILED_IS_NOT_AN_EMPTY_PAGE: Final = (
    "Cloudflare wraps every answer in an envelope with success, errors and result. A reply whose "
    "envelope does not say success true has not answered, whatever its status, and reading its "
    "missing result as no zones or no records is how a refusal becomes an absence."
)

# ---------------------------------------------------------------------------- the names
#: The connector's name, and the key `brain.ops.limits` records the verified ceiling under.
CLOUDFLARE: Final = "cloudflare"

#: The same string under the name every connectable module's tests read it by.
CONNECTOR_NAME: Final = CLOUDFLARE

#: The verified source this connector runs against in `brain.ops.limits`: its own.
CEILING_NAME: Final = CLOUDFLARE

#: The entity kinds this connector returns.
ZONE: Final = "zone"
DNS_RECORD: Final = "dns_record"
SECURITY_EVENT: Final = "security_event"

#: This connector's own version, which moves when anything in the manifest moves.
VERSION: Final = "1.0.0"

#: What the field mappings name their specification.
SPEC_REF: Final = "cloudflare.v4"

#: Where every call goes: Cloudflare's API, the same for every account.
API_BASE: Final = "https://api.cloudflare.com/client/v4"

#: Where a person creates the token in the dashboard.
API_TOKENS_URL: Final = "https://dash.cloudflare.com/profile/api-tokens"

#: The three permissions the token is created with, in the dashboard's own words
#: (https://developers.cloudflare.com/fundamentals/api/reference/permissions/).
TOKEN_PERMISSIONS: Final[tuple[str, str, str]] = ("Zone Read", "DNS Read", "Analytics Read")

#: The permission a change would need, which the read token must not hold.
WRITE_PERMISSION: Final = "DNS Write"

#: Cloudflare's identifiers for an account, a zone and a DNS record: 32 lower-case hex digits.
IDENTIFIER_RE: Final = re.compile(r"[0-9a-f]{32}")

#: Cloudflare numbers pages from one.
FIRST_PAGE: Final = 1

#: The largest page the zones list honours (per_page is 5 to 50).
ZONE_PAGE_SIZE: Final = 50

#: The DNS records page this reading asks for. Cloudflare's own default, so most zones are read in
#: one call and a larger zone is paged by `result_info`.
DNS_PAGE_SIZE: Final = 100

#: How often the worker reads a connected account into its index. Zones and records change rarely,
#: and a pass is one call per fifty zones and one per zone.
READING_INTERVAL: Final = timedelta(hours=1)

#: The header Cloudflare sends saying how much of the window is left: `"default";r=50;t=30`
#: (https://developers.cloudflare.com/fundamentals/api/reference/limits/).
RATE_LIMIT_HEADER: Final = "Ratelimit"
_REMAINING_RE: Final = re.compile(r"(?:^|;)\s*r=(\d+)")

#: The two settings a connection is made with, named once for the form, the reading and tests.
ACCOUNT_SETTING: Final = "account_id"
DEPARTMENT_SETTING: Final = "department"

#: The field a zone carries its account in, which the visibility rule also names.
ACCOUNT_FIELD: Final = "account_id"

#: The path parameter a zone's id goes into, and the field a record carries it in.
ZONE_PARAMETER: Final = "zone_id"

#: The field a prepared change's row carries the record's index id in.
RECORD_KEY: Final = "record"

#: How a DNS record is listed: under each zone, by the zone's id.
DNS_RECORD_LISTING: Final = ListedUnder(parent=ZONE, parameter=ZONE_PARAMETER)


class CloudflareEnvelopeError(ConnectorContractError):
    """A reply whose envelope did not say it answered. See the reason it names."""


# ------------------------------------------------------------------------ the endpoints
def _query(name: str) -> ParameterSpec:
    return ParameterSpec(name=name, location="query")


def _path(name: str) -> ParameterSpec:
    return ParameterSpec(name=name, location="path", required=True)


#: `GET /zones`: the zones the token reaches, a page at a time.
LIST_ZONES: Final = OperationSpec(
    operation_id="listZones",
    method="get",
    path="/zones",
    parameters=(_query("page"), _query("per_page")),
    records_at="result",
)

#: `GET /zones/{zone_id}`: one zone.
GET_ZONE: Final = OperationSpec(
    operation_id="getZone",
    method="get",
    path="/zones/{zone_id}",
    parameters=(_path(ZONE_PARAMETER),),
    records_at="result",
    returns_list=False,
)

#: `GET /zones/{zone_id}/dns_records`: one zone's records, a page at a time. It takes no id filter.
LIST_DNS_RECORDS: Final = OperationSpec(
    operation_id="listDnsRecords",
    method="get",
    path="/zones/{zone_id}/dns_records",
    parameters=(_path(ZONE_PARAMETER), _query("page"), _query("per_page")),
    records_at="result",
)

#: `GET /zones/{zone_id}/dns_records/{dns_record_id}`: one record, with its content.
GET_DNS_RECORD: Final = OperationSpec(
    operation_id="getDnsRecord",
    method="get",
    path="/zones/{zone_id}/dns_records/{dns_record_id}",
    parameters=(_path(ZONE_PARAMETER), _path("dns_record_id")),
    records_at="result",
    returns_list=False,
)

#: `PATCH /zones/{zone_id}/dns_records/{dns_record_id}`: what an approved change would send. Named
#: so the prepared action and its owner question describe one call; nothing here sends it.
PATCH_DNS_RECORD: Final = OperationSpec(
    operation_id="patchDnsRecord",
    method="patch",
    path="/zones/{zone_id}/dns_records/{dns_record_id}",
    parameters=(_path(ZONE_PARAMETER), _path("dns_record_id")),
    records_at="result",
    returns_list=False,
)

#: `POST /graphql`: Cloudflare's GraphQL Analytics API, where security events are read.
GRAPHQL_PATH: Final = "/graphql"


def _mapping(*pairs: tuple[str, str]) -> tuple[FieldMapping, ...]:
    return tuple(FieldMapping(target=target, source_path=source) for target, source in pairs)


#: A zone as the index keeps it. The mapping is an allowlist: what it does not name never arrives.
ZONE_MAPPING: Final = _mapping(
    ("id", "id"), ("name", "name"), ("status", "status"), (ACCOUNT_FIELD, "account.id")
)

#: A DNS record as the list the worker reads names it. **The content is not named**, so the value
#: the list carries never reaches anything this connector returns from a scheduled read.
DNS_LIST_MAPPING: Final = _mapping(("id", "id"), ("name", "name"), ("type", "type"))

#: The values of one record, read live and never kept.
LIVE_DNS_FIELDS: Final[tuple[str, ...]] = ("content", "ttl", "proxied")

#: A DNS record as the one-record call reads it while somebody waits: the index's fields and the
#: values. `DNS_RECORD_FIELDS` does not name the values, so `kept_fields` could not keep them.
DNS_LIVE_MAPPING: Final = (*DNS_LIST_MAPPING, *_mapping(*((one, one) for one in LIVE_DNS_FIELDS)))


def _operation(spec: OperationSpec, entity: str, fields: tuple[FieldMapping, ...]) -> RestOperation:
    return RestOperation(
        base_url=API_BASE,
        operation=spec,
        transport=RestTransport(
            spec_ref=SPEC_REF, operation=spec.operation_id, entity=entity, fields=fields
        ),
    )


def zones_operation() -> RestOperation:
    """The zones list, which the worker walks first."""
    return _operation(LIST_ZONES, ZONE, ZONE_MAPPING)


def zone_operation() -> RestOperation:
    """One zone by its id, for a live read."""
    return _operation(GET_ZONE, ZONE, ZONE_MAPPING)


def dns_records_operation() -> RestOperation:
    """One zone's records, which the worker walks under each zone it kept."""
    return _operation(LIST_DNS_RECORDS, DNS_RECORD, DNS_LIST_MAPPING)


def dns_record_operation() -> RestOperation:
    """One record by its zone and its id, with its values, for a live read."""
    return _operation(GET_DNS_RECORD, DNS_RECORD, DNS_LIVE_MAPPING)


# --------------------------------------------------------------------- the connection
@dataclass(frozen=True)
class CloudflareConnection:
    """One account and the one department that reads it, decided at connect, and nothing else.

    No client and no credential: `assert_holds_no_credential` runs on the class at construction.
    Each refusal names its setting, so the Connectors screen marks the one that was wrong.
    """

    account_id: str
    department: str

    def __post_init__(self) -> None:
        assert_holds_no_credential(type(self))
        if not IDENTIFIER_RE.fullmatch(self.account_id):
            msg = (
                f"{self.account_id!r} is not a Cloudflare account id, which is 32 hex digits. "
                f"{A_ZONE_OF_ANOTHER_ACCOUNT_STOPS_THE_READ}"
            )
            raise SettingRefusedError(msg, setting=ACCOUNT_SETTING)
        if not SLUG_RE.fullmatch(self.department):
            msg = f"{self.department!r} is not a department's short name, so no grant could name it"
            raise SettingRefusedError(msg, setting=DEPARTMENT_SETTING)
        self.scope()

    @classmethod
    def from_settings(cls, settings: Mapping[str, str]) -> CloudflareConnection:
        """The connection a stored row's settings describe. An account id is case-free hex."""
        return cls(
            account_id=settings[ACCOUNT_SETTING].strip().casefold(),
            department=settings[DEPARTMENT_SETTING],
        )

    def scope(self) -> ConnectorScope:
        """What this connector was connected to: one account, named."""
        return ConnectorScope(resource_kind="account", selectors=(self.account_id,))

    def visibility(self) -> Scope:
        """Who may be granted the kept rows, and the account they must belong to.

        See `A_ZONE_OF_ANOTHER_ACCOUNT_STOPS_THE_READ`: the account clause is what makes a zone of
        another account a row that disagrees with its own rule.
        """
        return Scope(
            clauses=(
                Clause(field=DEPARTMENT_SETTING, op=Op.EQ, value=self.department),
                Clause(field=ACCOUNT_FIELD, op=Op.EQ, value=self.account_id),
            )
        )


# ------------------------------------------------------------------------- the projection
#: What is kept about a zone. The account is a join key and the rule's second clause.
ZONE_FIELDS: Final[tuple[ProjectedField, ...]] = (
    ProjectedField(name="name", shape=FieldShape.LABEL, uses=(HotUse.IDENTIFY,)),
    ProjectedField(name="status", shape=FieldShape.STATUS, uses=(HotUse.FILTER, HotUse.COUNT)),
    ProjectedField(name=ACCOUNT_FIELD, shape=FieldShape.JOIN_KEY, uses=(HotUse.JOIN,)),
)

#: What is kept about a DNS record: its zone, its name and its type, and none of its values.
DNS_RECORD_FIELDS: Final[tuple[ProjectedField, ...]] = (
    ProjectedField(name=ZONE_PARAMETER, shape=FieldShape.JOIN_KEY, uses=(HotUse.JOIN,)),
    ProjectedField(name="name", shape=FieldShape.LABEL, uses=(HotUse.IDENTIFY,)),
    ProjectedField(name="type", shape=FieldShape.STATUS, uses=(HotUse.FILTER, HotUse.COUNT)),
)

#: The fields each entity keeps, by entity.
KEPT: Final[Mapping[str, tuple[ProjectedField, ...]]] = MappingProxyType(
    {ZONE: ZONE_FIELDS, DNS_RECORD: DNS_RECORD_FIELDS}
)

#: Cloudflare fields this connector deliberately never keeps, with the reason each is out.
FETCHED_LIVE_INSTEAD: Final[Mapping[str, str]] = MappingProxyType(
    {
        "content": "a record's value, which is what a question asks for and the owner's rule reads "
        "live; the scheduled list's mapping does not name it",
        "ttl": "a value of the record, read with its content",
        "proxied": "a value of the record, read with its content",
        "name_servers": "a zone's value, and a list besides",
        "security events": "read for a named window when asked, and never indexed at all",
    }
)


def projections(connection: CloudflareConnection) -> tuple[ProjectedEntity, ...]:
    """What is kept about a zone and a record, and the rule that decides who may read a row."""
    return tuple(
        ProjectedEntity(
            entity=entity,
            fields=fields,
            change_signal=ChangeSignal.UPDATED_SINCE,
            visibility=connection.visibility(),
        )
        for entity, fields in KEPT.items()
    )


def kept_fields_of(entity: str, row: Mapping[str, Any]) -> dict[str, ProjectedValue]:
    """One row as the fields its index entry may hold, built from the declared names.

    A label is cut to `MAX_LABEL_CHARS`, for Freshdesk's reason: a long name is otherwise refused at
    ingest and the record is missing from the index rather than shortened in it.
    """
    built: dict[str, ProjectedValue] = {}
    for field in KEPT[entity]:
        if field.name not in row:
            continue
        value = row[field.name]
        if field.shape is FieldShape.LABEL and isinstance(value, str):
            value = value[:MAX_LABEL_CHARS]
        built[field.name] = value
    return built


# --------------------------------------------------------------------------- the manifest
#: The tools a connection offers. All read, all with the connection's own token.
TOOLS: Final[tuple[ToolDeclaration, ...]] = (
    ToolDeclaration(
        name="cloudflare.list_zones",
        description="List the zones of the connected Cloudflare account: name and status.",
        entity=ZONE,
        identity_mode=IdentityMode.SERVICE,
    ),
    ToolDeclaration(
        name="cloudflare.read_zone",
        description="Read one Cloudflare zone by its id, live: its name, status and account.",
        entity=ZONE,
        identity_mode=IdentityMode.SERVICE,
    ),
    ToolDeclaration(
        name="cloudflare.list_dns_records",
        description=(
            "List one Cloudflare zone's DNS records: name and type, and never their content."
        ),
        entity=DNS_RECORD,
        identity_mode=IdentityMode.SERVICE,
    ),
    ToolDeclaration(
        name="cloudflare.read_dns_record",
        description=(
            "Read one DNS record live, with its content, time to live and whether it is proxied. "
            "The values are read for the question that asks and never stored. Reading only: a "
            "change is prepared for a person to approve."
        ),
        entity=DNS_RECORD,
        identity_mode=IdentityMode.SERVICE,
    ),
    ToolDeclaration(
        name="cloudflare.read_security_events",
        description=(
            "Read one zone's security events for the past hour or the past 24 hours, live: what "
            "Cloudflare did, when, the country, host and path, and the rule. Never the visitor's "
            "address or user agent."
        ),
        entity=SECURITY_EVENT,
        identity_mode=IdentityMode.SERVICE,
    ),
)


def manifest(
    connection: CloudflareConnection, *, ref: SecretRef, version: str = VERSION
) -> ConnectorManifest:
    """Everything this connector declares, for one connection (M11.7.3).

    **The binding is read-only**, `CredentialBinding`'s default, so a write tool on this manifest
    is refused by `ConnectorManifest` itself, and the DNS change is not one: see
    `A_DNS_CHANGE_IS_ONLY_EVER_PREPARED_FOR_A_PERSON`. **Every tool declares SERVICE
    identity**, the honest reading of one token for the account. `ceiling` is the verified source
    name in `brain.ops.limits`.
    """
    return ConnectorManifest(
        name=CLOUDFLARE,
        version=version,
        transport=TransportKind.REST,
        scope=connection.scope(),
        credential=CredentialBinding(ref=ref),
        tools=TOOLS,
        projections=projections(connection),
        ceiling=CEILING_NAME,
    )


def built_from_the_console(settings: Mapping[str, str], ref: SecretRef) -> ConnectorManifest:
    """The manifest a connection made on the Connectors screen declares."""
    return manifest(CloudflareConnection.from_settings(settings), ref=ref)


# ------------------------------------------------------------------ what a reply means
def answered(body: Any) -> Mapping[str, Any]:
    """The envelope, refused unless it says it answered. See the reason it raises with."""
    if not isinstance(body, Mapping) or body.get("success") is not True:
        raise CloudflareEnvelopeError(AN_ENVELOPE_THAT_SAYS_IT_FAILED_IS_NOT_AN_EMPTY_PAGE)
    return body


def last_page(body: Mapping[str, Any]) -> bool:
    """Whether the envelope says this was the last page. A missing or odd count is not the last."""
    info = body.get("result_info")
    if not isinstance(info, Mapping):
        return False
    page, pages = info.get("page"), info.get("total_pages")
    if not (isinstance(page, int) and isinstance(pages, int)):
        return False
    return page >= pages


def interpret(operation: RestOperation, *, status: int, body: Any, fetched_at: str) -> PageReply:
    """One answered call: its outcome, and its rows only when it answered.

    The classification is `throttle.classify`'s. A reply that is not a failure by its status and
    whose envelope does not say success is refused, never read as empty: see
    `AN_ENVELOPE_THAT_SAYS_IT_FAILED_IS_NOT_AN_EMPTY_PAGE`.
    """
    call = classify(status=status)
    if call is not CallOutcome.OK:
        return PageReply(call=call, rows=None)
    envelope = answered(body)
    # A list that is not its last page is part of an answer; one record is the whole of one.
    more = operation.operation.returns_list and not last_page(envelope)
    return PageReply(
        call=call, rows=operation.records(envelope, fetched_at=fetched_at, truncated=more)
    )


def retry_after(headers: Mapping[str, str]) -> float | None:
    """The wait Cloudflare stated, in seconds, or None when it stated nothing usable."""
    stated = _header(headers, "Retry-After")
    try:
        seconds = float(stated)
    except ValueError:
        return None
    return seconds if seconds > 0 else None


def allowance_spent(headers: Mapping[str, str]) -> bool:
    """Whether the `Ratelimit` header says nothing is left in the window."""
    found = _REMAINING_RE.search(_header(headers, RATE_LIMIT_HEADER))
    return found is not None and int(found.group(1)) <= 0


def _header(headers: Mapping[str, str], name: str) -> str:
    wanted = name.casefold()
    return next((value for key, value in headers.items() if key.casefold() == wanted), "").strip()


# ------------------------------------------------------------------ reading on a schedule
class CloudflareReading:
    """An account's zones, then each zone's records, into the minimal index and nothing else.

    A method named after a module function calls that function: inside a method the bare name is
    this module's.
    """

    def entities(self) -> tuple[str, ...]:
        return (ZONE, DNS_RECORD)

    def refresh_interval(self) -> timedelta:
        return READING_INTERVAL

    def listed_under(self, entity: str) -> ListedUnder | None:
        return DNS_RECORD_LISTING if entity == DNS_RECORD else None

    def operation(
        self, entity: str, *, settings: Mapping[str, str], resolver: Resolver
    ) -> RestOperation:
        # The address is Cloudflare's own and is checked when each page is prepared.
        del resolver
        CloudflareConnection.from_settings(settings)
        if entity == ZONE:
            return zones_operation()
        _assert_entity(entity, DNS_RECORD)
        return dns_records_operation()

    def key_scheme(self) -> KeyScheme:
        return KeyScheme.BEARER

    def first_page(self, entity: str) -> Mapping[str, str]:
        _assert_entity(entity, ZONE, DNS_RECORD)
        size = ZONE_PAGE_SIZE if entity == ZONE else DNS_PAGE_SIZE
        return MappingProxyType({"page": str(FIRST_PAGE), "per_page": str(size)})

    def next_page(
        self, entity: str, asked: Mapping[str, str], body: Any, returned: int
    ) -> Mapping[str, str] | None:
        """The page after this one, or None when the envelope or a short page says it was last."""
        _assert_entity(entity, ZONE, DNS_RECORD)
        if returned < int(asked["per_page"]) or not isinstance(body, Mapping) or last_page(body):
            return None
        return MappingProxyType({**asked, "page": str(int(asked["page"]) + 1)})

    def call_headers(self, settings: Mapping[str, str]) -> Mapping[str, str]:
        # Built for its refusal of settings that name no account; it adds no header.
        CloudflareConnection.from_settings(settings)
        return MappingProxyType({})

    def interpret(
        self, operation: RestOperation, *, status: int, body: Any, fetched_at: str
    ) -> PageReply:
        return interpret(operation, status=status, body=body, fetched_at=fetched_at)

    def retry_after(self, headers: Mapping[str, str]) -> float | None:
        return retry_after(headers)

    def allowance_spent(self, headers: Mapping[str, str]) -> bool:
        return allowance_spent(headers)

    def projected(
        self, entity: str, row: Mapping[str, Any], *, seen_at: datetime
    ) -> ProjectedRecord | None:
        """One zone's or one record's index entry, built from the declared names.

        None for a row with no id. A record's id is already its zone's and its own, as the walk
        named it (`DNS_RECORD_LISTING`), and it is refused here if it is not.
        """
        _assert_entity(entity, ZONE, DNS_RECORD)
        raw_id = row.get("id")
        if not isinstance(raw_id, str) or not raw_id.strip():
            return None
        if entity == DNS_RECORD:
            DNS_RECORD_LISTING.split(raw_id)
        return ProjectedRecord(
            source=CLOUDFLARE,
            entity=entity,
            source_id=raw_id,
            last_seen_at=seen_at,
            fields=kept_fields_of(entity, row),
        )


def _assert_entity(entity: str, *allowed: str) -> None:
    if entity not in allowed:
        msg = f"this reading keeps {list(allowed)} and was asked for {entity!r}"
        raise ConnectorContractError(msg)


# ------------------------------------------------------------------ reading one record live
class CloudflareLiveLookup:
    """One zone, or one DNS record with its values, read while somebody waits (M11.9.2).

    The service's credentials, declared: a connection holds one token for the account.
    """

    def entities(self) -> tuple[str, ...]:
        return (ZONE, DNS_RECORD)

    def identity_mode(self, entity: str) -> IdentityMode:
        del entity
        return IdentityMode.SERVICE

    def arguments_for(self, entity: str, source_id: str) -> Mapping[str, str]:
        """The one-record call's arguments: a zone's id, or a record's zone and its own id.

        Every id laid into Cloudflare's path is refused unless it is 32 hex digits, the zone half
        of a record's index id as much as its own, because either could otherwise name another
        address.
        """
        _assert_entity(entity, ZONE, DNS_RECORD)
        if entity == ZONE:
            return MappingProxyType({ZONE_PARAMETER: _identifier(source_id)})
        zone_id, record_id = DNS_RECORD_LISTING.split(source_id)
        return MappingProxyType(
            {ZONE_PARAMETER: _identifier(zone_id), "dns_record_id": _identifier(record_id)}
        )

    def operation(
        self, entity: str, *, settings: Mapping[str, str], resolver: Resolver
    ) -> RestOperation | None:
        del resolver  # checked when the address is prepared
        CloudflareConnection.from_settings(settings)
        if entity == ZONE:
            return zone_operation()
        _assert_entity(entity, DNS_RECORD)
        return dns_record_operation()


def _identifier(given: str) -> str:
    """A Cloudflare id, refused unless it is 32 hex digits. See `CloudflareLiveLookup`."""
    if not IDENTIFIER_RE.fullmatch(given):
        msg = (
            "an id laid into Cloudflare's address is 32 hex digits, and this one is not; it is "
            "refused rather than escaped"
        )
        raise ConnectorContractError(msg)
    return given


# ------------------------------------------------------------------ security events, live
class SecurityWindow(enum.StrEnum):
    """The windows a question may name. See `A_WINDOW_IS_NAMED_FROM_A_CLOSED_LIST`."""

    PAST_HOUR = "past_hour"
    PAST_24_HOURS = "past_24_hours"


#: How long each window is, ending at the moment of the question.
WINDOW_LENGTH: Final[Mapping[SecurityWindow, timedelta]] = MappingProxyType(
    {SecurityWindow.PAST_HOUR: timedelta(hours=1), SecurityWindow.PAST_24_HOURS: timedelta(days=1)}
)

#: The most events one question is told, newest first.
SECURITY_EVENTS_LIMIT: Final = 100

#: What an event is read as: our name for each field, and Cloudflare's. No visitor's address and no
#: user agent: see `A_SECURITY_EVENT_IS_READ_WITHOUT_ITS_VISITOR`.
SECURITY_EVENT_FIELDS: Final[tuple[tuple[str, str], ...]] = (
    ("id", "rayName"),
    ("action", "action"),
    ("country", "clientCountryName"),
    ("host", "clientRequestHTTPHost"),
    ("path", "clientRequestPath"),
    ("occurred_at", "datetime"),
    ("rule_id", "ruleId"),
    ("detected_by", "source"),
)

#: The query, from Cloudflare's own tutorial for `firewallEventsAdaptive`, naming only the fields
#: above (https://developers.cloudflare.com/analytics/graphql-api/tutorials/querying-firewall-events/).
SECURITY_EVENTS_QUERY: Final = (
    "query SecurityEvents($zoneTag: string, $filter: FirewallEventsAdaptiveFilter_InputObject) "
    "{ viewer { zones(filter: { zoneTag: $zoneTag }) { firewallEventsAdaptive(filter: $filter, "
    f"limit: {SECURITY_EVENTS_LIMIT}, orderBy: [datetime_DESC]) "
    "{ " + " ".join(source for _, source in SECURITY_EVENT_FIELDS) + " } } } }"
)


@dataclass(frozen=True)
class SecurityEventsRequest:
    """The one POST that reads a zone's events for a window. Holds no key."""

    url: str
    body: Mapping[str, Any]


def security_events_request(zone_id: str, window: str, *, now: datetime) -> SecurityEventsRequest:
    """The query for one zone's events over a named window ending at `now`.

    Refuses a window not on the list, a zone id that is not one, and a `now` with no zone.
    """
    try:
        named = SecurityWindow(window)
    except ValueError as exc:
        msg = (
            f"{window!r} is not a window this connector reads. "
            f"{A_WINDOW_IS_NAMED_FROM_A_CLOSED_LIST}"
        )
        raise ConnectorContractError(msg) from exc
    if not IDENTIFIER_RE.fullmatch(zone_id):
        msg = "a zone id is 32 hex digits, and this one is not; it is refused rather than escaped"
        raise ConnectorContractError(msg)
    if now.tzinfo is None:
        msg = "a window's end needs a time zone, or it is a different instant on every server"
        raise ConnectorContractError(msg)
    since = now - WINDOW_LENGTH[named]
    return SecurityEventsRequest(
        url=f"{API_BASE}{GRAPHQL_PATH}",
        body=MappingProxyType(
            {
                "query": SECURITY_EVENTS_QUERY,
                "variables": {
                    "zoneTag": zone_id,
                    "filter": {"datetime_geq": since.isoformat(), "datetime_leq": now.isoformat()},
                },
            }
        ),
    )


def security_events(status: int, body: Any, *, fetched_at: str) -> PageReply:
    """One GraphQL answer as security events, or the reason it is not one.

    GraphQL refuses inside a 200: a reply carrying `errors` (a window the plan does not keep, a
    permission the token lacks) is a refusal, and so is a reply naming no zone, which is a zone the
    token does not reach. Only a zone's list of events is an answer, an empty one included.
    """
    call = classify(status=status)
    if call is not CallOutcome.OK:
        return PageReply(call=call, rows=None)
    if not isinstance(body, Mapping) or body.get("errors"):
        return PageReply(call=CallOutcome.REJECTED, rows=None)
    zones = _at(body, "data", "viewer", "zones")
    if not isinstance(zones, list) or not zones or not isinstance(zones[0], Mapping):
        return PageReply(call=CallOutcome.REJECTED, rows=None)
    events = zones[0].get("firewallEventsAdaptive")
    if not isinstance(events, list):
        raise CloudflareEnvelopeError(AN_ENVELOPE_THAT_SAYS_IT_FAILED_IS_NOT_AN_EMPTY_PAGE)
    rows = tuple(
        {ours: event[theirs] for ours, theirs in SECURITY_EVENT_FIELDS if theirs in event}
        for event in events
        if isinstance(event, Mapping)
    )
    return PageReply(
        call=call,
        rows=normalise(
            SECURITY_EVENT,
            rows,
            source=SPEC_REF,
            fetched_at=fetched_at,
            truncated=len(events) >= SECURITY_EVENTS_LIMIT,
        ),
    )


def _at(body: Mapping[str, Any], *steps: str) -> Any:
    found: Any = body
    for step in steps:
        if not isinstance(found, Mapping):
            return None
        found = found.get(step)
    return found


# ------------------------------------------------------------- a DNS change, prepared only
#: The record types a change may be prepared for, each with a content this module can check.
CHANGEABLE_TYPES: Final = frozenset({"A", "AAAA", "CNAME", "TXT"})

#: A host name, as a CNAME's content and a record's name are written.
HOSTNAME_RE: Final = re.compile(
    r"(?=.{1,253}$)(?:[A-Za-z0-9_](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
)

#: The longest TXT content Cloudflare takes in one record.
MAX_TXT_CHARS: Final = 2048

#: What a person must hold, in the record's department, to prepare or approve a change.
DNS_CHANGE_CAPABILITY: Final = f"write:{DNS_RECORD}"

#: The change as the gate governs it. **A write, and one of the owner's sensitive effects**, so
#: `brain.tools.registry.default_rung` suggests Assisted and `brain.gate.leash.effective_tier` caps
#: it there whatever the leash says: it is suspended for a person, or simulated, and never run.
DNS_CHANGE_TOOL: Final = ToolDefinition(
    name="cloudflare.change_dns_record",
    description=(
        "Prepare a change to one DNS record's content, for a person to approve. Nothing is "
        "changed in Cloudflare by preparing it."
    ),
    entity=DNS_RECORD,
    required_capability=DNS_CHANGE_CAPABILITY,
    side_effect=SideEffect.WRITE,
    identity_mode=IdentityMode.SERVICE,
    source=CLOUDFLARE,
    sensitive=True,
)


#: The shortest and longest time to live Cloudflare takes, and the one meaning "automatic".
MIN_TTL: Final = 60
MAX_TTL: Final = 86_400
AUTOMATIC_TTL: Final = 1

#: The record types Cloudflare can proxy.
PROXIABLE_TYPES: Final = frozenset({"A", "AAAA", "CNAME"})


@dataclass(frozen=True)
class DnsChange:
    """One record's new values, checked against its type before anything is prepared.

    `record` is the id the index keeps, the zone's and the record's own, so a change names exactly
    the record a question found. `ttl` and `proxied` are changed only when given: a change that
    leaves them as they are neither sends nor reads them back.
    """

    record: str
    name: str
    record_type: str
    content: str
    ttl: int | None = None
    proxied: bool | None = None

    def __post_init__(self) -> None:
        for one in DNS_RECORD_LISTING.split(self.record):
            if not IDENTIFIER_RE.fullmatch(one):
                msg = "a DNS record is named by its zone's id and its own, each 32 hex digits"
                raise ConnectorContractError(msg)
        if not HOSTNAME_RE.fullmatch(self.name):
            msg = "a DNS record's name is a host name"
            raise ConnectorContractError(msg)
        if self.record_type not in CHANGEABLE_TYPES:
            msg = (
                f"a change is prepared for {sorted(CHANGEABLE_TYPES)} records only, whose content "
                "this connector can check before a person is asked to approve it"
            )
            raise ConnectorContractError(msg)
        if not content_fits(self.record_type, self.content):
            msg = f"that content is not a {self.record_type} record's"
            raise ConnectorContractError(msg)
        if self.ttl is not None and not (
            self.ttl == AUTOMATIC_TTL or MIN_TTL <= self.ttl <= MAX_TTL
        ):
            msg = f"a time to live is {AUTOMATIC_TTL} for automatic or {MIN_TTL} to {MAX_TTL}"
            raise ConnectorContractError(msg)
        if self.proxied is not None and self.record_type not in PROXIABLE_TYPES:
            msg = f"only {sorted(PROXIABLE_TYPES)} records can be proxied"
            raise ConnectorContractError(msg)

    @property
    def zone_id(self) -> str:
        return DNS_RECORD_LISTING.split(self.record)[0]

    @property
    def record_id(self) -> str:
        return DNS_RECORD_LISTING.split(self.record)[1]

    def values(self) -> dict[str, str | int | bool]:
        """Every field this change sets, in Cloudflare's names and types: sent, then checked."""
        values: dict[str, str | int | bool] = {
            "name": self.name,
            "type": self.record_type,
            "content": self.content,
        }
        if self.ttl is not None:
            values["ttl"] = self.ttl
        if self.proxied is not None:
            values["proxied"] = self.proxied
        return values


def content_fits(record_type: str, content: str) -> bool:
    """Whether `content` is a value a record of this type may hold."""
    match record_type:
        case "A":
            return _address(content, ipaddress.IPv4Address)
        case "AAAA":
            return _address(content, ipaddress.IPv6Address)
        case "CNAME":
            return HOSTNAME_RE.fullmatch(content) is not None
        case "TXT":
            return 0 < len(content) <= MAX_TXT_CHARS and content.isprintable()
        case _:
            return False


def _address(content: str, kind: type[ipaddress.IPv4Address | ipaddress.IPv6Address]) -> bool:
    try:
        kind(content)
    except ValueError:
        return False
    return True


def _said(value: str | int | bool) -> str:
    """One value as the artefact and the digest carry it: a boolean as `true` or `false`."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def prepare_dns_change(change: DnsChange, *, agent_id: str, department: str) -> Action:
    """The action a person approves: this record, in this department, to these values (M11.7.3).

    The record's name and type travel with the new content, so the artefact an approver reads says
    which record changes and to what, and the row carries the record's index id and the department
    the approver's grant is matched against. Nothing read live is in it: the values are the ones
    asked for, not the ones Cloudflare holds.
    """
    if not SLUG_RE.fullmatch(department):
        msg = "a department's short name is what an approver's grant is matched against"
        raise ConnectorContractError(msg)
    args = {name: _said(value) for name, value in change.values().items()}
    return Action(
        agent_id=agent_id,
        tool=DNS_CHANGE_TOOL,
        target=DNS_RECORD,
        touched_fields=tuple(args),
        row={
            DEPARTMENT_SETTING: department,
            ZONE_PARAMETER: change.zone_id,
            RECORD_KEY: change.record,
            **args,
        },
        args=args,
    )


def dns_change_of(action: Action) -> DnsChange:
    """The change an approved action names, rebuilt from the action and checked again.

    Refused for an action that is not this connector's change, so a write key is never handed an
    action it was not granted for.
    """
    if action.tool.name != DNS_CHANGE_TOOL.name:
        msg = f"{action.tool.name!r} is not a DNS change"
        raise ConnectorContractError(msg)
    args = action.args
    ttl = args.get("ttl")
    proxied = args.get("proxied")
    if proxied not in (None, "true", "false"):
        msg = "a change's proxying is true or false"
        raise ConnectorContractError(msg)
    return DnsChange(
        record=action.row.get(RECORD_KEY, ""),
        name=args.get("name", ""),
        record_type=args.get("type", ""),
        content=args.get("content", ""),
        ttl=None if ttl is None else int(ttl),
        proxied=None if proxied is None else proxied == "true",
    )


def dns_change_operation() -> RestOperation:
    """The one-record PATCH, reading its reply with the live mapping."""
    return _operation(PATCH_DNS_RECORD, DNS_RECORD, DNS_LIVE_MAPPING)


class DnsChangeWrites:
    """How an approved DNS change is sent and how the record read back is judged (M11.7.3).

    The body is exactly the fields the change set, and the judgement compares exactly those: a
    change that did not set the time to live does not fail because Cloudflare's is automatic.
    """

    def call_for(self, action: Action) -> WriteCall:
        change = dns_change_of(action)
        return WriteCall(
            operation=dns_change_operation(),
            arguments=MappingProxyType(
                {ZONE_PARAMETER: change.zone_id, "dns_record_id": change.record_id}
            ),
            body=MappingProxyType(change.values()),
            entity=DNS_RECORD,
            source_id=change.record,
        )

    def differs(self, action: Action, found: Mapping[str, Any]) -> tuple[str, ...]:
        wanted = dns_change_of(action).values()
        return tuple(
            sorted(
                name
                for name, value in wanted.items()
                if _said_or_none(found.get(name)) != _said(value)
            )
        )


def _said_or_none(value: object) -> str | None:
    if isinstance(value, str | int | bool):
        return _said(value)
    return None


#: What an approver of a DNS change is told on an install that has not given the write key.
THIS_INSTALL_HAS_NOT_ALLOWED_DNS_CHANGES: Final = (
    "Approving this changes nothing in Cloudflare: this install has not allowed DNS changes. An "
    "administrator allows them on the Cloudflare source's page with a token that can edit DNS."
)

#: The permission the write key is created with, in the dashboard's own words.
EDIT_PERMISSION: Final = "DNS Edit"

#: The grant that lets an approved DNS change be sent. Off until its key is given.
DNS_CHANGES: Final = WriteGrant(
    name="dns_changes",
    label="Allow approved DNS changes",
    tools=(DNS_CHANGE_TOOL.name,),
    credential_label="A second Cloudflare API token that can edit DNS",
    credential_hint=(
        "Create a second custom token in Cloudflare (My Profile, API Tokens, Create Token) with "
        "one permission, DNS Edit (Zone, DNS, Edit, listed as DNS Write in Cloudflare's permission "
        "reference), over all zones from the same account and nothing else. It is kept in a vault "
        "slot of its own, apart from the read token, and used only to send a DNS change a person "
        "in the zones' department approved, which is then read back before it is reported done. "
        "Never Zone Edit, any Account permission or the Global API Key."
    ),
    not_allowed=THIS_INSTALL_HAS_NOT_ALLOWED_DNS_CHANGES,
    prepares=DnsChangeWrites(),
)


# ------------------------------------------------------------------ what this connector declares
#: Why an answered Cloudflare list page is a complete look.
CLOUDFLARE_ABSENCE_IS_THE_LAST_PAGE: Final = (
    "A Cloudflare list page says in result_info which page it is and how many there are, so an "
    "answered page with no rows that is also the last page is a complete empty reading, and one "
    "that is not the last proves nothing absent. A one-record reply, a GraphQL answer and an "
    "envelope that does not say success are not a listing, and read as unreadable."
)


def read_back_reading(operation: RestOperation, *, status: int, body: Any) -> Reading:
    """One reply read as a listing: found, absent only when it was the last page, else not known."""
    call = classify(status=status)
    if call is not CallOutcome.OK:
        return Reading(outcome=call, matched=0, complete=False)
    try:
        envelope = answered(body)
        rows = operation.project(envelope)
    except ConnectorContractError:
        return unreadable()
    return Reading(outcome=CallOutcome.OK, matched=len(rows), complete=last_page(envelope))


#: The screens an administrator connects Cloudflare through, the form last.
GUIDE: Final = keyed(
    (
        GuideStep(
            key="token",
            title="Create a token that can only read",
            text=(
                "In the Cloudflare dashboard open My Profile, then API Tokens, press Create Token "
                "and start a custom token. Give it exactly three permissions: Zone Read, DNS Read "
                "and Analytics Read. Nothing marked Edit or Write: this system never changes DNS "
                "with this token, and a change is only ever prepared for a person to approve."
            ),
            sketch=Sketch(
                place="Cloudflare dashboard",
                heading="Create Custom Token",
                lines=(
                    SketchLine(LineKind.ITEM, "Zone Read", mark=True),
                    SketchLine(LineKind.ITEM, "DNS Read", mark=True),
                    SketchLine(LineKind.ITEM, "Analytics Read", mark=True),
                    SketchLine(LineKind.TEXT, "Nothing marked Edit or Write"),
                ),
                button="Continue to summary",
            ),
            link=API_TOKENS_URL,
            link_label="Open API Tokens in Cloudflare",
        ),
        GuideStep(
            key="account",
            title="Limit it to the one account, then copy the token",
            text=(
                "Under Zone Resources choose Include, All zones from an account, and the one "
                "account this system reads. Press Continue to summary, then Create Token, and "
                "copy the token: Cloudflare shows it only once. The account's id is on that "
                "account's Overview page, under Account ID."
            ),
            sketch=Sketch(
                place="Cloudflare dashboard",
                heading="Zone Resources",
                lines=(
                    SketchLine(LineKind.ITEM, "All zones from an account", mark=True),
                    SketchLine(LineKind.FIELD, "Account ID", "0123456789abcdef", mark=True),
                ),
                button="Create Token",
            ),
        ),
        GuideStep(
            key="connect",
            title="Paste the account id, the department and the token here",
            text=(
                "Type the account's id, the short name of the one department whose people may be "
                "granted its zones and records, and paste the token, then press Connect "
                "Cloudflare. The token is kept in the vault and only ever sent to Cloudflare."
            ),
            sketch=Sketch(
                place="Company Brain",
                heading="Connect Cloudflare",
                lines=(
                    SketchLine(LineKind.FIELD, "Account ID", "0123456789abcdef", mark=True),
                    SketchLine(LineKind.FIELD, "Department", "operations", mark=True),
                    SketchLine(LineKind.FIELD, "API token", "********", mark=True),
                ),
                button="Connect Cloudflare",
            ),
            asks=(ACCOUNT_SETTING, DEPARTMENT_SETTING, "credential"),
        ),
    )
)


CONNECTOR: Final = ConnectorDeclaration(
    name=CLOUDFLARE,
    label="Cloudflare",
    guide=GUIDE,
    console=ConsoleForm(
        settings=(
            Setting(
                name=ACCOUNT_SETTING,
                label="Account ID",
                hint=(
                    "The 32-character id of the one Cloudflare account this system reads, from "
                    "that account's Overview page under Account ID."
                ),
                refused=(
                    "That is not a Cloudflare account id. Copy the 32 letters and digits shown "
                    "under Account ID on the account's Overview page."
                ),
            ),
            Setting(
                name=DEPARTMENT_SETTING,
                label="Department that reads its zones",
                hint=(
                    "The short name of the one department whose people may be granted this "
                    "account's zones and DNS records, as the Departments page shows it. "
                    "Everybody else, whatever they hold, is not shown them."
                ),
                refused=(
                    "That is not a department's short name. Use lower-case letters, digits and "
                    "underscores, exactly as the Departments page shows it."
                ),
            ),
        ),
        credential_label="A Cloudflare API token that can only read",
        credential_hint=(
            "Create a custom API token in Cloudflare (My Profile, API Tokens, Create Token) with "
            "three permissions and nothing else: Zone Read, DNS Read and Analytics Read, over all "
            "zones from the one account this system reads. Never a token with DNS Write or any "
            "Edit permission, and never the Global API Key: DNS is only ever changed through a "
            "change a person approves, never with this token. Paste it as one piece. It is kept "
            "in the vault and never shown again."
        ),
        build=built_from_the_console,
    ),
    read_back=ReadBack(
        reading=read_back_reading,
        recorded=(
            "CF-200-zones",
            "CF-200-zones-full-page",
            "CF-200-zone",
            "CF-200-dns-records",
            "CF-200-dns-records-empty",
            "CF-200-dns-record",
            "CF-200-security-events",
            "CF-200-graphql-errors",
            "CF-429",
            "CF-403",
        ),
        findings=(CLOUDFLARE_ABSENCE_IS_THE_LAST_PAGE,),
    ),
    recorded=Recorded(tested=True),
    reading=CloudflareReading(),
    live=CloudflareLiveLookup(),
    writes=(DNS_CHANGES,),
)
