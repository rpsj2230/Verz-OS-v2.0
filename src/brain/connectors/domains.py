"""Domains and hosting: each client domain's registrar, expiry and hosting status, from the source.

An agency keeps its clients' domains in a spreadsheet, and the spreadsheet is wrong the day a
client renews somewhere else. The source for who registered a domain and until when is the
domain's own registry, which publishes it in RDAP (RFC 9083, the successor to WHOIS); the source
for whether a site is hosted and answering is the site. So this connector asks those two and
nothing else, and an expiry question is answered from the registry rather than from a copy
somebody typed.

**This connector keeps a minimal index and reads every value live.** What it keeps of a domain is
its name, when its registry says it expires and its registration status (`FIELDS`), so a
question can find the domain and ask which ones lapse this month; who registered it, its name
servers and whether its site answers are read live when a question needs them and are never
stored. See `brain.connectors.declaration.CONNECTORS_NEVER_BULK_SYNC`.

**Only the connection's own list is ever looked up.** A connection names the domains an agency
looks after, and the reading, the live read and the site check all refuse a domain that is not
on it, so this install cannot be used as a free RDAP or WHOIS client by asking about somebody
else's domain. A domain nobody listed is simply not there to be asked about. See
`ONLY_THE_CONNECTIONS_OWN_DOMAINS_ARE_LOOKED_UP`.

**Each domain is read from the server its registry publishes.** Registries publish RDAP at their
own addresses, found from IANA's bootstrap list (`brain.connectors.rdap_servers`), so this is a
routed reading: one page a domain, each page's operation at that domain's registry
(`brain.connectors.declaration.RoutedReading`). **A registry that publishes no RDAP is said so,
for that domain** (several country domains publish none), in the index and in the answer, and
the domain is never sent anywhere else to be looked up. See
`A_REGISTRY_THAT_PUBLISHES_NO_RDAP_IS_SAID_SO`.

**No key.** A registry's RDAP record is published to anybody who asks, and a site answers anybody,
so the connection keeps nothing in the vault, the worker takes no lease and no `Authorization` is
sent (`KeyScheme.NONE`, `CredentialShape.NONE`). The department a connection names is who may be
granted what it holds, as Freshdesk's is.

**Hosting status is what the domain's own site answers**, asked over HTTPS through the same
address rule every call from this install passes: it answers, it answers with a server error,
it does not answer, or its name resolves to nothing. It is read live, because a site that went
down an hour ago is the point of asking. See `HOSTING_IS_WHAT_THE_SITE_ITSELF_ANSWERS`.

Rejected: a registrar's or a host's own API (auto-renew, a suspended hosting account). Each is one
vendor's, needs one vendor's key, and covers only the domains held there; RDAP covers every
registrar. An agency that wants its registrar's account status connects that registrar as a
connector of its own. Rejected: a lookup through a public RDAP redirector. It is a third party
deciding where each question goes, and the worker never follows a redirect anyway.

Not done: a domain its registry no longer holds (an expired and deleted name answers 404) is
refused as a failed read rather than said to be unregistered; and the site check says nothing of
its certificate's expiry, which the caller does not expose.

Task ids: M11.7.4
"""

from __future__ import annotations

import re
import secrets
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final, Self

from brain.connectors.ask import AskEntity, AskRows, each_behind_its_own
from brain.connectors.contract import (
    AccessMode,
    ConnectorContractError,
    ConnectorScope,
    CredentialBinding,
    TransportKind,
    assert_holds_no_credential,
)
from brain.connectors.declaration import (
    ConnectExample,
    ConnectorDeclaration,
    ConsoleForm,
    CredentialShape,
    KeyScheme,
    OneCall,
    PageReply,
    Recorded,
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
from brain.connectors.rdap_servers import server_for
from brain.connectors.rest import ID_TARGET, OperationSpec, ParameterSpec, RestOperation
from brain.connectors.throttle import CallOutcome, classify
from brain.connectors.transports import FieldMapping, RestTransport, SourceRecord, normalise
from brain.connectors.write_verification import ReadBack, Reading, unreadable
from brain.core.department import SLUG_RE
from brain.core.envelope import IdentityMode, TypedResult
from brain.core.scope import Scope
from brain.ops.connect_steps import GuideStep, LineKind, Sketch, SketchLine, keyed
from brain.ops.limits import ConnectorLimit
from brain.ops.secrets import SecretRef
from brain.tools.fetch import Resolver, UnsafeAddressError, assert_fetchable

# ------------------------------------------------------------------ written-down reasons

#: Why a domain nobody listed is never looked up.
ONLY_THE_CONNECTIONS_OWN_DOMAINS_ARE_LOOKED_UP: Final = (
    "A connection names the domains an agency looks after, and nothing else is ever sent to a "
    "registry or a site: the reading walks that list, and the live read and the site check refuse "
    "a domain not on it. Otherwise asking about any domain would make this install a free RDAP "
    "or WHOIS client for whoever may ask a question."
)

#: What is said of a domain whose registry publishes no RDAP.
A_REGISTRY_THAT_PUBLISHES_NO_RDAP_IS_SAID_SO: Final = (
    "Some registries, several country domains among them, publish no RDAP record. Such a domain "
    "is kept in the index as unpublished and its expiry and registrar are answered as not "
    "published by its registry, for that domain, rather than as a source that could not be "
    "reached, and it is never looked up anywhere else."
)

#: What hosting status means here.
HOSTING_IS_WHAT_THE_SITE_ITSELF_ANSWERS: Final = (
    "Whether a domain's site is hosted and answering is asked of the site, over HTTPS, through "
    "the address rule every call from this install passes. It is read when a question asks, "
    "because a site that went down an hour ago is the point of asking, and it is kept nowhere."
)

# ------------------------------------------------------------------------ the figures
CONNECTOR_NAME: Final = "domains"
DOMAIN: Final = "domain"
VERSION: Final = "1.0.0"

#: The specification this reads: RDAP's domain lookup, RFC 9083 over RFC 7480.
SPEC_REF: Final = "rdap.rfc9083"

#: How often the index is read again. An expiry moves at renewal, a few times a year.
READING_INTERVAL: Final = timedelta(days=1)

#: The most domains one connection may name. An agency's book, and one day's reading of it.
MAX_DOMAINS: Final = 200

#: How long the domains setting may be: `MAX_DOMAINS` names of about thirty characters each.
DOMAINS_CHARS: Final = 8000

#: The registration status kept for a domain whose registry publishes no RDAP.
UNPUBLISHED: Final = "unpublished"

#: What a live read says of a value a registry does not publish.
NOT_PUBLISHED: Final = "not published by its registry, which offers no RDAP record"

#: The most of a site's answer read to judge it. Its status is the finding, never its page.
SITE_BYTES: Final = 4096

DOMAINS_SETTING: Final = "domains"
DEPARTMENT_SETTING: Final = "department"

_LABEL: Final = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_DOMAIN_RE: Final = re.compile(rf"^(?:{_LABEL}\.)+(?:[a-z]{{2,63}}|xn--[a-z0-9-]{{1,59}})$")
_SEPARATORS: Final = re.compile(r"[\s,;]+")


class DomainsError(ConnectorContractError):
    """A domain or a reply this connector will not read, said in words that name no value."""


# --------------------------------------------------------------------- the connection
def domains_of(text: str) -> tuple[str, ...]:
    """The domains a setting lists, lower-cased, without a trailing dot, each once, in order."""
    found: dict[str, None] = {}
    for one in _SEPARATORS.split(text.strip()):
        name = one.strip().lower().rstrip(".")
        if name:
            found[name] = None
    return tuple(found)


@dataclass(frozen=True)
class DomainsConnection:
    """The domains a connection looks after and the department that may be granted them."""

    domains: tuple[str, ...]
    department: str

    def __post_init__(self) -> None:
        assert_holds_no_credential(type(self))
        if not self.domains or len(self.domains) > MAX_DOMAINS:
            msg = f"a connection names between one and {MAX_DOMAINS} domains"
            raise SettingRefusedError(msg, setting=DOMAINS_SETTING)
        if any(not _DOMAIN_RE.fullmatch(one) for one in self.domains):
            msg = "a listed name is not a domain name"
            raise SettingRefusedError(msg, setting=DOMAINS_SETTING)
        if not SLUG_RE.fullmatch(self.department):
            msg = "the department is not a department's short name"
            raise SettingRefusedError(msg, setting=DEPARTMENT_SETTING)
        self.scope()

    @classmethod
    def from_settings(cls, settings: Mapping[str, str]) -> Self:
        return cls(
            domains=domains_of(settings.get(DOMAINS_SETTING, "")),
            department=settings.get(DEPARTMENT_SETTING, "").strip(),
        )

    def scope(self) -> ConnectorScope:
        """What this connection may look up: these domains, named, and no others."""
        return ConnectorScope(resource_kind="domain", selectors=self.domains)

    def visibility(self) -> Scope:
        """Who may be granted what it keeps: the department the connection names."""
        return Scope.department(self.department)

    def listed(self, domain: str) -> bool:
        """Whether a domain is on this connection's list. See the module docstring."""
        return self.scope().admits(domain.lower())

    def routed(self) -> tuple[str, ...]:
        """The listed domains whose registry publishes RDAP, in the list's order."""
        return tuple(one for one in self.domains if server_for(one) is not None)

    def unrouted(self) -> tuple[str, ...]:
        """The listed domains whose registry publishes none."""
        return tuple(one for one in self.domains if server_for(one) is None)


# ---------------------------------------------------------------- the registry's record
DOMAIN_OPERATION: Final = OperationSpec(
    operation_id="rdap_domain",
    method="get",
    path="/domain/{name}",
    parameters=(ParameterSpec(name="name", location="path", required=True),),
    returns_list=False,
)

TRANSPORT: Final = RestTransport(
    spec_ref=SPEC_REF,
    operation=DOMAIN_OPERATION.operation_id,
    entity=DOMAIN,
    fields=(FieldMapping(target=ID_TARGET, source_path="ldhName"),),
)

#: What the index keeps of a domain. Three of the twelve.
FIELDS: Final[tuple[ProjectedField, ...]] = (
    ProjectedField(name="name", shape=FieldShape.LABEL, uses=(HotUse.IDENTIFY,)),
    ProjectedField(name="expiry", shape=FieldShape.TIMESTAMP, uses=(HotUse.FILTER, HotUse.SORT)),
    ProjectedField(
        name="registration", shape=FieldShape.STATUS, uses=(HotUse.FILTER, HotUse.COUNT)
    ),
)

#: What a live read adds, and is never kept.
LIVE_ONLY: Final[tuple[str, ...]] = ("registrar", "nameservers", "hosting")

#: RDAP's statuses (RFC 8056) that say a domain does not resolve, or is going, by the word kept.
_HELD: Final = frozenset({"client hold", "server hold"})
_GOING: Final = frozenset({"pending delete", "redemption period"})


def operation_at(base_url: str) -> RestOperation:
    """The domain lookup at one registry's RDAP base address."""
    return RestOperation(base_url=base_url, operation=DOMAIN_OPERATION, transport=TRANSPORT)


def registration_of(statuses: Sequence[str]) -> str:
    """One word for a domain's registration, from its RDAP statuses. Active unless they say not."""
    said = {one.strip().lower() for one in statuses}
    if said & _HELD:
        return "on_hold"
    if said & _GOING:
        return "pending_delete"
    if "inactive" in said:
        return "inactive"
    return "active"


def _expiry(events: Any) -> str | None:
    for event in events if isinstance(events, list) else ():
        if isinstance(event, Mapping) and event.get("eventAction") == "expiration":
            stated = event.get("eventDate")
            if isinstance(stated, str):
                try:
                    at = datetime.fromisoformat(stated.replace("Z", "+00:00"))
                except ValueError:
                    return None
                return at.astimezone(UTC).isoformat()
    return None


def _registrar(entities: Any) -> str | None:
    for entity in entities if isinstance(entities, list) else ():
        if not isinstance(entity, Mapping) or "registrar" not in (entity.get("roles") or ()):
            continue
        card = entity.get("vcardArray")
        lines = card[1] if isinstance(card, list) and len(card) > 1 else ()
        for line in lines if isinstance(lines, list) else ():
            if isinstance(line, list) and len(line) > 3 and line[0] == "fn":
                return str(line[3])
    return None


def record_of(body: Any) -> dict[str, Any]:
    """One registry reply as the fields this connector reads, and nothing else it sent."""
    if not isinstance(body, Mapping) or not isinstance(body.get("ldhName"), str):
        msg = "an RDAP reply names no domain"
        raise DomainsError(msg)
    name = str(body["ldhName"]).lower().rstrip(".")
    statuses = body.get("status")
    servers = body.get("nameservers")
    row: dict[str, Any] = {
        "id": name,
        "name": name,
        "registration": registration_of(
            [str(one) for one in statuses] if isinstance(statuses, list) else ()
        ),
        "nameservers": ", ".join(
            sorted(
                str(one.get("ldhName", "")).lower()
                for one in (servers if isinstance(servers, list) else ())
                if isinstance(one, Mapping) and one.get("ldhName")
            )
        ),
    }
    expiry, registrar = _expiry(body.get("events")), _registrar(body.get("entities"))
    if expiry is not None:
        row["expiry"] = expiry
    if registrar is not None:
        row["registrar"] = registrar
    return row


def projected_fields(row: Mapping[str, Any]) -> dict[str, ProjectedValue]:
    """The index fields of one record, built from the declared names and never copied."""
    return {one.name: row[one.name] for one in FIELDS if row.get(one.name) is not None}


def _unpublished_row(name: str) -> dict[str, Any]:
    return {
        "id": name,
        "name": name,
        "registration": UNPUBLISHED,
        "expiry": NOT_PUBLISHED,
        "registrar": NOT_PUBLISHED,
    }


# ------------------------------------------------------------------------ the reading
class DomainsReading:
    """The listed domains, one page each at its registry, into the minimal index and no more."""

    def entities(self) -> tuple[str, ...]:
        return (DOMAIN,)

    def refresh_interval(self) -> timedelta:
        return READING_INTERVAL

    def operation(
        self, entity: str, *, settings: Mapping[str, str], resolver: Resolver
    ) -> RestOperation:
        """The first routed domain's lookup, for a caller that asks a reading for one operation."""
        first = self.first_route(entity, settings=settings)
        if first is None:
            msg = "no listed domain's registry publishes RDAP"
            raise DomainsError(msg)
        return self.operation_for(entity, first, settings=settings, resolver=resolver)

    def key_scheme(self) -> KeyScheme:
        return KeyScheme.NONE

    def first_page(self, entity: str) -> Mapping[str, str]:
        del entity
        msg = "a domains reading's pages are its connection's own list: ask first_route"
        raise DomainsError(msg)

    def next_page(
        self, entity: str, asked: Mapping[str, str], body: Any, returned: int
    ) -> Mapping[str, str] | None:
        del entity, asked, body, returned
        return None

    def call_headers(self, settings: Mapping[str, str]) -> Mapping[str, str]:
        # Built for its refusal of a list that is not domains; it adds no header.
        DomainsConnection.from_settings(settings)
        return {}

    def interpret(
        self, operation: RestOperation, *, status: int, body: Any, fetched_at: str
    ) -> PageReply:
        del operation
        call = classify(status=status)
        if call is not CallOutcome.OK:
            return PageReply(call=call, rows=None)
        return PageReply(
            call=call,
            rows=normalise(DOMAIN, (record_of(body),), source=SPEC_REF, fetched_at=fetched_at),
        )

    def retry_after(self, headers: Mapping[str, str]) -> float | None:
        stated = {key.lower(): value for key, value in headers.items()}.get("retry-after", "")
        return float(stated) if stated.strip().isdigit() else None

    def allowance_spent(self, headers: Mapping[str, str]) -> bool:
        del headers
        return False

    def projected(
        self, entity: str, row: Mapping[str, Any], *, seen_at: datetime
    ) -> ProjectedRecord | None:
        self._assert_domain(entity)
        name = row.get("id")
        if not isinstance(name, str) or not name:
            return None
        return ProjectedRecord(
            source=CONNECTOR_NAME,
            entity=DOMAIN,
            source_id=name,
            last_seen_at=seen_at,
            fields=projected_fields(row),
        )

    # ------------------------------------------------------------ RoutedReading
    def first_route(self, entity: str, *, settings: Mapping[str, str]) -> Mapping[str, str] | None:
        self._assert_domain(entity)
        routed = DomainsConnection.from_settings(settings).routed()
        return {"name": routed[0]} if routed else None

    def next_route(
        self, entity: str, asked: Mapping[str, str], *, settings: Mapping[str, str]
    ) -> Mapping[str, str] | None:
        self._assert_domain(entity)
        routed = DomainsConnection.from_settings(settings).routed()
        after = asked.get("name", "")
        if after not in routed:
            return None
        at = routed.index(after) + 1
        return {"name": routed[at]} if at < len(routed) else None

    def operation_for(
        self,
        entity: str,
        page: Mapping[str, str],
        *,
        settings: Mapping[str, str],
        resolver: Resolver,
    ) -> RestOperation:
        """The lookup of one listed domain at its registry. See the module docstring."""
        del resolver  # the address is checked when the page is prepared
        self._assert_domain(entity)
        name = page.get("name", "")
        if not DomainsConnection.from_settings(settings).listed(name):
            raise DomainsError(ONLY_THE_CONNECTIONS_OWN_DOMAINS_ARE_LOOKED_UP)
        base = server_for(name)
        if base is None:
            raise DomainsError(A_REGISTRY_THAT_PUBLISHES_NO_RDAP_IS_SAID_SO)
        return operation_at(base)

    def unrouted(
        self, entity: str, *, settings: Mapping[str, str], seen_at: datetime
    ) -> tuple[ProjectedRecord, ...]:
        self._assert_domain(entity)
        kept = (
            self.projected(entity, _unpublished_row(name), seen_at=seen_at)
            for name in DomainsConnection.from_settings(settings).unrouted()
        )
        return tuple(
            ProjectedRecord(
                source=one.source,
                entity=one.entity,
                source_id=one.source_id,
                last_seen_at=one.last_seen_at,
                # A sentence is not an expiry date, so only the status is kept.
                fields={key: value for key, value in one.fields.items() if key != "expiry"},
            )
            for one in kept
            if one is not None
        )

    def unpublished(
        self, entity: str, source_id: str, *, settings: Mapping[str, str], fetched_at: str
    ) -> TypedResult[SourceRecord] | None:
        self._assert_domain(entity)
        connection = DomainsConnection.from_settings(settings)
        if not connection.listed(source_id) or server_for(source_id) is not None:
            return None
        return normalise(
            DOMAIN, (_unpublished_row(source_id.lower()),), source=SPEC_REF, fetched_at=fetched_at
        )

    @staticmethod
    def _assert_domain(entity: str) -> None:
        if entity != DOMAIN:
            msg = f"this reading keeps {DOMAIN!r} and was asked for {entity!r}"
            raise DomainsError(msg)


# ------------------------------------------------------------------- read live, and the site
def hosting_of(domain: str, *, caller: OneCall, resolver: Resolver) -> str:
    """What one domain's site answers, in words. See `HOSTING_IS_WHAT_THE_SITE_ITSELF_ANSWERS`."""
    try:
        checked = assert_fetchable(f"https://{domain}/", resolver)
    except UnsafeAddressError:
        return "does not resolve to a public address"
    except OSError:
        return "does not resolve"
    answer = caller.get(
        checked.url, address=checked.address, headers={"Accept": "text/html"}, max_bytes=SITE_BYTES
    )
    status = getattr(answer, "status", None)
    if getattr(answer, "timed_out", False):
        return "does not answer in time"
    if status is None or getattr(answer, "connection_failed", False):
        return "does not answer"
    if int(status) >= 500:
        return f"answers with a server error (HTTP {status})"
    return f"answers (HTTP {status})"


class DomainsLiveLookup:
    """A listed domain read live from its registry, with its site asked beside it."""

    def entities(self) -> tuple[str, ...]:
        return (DOMAIN,)

    def identity_mode(self, entity: str) -> IdentityMode:
        # A published record read with no key: whoever may be told it is decided by our grants.
        del entity
        return IdentityMode.SERVICE

    def arguments_for(self, entity: str, source_id: str) -> Mapping[str, str]:
        del entity
        name = source_id.lower()
        if not _DOMAIN_RE.fullmatch(name):
            msg = "the record's id is not a domain name"
            raise DomainsError(msg)
        return {"name": name}

    def operation(self, entity: str, *, settings: Mapping[str, str], resolver: Any) -> None:
        """None: a domain is read by its routed page, from the registry that holds it."""
        del entity, settings, resolver

    def facts(
        self, entity: str, source_id: str, *, caller: OneCall, resolver: Resolver
    ) -> Mapping[str, str]:
        del entity
        return {"hosting": hosting_of(source_id.lower(), caller=caller, resolver=resolver)}


# ------------------------------------------------------------------------ the manifest
def manifest(connection: DomainsConnection, *, ref: SecretRef) -> ConnectorManifest:
    """Everything this connector declares for one connection.

    The credential binds a slot nothing is written to, because the manifest's shape requires one
    and a source that takes no key has none to keep; the reading and the live read take no lease
    for it (`KeyScheme.NONE`). The one tool reads a published record, so it declares SERVICE
    identity and the connection's department predicate is what narrows it.
    """
    return ConnectorManifest(
        name=CONNECTOR_NAME,
        version=VERSION,
        transport=TransportKind.REST,
        scope=connection.scope(),
        credential=CredentialBinding(ref=ref, mode=AccessMode.READ_ONLY),
        tools=(
            ToolDeclaration(
                name="domains.read_domain",
                description=(
                    "Read one of the agency's domains: its registrar and expiry from its "
                    "registry, and whether its site answers, all live."
                ),
                entity=DOMAIN,
                identity_mode=IdentityMode.SERVICE,
            ),
        ),
        projections=(
            ProjectedEntity(
                entity=DOMAIN,
                fields=FIELDS,
                # Every listed domain is read again in full each day, from the start, which is
                # what an updated-since cursor that begins at the beginning reads; the registry's
                # own last-changed event is each record's change mark.
                change_signal=ChangeSignal.UPDATED_SINCE,
                visibility=connection.visibility(),
            ),
        ),
        ceiling=CONNECTOR_NAME,
    )


def built_from_the_console(settings: Mapping[str, str], ref: SecretRef) -> ConnectorManifest:
    """The manifest a connection made on the Connectors screen declares."""
    return manifest(DomainsConnection.from_settings(settings), ref=ref)


@dataclass(frozen=True)
class Reply:
    """One registry reply, for the read-back: its status and body."""

    status: int
    body: Any


def read_back_reading(operation: RestOperation, reply: Reply) -> Reading:
    """One registry reply, read as the reading reads it. An answered lookup is complete."""
    call = classify(status=reply.status)
    if call is not CallOutcome.OK:
        return Reading(outcome=call, matched=0, complete=False)
    try:
        rows = operation.project(reply.body)
        record_of(reply.body)
    except ConnectorContractError:
        return unreadable()
    return Reading(outcome=CallOutcome.OK, matched=len(rows), complete=True)


# ------------------------------------------------------------------------ the console
CONSOLE: Final = ConsoleForm(
    settings=(
        Setting(
            name=DOMAINS_SETTING,
            label="Domains",
            hint=(
                "Every client domain to look after, separated by commas or new lines, such as "
                f"example.com, example.org. Up to {MAX_DOMAINS}; only these are ever looked up."
            ),
            refused=(
                f"That is not a list of up to {MAX_DOMAINS} domain names. Type each as its name "
                "alone, such as example.com, with no https:// and nothing after it."
            ),
            max_chars=DOMAINS_CHARS,
        ),
        Setting(
            name=DEPARTMENT_SETTING,
            label="Department that may be told them",
            hint=(
                "The short name of the department whose people may be granted these domains, "
                "as the Departments page shows it."
            ),
            refused=(
                "That is not a department's short name. Use lower-case letters, digits and "
                "underscores, exactly as the Departments page shows it."
            ),
        ),
    ),
    credential_label="No key",
    credential_hint=(
        "A registry publishes who registered a domain and until when to anybody who asks, so "
        "nothing is kept in the vault for this source."
    ),
    build=built_from_the_console,
    credential_shape=CredentialShape.NONE,
    example=ConnectExample(
        settings={DOMAINS_SETTING: "example.com, example.org", DEPARTMENT_SETTING: "operations"},
        fresh=lambda departments: {
            DOMAINS_SETTING: (
                f"acceptance-{secrets.token_hex(4)}.example, "
                f"acceptance-{secrets.token_hex(4)}.example"
            ),
            DEPARTMENT_SETTING: departments[0],
        },
        edit=DOMAINS_SETTING,
        edited=lambda: f"acceptance-{secrets.token_hex(4)}.example",
    ),
)

#: The screens that connect it: gather the list, then type it here.
GUIDE: Final = keyed(
    (
        GuideStep(
            key="list",
            title="Gather the domains you look after",
            text=(
                "List every client domain this system should report on: its registrar, when it "
                "expires and whether its site answers. Only the domains you list are ever looked "
                "up, and each is read from its own registry."
            ),
            sketch=Sketch(
                place="Your records",
                heading="Client domains",
                lines=(
                    SketchLine(LineKind.ITEM, "example.com", mark=True),
                    SketchLine(LineKind.ITEM, "example.org", mark=True),
                ),
            ),
        ),
        GuideStep(
            key="department",
            title="Choose who may be told them",
            text=(
                "Choose the one department whose people may be told these domains' registrars, "
                "expiry dates and whether their sites answer. Its administrator then grants each "
                "fact to the people who need it; nobody else is told anything about them."
            ),
            sketch=Sketch(
                place="Company Brain",
                heading="Departments",
                lines=(SketchLine(LineKind.ITEM, "operations", mark=True),),
            ),
        ),
        GuideStep(
            key="connect",
            title="Type the domains and the department here",
            text=(
                "Type the domains, separated by commas or new lines, and the short name of the "
                "department whose people may be told them, then press Connect Domains and "
                "hosting. No key is needed."
            ),
            sketch=Sketch(
                place="Company Brain",
                heading="Connect Domains and hosting",
                lines=(
                    SketchLine(LineKind.FIELD, "Domains", "example.com, example.org", mark=True),
                    SketchLine(LineKind.FIELD, "Department", "operations", mark=True),
                ),
                button="Connect Domains and hosting",
            ),
            asks=(DOMAINS_SETTING, DEPARTMENT_SETTING),
        ),
    )
)


#: This source's verified rate ceiling, which `brain.ops.limits.connector_ceiling` finds
#: on this declaration. See `brain.ops.limits.A_CEILING_LIVES_WITH_ITS_CONNECTOR`.
CEILING: Final = ConnectorLimit(
    name="domains",
    per_minute=30,
    raisable=False,
    note=(
        "RDAP servers state no common figure: RFC 7480 section 5.5 lets each registry limit "
        "as it chooses and answer 429 when it does, and one domains connection's calls go "
        "to many registries. Thirty a minute is this product's own pace, one lookup every "
        "two seconds, which reads a book of two hundred domains in under seven minutes and "
        "is below every limit a registry publishes. Not a vendor's figure, and said so."
    ),
)


CONNECTOR: Final = ConnectorDeclaration(
    ceiling=CEILING,
    name=CONNECTOR_NAME,
    label="Domains and hosting",
    guide=GUIDE,
    console=CONSOLE,
    read_back=ReadBack(
        reading=read_back_reading,
        recorded=(
            "DOMAINS-200-domain",
            "DOMAINS-404",
            "DOMAINS-429",
            "DOMAINS-503",
        ),
        findings=(),
    ),
    recorded=Recorded(tested=True),
    reading=DomainsReading(),
    live=DomainsLiveLookup(),
    # A domain's kept fields and the three read live, each behind its own capability (M11.7.4):
    # a domain is reached with `read:domain` in the connection's department, and each fact a
    # person is told is a further grant. Keyless, so it declares no scopes and has no slot.
    ask=AskRows(
        scoped_by=DEPARTMENT_SETTING,
        entities=(
            AskEntity(
                entity=DOMAIN,
                fields=each_behind_its_own(DOMAIN, (*(one.name for one in FIELDS), *LIVE_ONLY)),
                description=(
                    "Look up the agency's domains by name: when each expires and its registration "
                    "status, and its registrar and whether its site answers, read live"
                ),
                named_by="name",
            ),
        ),
    ),
)
