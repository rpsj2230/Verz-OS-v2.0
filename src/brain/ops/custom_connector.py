"""A connector for a new API, added from the console as data: its specification, mapping and key.

M11.7.8 asks that an administrator adds a connector for an API this release does not ship by
supplying its specification, its field mapping and a credential reference, and that it becomes
available to agents after review without a release. `brain.connectors.rest` was written for exactly
this ("adding an endpoint has to be data, not a deployment") and every shipped REST connector is
already a specification, a `FieldMapping` per entity and a projection. **So a definition here is the
same four things a shipped connector's module declares, held as data, and `declaration_of` turns it
into the same `ConnectorDeclaration` through the same `load_spec`, `RestTransport`, `FieldMapping`,
projection and address rule.** Nothing downstream can tell the two apart, which is the point: the
worker, the live read, the Connectors screen, the registry and Ask read it through the code they
read Xero through.

**Read-only, by construction.** A definition names operations, and an operation that is not a GET is
refused here at submit; `RestOperation.read` refuses one again at call time. No definition can
declare a write: `ConnectorDeclaration.writes` is never set from one.

**The ceiling is mandatory.** A definition with no verified rate ceiling, cited from the vendor's
own page, is refused, because nothing is read against a ceiling nobody measured
(`brain.ops.connector_sync.NO_VERIFIED_CEILING`) and `brain.ops.connectable` offers nothing it
cannot read. See `AN_UNMEASURED_SOURCE_IS_NOT_OFFERED`.

**The document is parsed with a size cap and never fetches.** A specification is somebody's text
pasted into a form. It is refused over `MAX_DOCUMENT_BYTES` or `MAX_DOCUMENT_DEPTH` before it is
parsed into anything larger, and every `$ref` in the whole document, reached or not, must point
inside it: an external reference is refused at submit rather than when a schema happens to reach it,
because a reviewer approving a document should be approving everything it says.
`brain.connectors.rest._pointer` refuses the same thing at load, so the rule has two places it is
checked and one place it is stated. See `A_SPECIFICATION_NEVER_FETCHES`.

**Every mapped field is classified, and Ask's rows are built from those classifications.** A field
with no classification is refused rather than withheld from everybody, because a definition is
reviewed field by field and an unclassified field is one nobody decided about. Each field is behind
its own capability, `read:<entity>.<field>`, at the classification the submitter gave it, which is
`brain.connectors.ask.each_behind_its_own`'s pattern with the sensitivity chosen per field.

**A field is kept in the minimal index only when it says how.** Each field names the shape it is
kept in (a label, a status, a timestamp, a join key) or nothing, and a field kept in no shape is
read live from the entity's one-record operation while somebody waits. A definition with a field
kept nowhere and no one-record operation is refused, because nothing could ever answer it. The
projection is `brain.connectors.manifest.ProjectedEntity`, so its five clauses and its twelve-field
cap are the refusals, and the department every kept row carries counts against the cap.

**One department reads a connected definition, as one reads a connected helpdesk.** The definition
names it, the reviewer approves it, and the connection's one setting must name the same department,
so a person connecting it confirms who will be granted its records. The kept rows carry it and a
reader is granted its records in that department, which is `brain.connectors.freshdesk`'s visibility
rule, reused.

**The key schemes are the closed set's, never a new one.** A bearer token and HTTP Basic with the
key as the user name are pasted as one key; a source publishing to anybody takes none. A Google
service account needs a token scope only a shipped connector can declare, and a database user is a
`ViewReading`, so both are refused here. See `A_DEFINITION_USES_A_KEY_SCHEME_THAT_EXISTS`.

Rejected: generating a Python module per definition and loading it. It would be code written by a
form and executed by the worker, which is the review this leaf replaces with a second person, done
badly. A definition is data, compiled into objects whose every method is this module's.

Scope: domain logic. Nothing here reads a table or opens a connection; the resolver is a parameter.

Task ids: M11.7.8
"""

from __future__ import annotations

import enum
import json
import re
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from typing import Any, Final
from urllib.parse import urlsplit

from brain.connectors.ask import AskEntity, AskRows
from brain.connectors.contract import (
    AccessMode,
    ConnectorContractError,
    ConnectorScope,
    CredentialBinding,
    TransportKind,
)
from brain.connectors.declaration import (
    ConnectorDeclaration,
    ConsoleForm,
    CredentialShape,
    KeyScheme,
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
from brain.connectors.rest import (
    ID_TARGET,
    READ_METHOD,
    OperationSpec,
    RestOperation,
    RestSpec,
    load_spec,
)
from brain.connectors.throttle import CallOutcome, classify
from brain.connectors.transports import FieldMapping, RestTransport
from brain.connectors.write_verification import NOTHING_IS_RECORDED, ReadBack, classified_reading
from brain.core.department import SLUG_RE
from brain.core.entitlement import Capability
from brain.core.envelope import OBJECT_NAME_PATTERN, IdentityMode
from brain.core.field_policy import Classification, FieldRule
from brain.core.projection import MAX_LABEL_CHARS
from brain.core.scope import Scope
from brain.ops.credentials import CONNECTOR_NAME_PATTERN
from brain.ops.limits import ConnectorLimit
from brain.ops.secrets import SecretRef
from brain.tools.fetch import Resolver

# ------------------------------------------------------------------ written-down reasons
#: Why a definition with no ceiling is refused.
AN_UNMEASURED_SOURCE_IS_NOT_OFFERED: Final = (
    "Nothing is read from a source against a ceiling nobody measured, and the Connectors screen "
    "offers nothing it cannot read. So a definition names the vendor's own calls a minute, and a "
    "day where there is one, with the page that says so, and one with none is refused rather "
    "than stored to wait for a figure."
)

#: Why the document may not reach outside itself.
A_SPECIFICATION_NEVER_FETCHES: Final = (
    "A specification pasted into a form is configuration, and a reference to another address "
    "inside it would make loading it an outbound request from inside the company's network. So "
    "every $ref in the document, whether a schema reaches it or not, must point inside it, and "
    "the document is refused whole over its size or depth cap before anything is built from it."
)

#: Why a definition's key scheme is one the worker already presents.
A_DEFINITION_USES_A_KEY_SCHEME_THAT_EXISTS: Final = (
    "The worker's run is the only code that writes a key into a header, and each way it does so "
    "was reviewed where the key is handled. A definition chooses one of those ways and cannot add "
    "one: a bearer token or Basic with the key as the user name, pasted as one key, or no key "
    "for a source that publishes to anybody."
)

#: Why the connection's department must be the definition's.
THE_DEPARTMENT_IS_THE_REVIEWED_ONE: Final = (
    "Who may be granted a connected API's records is part of what the reviewer approved, so the "
    "connection names the department the definition names, and a connection naming another is "
    "refused rather than granting a department nobody reviewed."
)

#: Why a mapped field must say how it is classified, and what happens to one kept nowhere.
EVERY_FIELD_IS_DECIDED_BY_THE_PERSON_WHO_MAPPED_IT: Final = (
    "A definition is reviewed field by field, so every mapped field carries the classification "
    "its submitter chose and is reached by its own capability. A field kept in no index shape is "
    "read live by the entity's one-record operation, and one with neither could never answer, so "
    "it is refused."
)

# ------------------------------------------------------------------------ the figures
#: The largest specification accepted, as the bytes pasted. Far past any document a mapping of a
#: few entities needs, and small enough that a paste is never a denial of service.
MAX_DOCUMENT_BYTES: Final = 256 * 1024

#: How deeply the document may nest. A real specification is a dozen levels at most.
MAX_DOCUMENT_DEPTH: Final = 32

#: How many entities one definition reads, and how many fields one entity maps.
MAX_ENTITIES: Final = 8
MAX_FIELDS: Final = 24

#: The field a kept row carries for its department, which no mapping may name. The visibility
#: rule's own field, `brain.core.scope.Scope.department`.
DEPARTMENT_FIELD: Final = "department"

#: How often a connected definition's entities are read. Fixed by the product, as every shipped
#: connector's interval is, and long enough that a vendor's per-minute figure is never the limit.
READING_INTERVAL: Final = timedelta(hours=1)

#: The longest label, description and cited page a definition may carry.
MAX_LABEL: Final = 80
MAX_DESCRIPTION: Final = 300
MAX_CITED: Final = 500

#: The largest page size a definition may declare.
MAX_PAGE_SIZE: Final = 1000

#: What a record id laid into a one-record operation's path may be. Encoded anyway by
#: `RestOperation.url_for`; refused here first, so an id that is not one is never sent.
LIVE_ID_PATTERN: Final = re.compile(r"^[A-Za-z0-9_.@:-]{1,128}$")

_NAME_RE: Final = re.compile(OBJECT_NAME_PATTERN)
_CONNECTOR_RE: Final = re.compile(CONNECTOR_NAME_PATTERN)

#: The schemes a definition may choose, and the credential shape each is pasted in.
SCHEMES: Final[Mapping[KeyScheme, CredentialShape]] = MappingProxyType(
    {
        KeyScheme.BEARER: CredentialShape.KEY,
        KeyScheme.BASIC_KEY_AS_USER: CredentialShape.KEY,
        KeyScheme.NONE: CredentialShape.NONE,
    }
)

#: What the fast lane uses a kept field of each shape for, as `ProjectedEntity`'s hot clause asks.
USES: Final[Mapping[FieldShape, tuple[HotUse, ...]]] = MappingProxyType(
    {
        FieldShape.IDENTIFIER: (HotUse.IDENTIFY,),
        FieldShape.JOIN_KEY: (HotUse.JOIN, HotUse.FILTER),
        FieldShape.STATUS: (HotUse.FILTER, HotUse.COUNT),
        FieldShape.TIMESTAMP: (HotUse.FILTER, HotUse.SORT),
        FieldShape.LABEL: (HotUse.IDENTIFY,),
    }
)


class CustomConnectorError(ConnectorContractError):
    """A definition that cannot be stored or compiled, with every problem it has."""

    def __init__(self, problems: tuple[DefinitionProblem, ...]) -> None:
        super().__init__("; ".join(f"{one.field}: {one.message}" for one in problems))
        self.problems = problems


@dataclass(frozen=True)
class DefinitionProblem:
    """One thing wrong with a definition: where, a stable code, and what to do about it."""

    field: str
    code: str
    message: str


class ReviewState(enum.StrEnum):
    """Where a definition stands. Only APPROVED is offered, given tools or read."""

    UNREVIEWED = "unreviewed"
    APPROVED = "approved"
    REJECTED = "rejected"


# ------------------------------------------------------------------------ the definition
@dataclass(frozen=True)
class MappedField:
    """One field of one entity: our name, where it is in the vendor's record, and who may see it.

    `kept` is the shape it is kept in the minimal index, or None for a field read live only.
    """

    target: str
    source_path: str
    classification: Classification
    kept: FieldShape | None = None


@dataclass(frozen=True)
class EntityDefinition:
    """One entity a definition reads: its list operation, its one-record operation, its fields."""

    entity: str
    list_operation: str
    id_path: str
    fields: tuple[MappedField, ...]
    named_by: str
    description: str
    one_operation: str | None = None

    def kept(self) -> tuple[MappedField, ...]:
        return tuple(one for one in self.fields if one.kept is not None)

    def live_only(self) -> tuple[str, ...]:
        return tuple(one.target for one in self.fields if one.kept is None)

    def mapping(self) -> tuple[FieldMapping, ...]:
        """The id first, then every field, as the transport's allowlist."""
        return (
            FieldMapping(target=ID_TARGET, source_path=self.id_path),
            *(FieldMapping(target=one.target, source_path=one.source_path) for one in self.fields),
        )


@dataclass(frozen=True)
class Ceiling:
    """The vendor's own rate ceiling, and the page it is stated on."""

    per_minute: int
    cited: str
    per_day: int | None = None


@dataclass(frozen=True)
class CustomDefinition:
    """A connector for an API this release does not ship, as an administrator submitted it."""

    name: str
    label: str
    document: Mapping[str, Any]
    entities: tuple[EntityDefinition, ...]
    key_scheme: KeyScheme
    credential_shape: CredentialShape
    ceiling: Ceiling | None
    department: str
    page_parameter: str | None = None
    page_size: int | None = None
    #: Bumped by every change, so a compiled declaration is cached by name and revision.
    revision: int = 1

    def entity(self, name: str) -> EntityDefinition:
        for one in self.entities:
            if one.entity == name:
                return one
        msg = f"this connector reads {[one.entity for one in self.entities]}, not {name!r}"
        raise ConnectorContractError(msg)


# ---------------------------------------------------------------------- the document
def parse_document(text: str) -> dict[str, Any]:
    """The specification as JSON, refused over its caps or for any reference outside itself.

    See `A_SPECIFICATION_NEVER_FETCHES`. Raises `CustomConnectorError` naming `document`.
    """
    if len(text.encode("utf-8")) > MAX_DOCUMENT_BYTES:
        raise _refused(
            "document",
            "too_large",
            f"The specification is larger than {MAX_DOCUMENT_BYTES // 1024} KB. Paste only the "
            "operations this connector reads and the schemas they use.",
        )
    try:
        parsed = json.loads(text)
    except ValueError as exc:
        raise _refused(
            "document", "not_json", "The specification is not JSON. Paste it as JSON."
        ) from exc
    if not isinstance(parsed, dict):
        raise _refused("document", "not_an_object", "The specification is not a JSON object.")
    check_document(parsed)
    return parsed


def check_document(document: Mapping[str, Any]) -> None:
    """Refuse a document deeper than the cap, or with a `$ref` that is not inside it."""
    stack: list[tuple[Any, int]] = [(document, 0)]
    while stack:
        node, depth = stack.pop()
        if depth > MAX_DOCUMENT_DEPTH:
            raise _refused(
                "document",
                "too_deep",
                f"The specification nests deeper than {MAX_DOCUMENT_DEPTH} levels.",
            )
        if isinstance(node, Mapping):
            ref = node.get("$ref")
            if "$ref" in node and (not isinstance(ref, str) or not ref.startswith("#/")):
                raise _refused(
                    "document",
                    "external_reference",
                    "The specification refers to something outside itself. Every $ref must "
                    "start with #/ and point at a component in this document; nothing is "
                    "fetched from elsewhere.",
                )
            stack.extend((child, depth + 1) for child in node.values())
        elif isinstance(node, list):
            stack.extend((child, depth + 1) for child in node)


def _refused(field: str, code: str, message: str) -> CustomConnectorError:
    return CustomConnectorError((DefinitionProblem(field=field, code=code, message=message),))


# ---------------------------------------------------------------------- the judgement
def problems(
    definition: CustomDefinition,
    *,
    resolver: Resolver,
    taken_names: Collection[str] = (),
    taken_entities: Collection[str] = (),
) -> tuple[DefinitionProblem, ...]:
    """Everything wrong with a definition, all at once, or nothing.

    `taken_names` are the names a definition may not have (every shipped connector, every key
    slot); `taken_entities` the entities another source already classifies, whose capabilities a
    definition would otherwise share.
    """
    found: list[DefinitionProblem] = []

    def say(field: str, code: str, message: str) -> None:
        found.append(DefinitionProblem(field=field, code=code, message=message))

    if not (_CONNECTOR_RE.fullmatch(definition.name) and _NAME_RE.match(definition.name)):
        say(
            "name",
            "not_a_name",
            "Use lower-case letters, digits and underscores, starting with a letter.",
        )
    elif definition.name in taken_names:
        say(
            "name",
            "taken",
            "That name is a connector this release ships or a key slot this install keeps. "
            "Choose another.",
        )
    if not definition.label.strip() or len(definition.label) > MAX_LABEL:
        say("label", "blank", f"Give the connector a name of at most {MAX_LABEL} characters.")
    if not SLUG_RE.fullmatch(definition.department):
        say(
            "department",
            "not_a_department",
            "Give the short name of the one department whose people may be granted its records.",
        )
    _ceiling_problems(definition.ceiling, say)
    if SCHEMES.get(definition.key_scheme) is not definition.credential_shape:
        say("key_scheme", "not_a_scheme", A_DEFINITION_USES_A_KEY_SCHEME_THAT_EXISTS)
    try:
        check_document(definition.document)
        spec = load_spec(definition.document, resolver=resolver)
    except ConnectorContractError as refused:
        if isinstance(refused, CustomConnectorError):
            found.extend(refused.problems)
        else:
            say("document", "unreadable", f"The specification cannot be read: {refused}")
        return tuple(found)
    if not definition.entities or len(definition.entities) > MAX_ENTITIES:
        say("entities", "count", f"Map between one and {MAX_ENTITIES} entities.")
    seen: set[str] = set()
    for index, entity in enumerate(definition.entities):
        where = f"entities.{index}"
        if entity.entity in seen:
            say(where, "twice", "That entity is mapped twice.")
        seen.add(entity.entity)
        if entity.entity in taken_entities:
            say(
                where,
                "entity_taken",
                "Another source already has records of that kind, and the two would share their "
                "capabilities. Name the entity after this API, such as its own word for it.",
            )
        found.extend(_entity_problems(definition, entity, spec, where))
    if (definition.page_parameter is None) != (definition.page_size is None):
        say("paging", "half", "Give both the page parameter and the page size, or neither.")
    elif definition.page_size is not None and not 1 <= definition.page_size <= MAX_PAGE_SIZE:
        say("paging", "size", f"A page size is between 1 and {MAX_PAGE_SIZE}.")
    elif definition.page_parameter is not None:
        for entity in definition.entities:
            declared = _operation(spec, entity.list_operation)
            if declared is None or (
                (one := declared.parameter(definition.page_parameter)) is None
                or one.location != "query"
            ):
                say(
                    "paging",
                    "not_a_parameter",
                    "Every list operation must declare the page parameter in its query.",
                )
                break
    return tuple(found)


def _ceiling_problems(ceiling: Ceiling | None, say: Callable[[str, str, str], None]) -> None:
    if ceiling is None:
        say("ceiling", "missing", AN_UNMEASURED_SOURCE_IS_NOT_OFFERED)
        return
    if ceiling.per_minute < 1:
        say("ceiling", "per_minute", "Give the vendor's calls a minute as a whole number above 0.")
    if ceiling.per_day is not None and ceiling.per_day < 1:
        say("ceiling", "per_day", "Give the vendor's calls a day as a whole number above 0.")
    cited = urlsplit(ceiling.cited.strip())
    if cited.scheme != "https" or not cited.hostname or len(ceiling.cited) > MAX_CITED:
        say(
            "ceiling",
            "not_cited",
            "Give the https address of the vendor's page that states this ceiling.",
        )


def _operation(spec: RestSpec, name: str) -> OperationSpec | None:
    return spec.operations.get(name)


def _entity_problems(
    definition: CustomDefinition, entity: EntityDefinition, spec: RestSpec, where: str
) -> list[DefinitionProblem]:
    found: list[DefinitionProblem] = []

    def say(code: str, message: str) -> None:
        found.append(DefinitionProblem(field=where, code=code, message=message))

    if not _NAME_RE.match(entity.entity) or entity.entity == DEPARTMENT_FIELD:
        say("not_a_name", "An entity is named in lower-case letters, digits and underscores.")
        return found
    if not entity.description.strip() or len(entity.description) > MAX_DESCRIPTION:
        say("description", f"Describe the entity in at most {MAX_DESCRIPTION} characters.")
    listed = _operation(spec, entity.list_operation)
    if listed is None:
        say("no_list_operation", "The specification declares no operation by that id.")
    elif listed.method != READ_METHOD or not listed.returns_list:
        say("list_not_a_list", "The list operation must be a GET whose answer holds a list.")
    if entity.one_operation is not None:
        one = _operation(spec, entity.one_operation)
        path = [] if one is None else [p for p in one.parameters if p.location == "path"]
        if one is None:
            say("no_one_operation", "The specification declares no operation by that id.")
        elif one.method != READ_METHOD or one.returns_list or len(path) != 1:
            say(
                "one_not_one",
                "The one-record operation must be a GET with one path parameter, the record's "
                "id, whose answer is one record.",
            )
    if not entity.fields or len(entity.fields) > MAX_FIELDS:
        say("field_count", f"Map between one and {MAX_FIELDS} fields.")
    targets = [one.target for one in entity.fields]
    if len(targets) != len(set(targets)):
        say("field_twice", "A field is mapped twice.")
    for mapped in entity.fields:
        if mapped.target in (ID_TARGET, DEPARTMENT_FIELD) or not _NAME_RE.match(mapped.target):
            say(
                "field_name",
                f"A field is named in lower-case letters, digits and underscores, and not "
                f"{ID_TARGET} or {DEPARTMENT_FIELD}, which are the record's own.",
            )
            return found
    if entity.live_only() and entity.one_operation is None:
        say("read_nowhere", EVERY_FIELD_IS_DECIDED_BY_THE_PERSON_WHO_MAPPED_IT)
    if entity.named_by not in {one.target for one in entity.kept()}:
        say(
            "named_by",
            "Name the kept field a person names a record by, such as its number or its name.",
        )
    try:
        mapping = entity.mapping()
        transport = RestTransport(
            spec_ref=definition.name or "custom",
            operation=entity.list_operation,
            entity=entity.entity,
            fields=mapping,
        )
        if listed is not None:
            spec.bind(transport)
        _projection(entity, Scope.department(definition.department or "x"))
    except ConnectorContractError as refused:
        say("mapping", f"The mapping cannot be used: {refused}")
    return found


def check(
    definition: CustomDefinition,
    *,
    resolver: Resolver,
    taken_names: Collection[str] = (),
    taken_entities: Collection[str] = (),
) -> None:
    """Refuse a definition with any problem. See `problems`."""
    found = problems(
        definition, resolver=resolver, taken_names=taken_names, taken_entities=taken_entities
    )
    if found:
        raise CustomConnectorError(found)


# ------------------------------------------------------------------------ compiling it
def _projection(entity: EntityDefinition, visibility: Scope) -> ProjectedEntity:
    """What is kept about one entity, in `ProjectedEntity`'s terms, so its clauses are the rules.

    `UPDATED_SINCE` is the signal, at its coarsest: the worker reads every page of the entity at
    each interval, so a change is seen at the next read, as it is for a helpdesk's tickets.
    """
    return ProjectedEntity(
        entity=entity.entity,
        fields=tuple(
            ProjectedField(name=one.target, shape=one.kept, uses=USES[one.kept])
            for one in entity.fields
            if one.kept is not None
        ),
        change_signal=ChangeSignal.UPDATED_SINCE,
        visibility=visibility,
    )


def _host(definition: CustomDefinition) -> str:
    servers = definition.document.get("servers") or [{}]
    url = servers[0].get("url", "") if isinstance(servers[0], Mapping) else ""
    return urlsplit(str(url)).hostname or definition.name


def manifest_of(
    definition: CustomDefinition, settings: Mapping[str, str], ref: SecretRef
) -> ConnectorManifest:
    """The manifest a connection of this definition declares, refused for another department."""
    department = settings.get(DEPARTMENT_FIELD, "").strip()
    if department != definition.department:
        msg = f"{department!r} is not the reviewed department. {THE_DEPARTMENT_IS_THE_REVIEWED_ONE}"
        raise SettingRefusedError(msg, setting=DEPARTMENT_FIELD)
    visibility = Scope.department(definition.department)
    return ConnectorManifest(
        name=definition.name,
        version=f"1.0.{definition.revision}",
        transport=TransportKind.REST,
        scope=ConnectorScope(resource_kind="service", selectors=(_host(definition),)),
        credential=CredentialBinding(ref=ref, mode=AccessMode.READ_ONLY),
        tools=tuple(
            ToolDeclaration(
                name=f"{definition.name}.read_{one.entity}",
                description=one.description,
                entity=one.entity,
                identity_mode=IdentityMode.SERVICE,
            )
            for one in definition.entities
        ),
        projections=tuple(_projection(one, visibility) for one in definition.entities),
        ceiling=definition.name,
    )


def _parsed_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


class CustomReading:
    """A definition's entities, a page at a time, into the minimal index and nothing else."""

    def __init__(self, definition: CustomDefinition) -> None:
        self._definition = definition

    def __repr__(self) -> str:
        return f"CustomReading({self._definition.name!r}, revision={self._definition.revision})"

    def entities(self) -> tuple[str, ...]:
        return tuple(one.entity for one in self._definition.entities)

    def refresh_interval(self) -> timedelta:
        return READING_INTERVAL

    def bound(self, entity: str, operation: str, *, resolver: Resolver) -> RestOperation:
        """One operation of the document, bound to the entity's mapping, address checked."""
        one = self._definition.entity(entity)
        spec = load_spec(self._definition.document, resolver=resolver)
        return spec.bind(
            RestTransport(
                spec_ref=self._definition.name,
                operation=operation,
                entity=one.entity,
                fields=one.mapping(),
            )
        )

    def operation(
        self, entity: str, *, settings: Mapping[str, str], resolver: Resolver
    ) -> RestOperation:
        del settings  # the address is the document's one server, for every connection
        return self.bound(entity, self._definition.entity(entity).list_operation, resolver=resolver)

    def key_scheme(self) -> KeyScheme:
        return self._definition.key_scheme

    def first_page(self, entity: str) -> Mapping[str, str]:
        self._definition.entity(entity)
        if self._definition.page_parameter is None:
            return MappingProxyType({})
        return MappingProxyType({self._definition.page_parameter: "1"})

    def next_page(
        self, entity: str, asked: Mapping[str, str], body: Any, returned: int
    ) -> Mapping[str, str] | None:
        del entity, body
        name, size = self._definition.page_parameter, self._definition.page_size
        if name is None or size is None or returned < size:
            return None
        return MappingProxyType({**asked, name: str(int(asked.get(name, "1")) + 1)})

    def call_headers(self, settings: Mapping[str, str]) -> Mapping[str, str]:
        del settings
        return MappingProxyType({})

    def interpret(
        self, operation: RestOperation, *, status: int, body: Any, fetched_at: str
    ) -> PageReply:
        call = classify(status=status)
        if call is not CallOutcome.OK:
            return PageReply(call=call, rows=None)
        return PageReply(call=call, rows=operation.records(body, fetched_at=fetched_at))

    def retry_after(self, headers: Mapping[str, str]) -> float | None:
        for key, value in headers.items():
            if key.casefold() == "retry-after":
                try:
                    return float(int(str(value).strip()))
                except ValueError:
                    return None
        return None

    def allowance_spent(self, headers: Mapping[str, str]) -> bool:
        del headers  # a vendor's own budget header is not something a definition names
        return False

    def projected(
        self, entity: str, row: Mapping[str, Any], *, seen_at: datetime
    ) -> ProjectedRecord | None:
        """The kept fields of one row, built from the declared names and never copied."""
        one = self._definition.entity(entity)
        raw_id = row.get(ID_TARGET)
        if not isinstance(raw_id, str | int) or not str(raw_id).strip():
            return None
        fields: dict[str, ProjectedValue] = {}
        for kept in one.kept():
            if kept.target not in row:
                continue
            value = row[kept.target]
            if kept.kept is FieldShape.TIMESTAMP:
                dated = _parsed_time(value)
                if dated is not None:
                    fields[kept.target] = dated
                continue
            if kept.kept is FieldShape.LABEL and isinstance(value, str):
                value = value[:MAX_LABEL_CHARS]
            fields[kept.target] = value
        return ProjectedRecord(
            source=self._definition.name,
            entity=one.entity,
            source_id=str(raw_id),
            last_seen_at=seen_at,
            fields=fields,
        )


class CustomLiveLookup:
    """One record of a definition, read by its one-record operation while somebody waits."""

    def __init__(self, definition: CustomDefinition, reading: CustomReading) -> None:
        self._definition = definition
        self._reading = reading

    def __repr__(self) -> str:
        return f"CustomLiveLookup({self._definition.name!r})"

    def entities(self) -> tuple[str, ...]:
        return tuple(one.entity for one in self._definition.entities if one.one_operation)

    def identity_mode(self, entity: str) -> IdentityMode:
        del entity  # one key per connection, so the service's
        return IdentityMode.SERVICE

    def arguments_for(self, entity: str, source_id: str) -> Mapping[str, str]:
        operation = self._one(entity)
        if not LIVE_ID_PATTERN.match(source_id):
            msg = "a record id laid into an address is refused rather than escaped"
            raise ConnectorContractError(msg)
        return MappingProxyType({operation: source_id})

    def _one(self, entity: str) -> str:
        """The name of the one path parameter of the entity's one-record operation."""
        one = self._definition.entity(entity)
        if one.one_operation is None:
            msg = f"{entity!r} has no one-record operation"
            raise ConnectorContractError(msg)
        found = self._definition.document["paths"]
        for methods in found.values():
            body = methods.get("get") if isinstance(methods, Mapping) else None
            if isinstance(body, Mapping) and body.get("operationId") == one.one_operation:
                for parameter in body.get("parameters", ()):
                    if isinstance(parameter, Mapping) and parameter.get("in") == "path":
                        return str(parameter["name"])
        msg = f"{entity!r}'s one-record operation names no path parameter"
        raise ConnectorContractError(msg)

    def operation(
        self, entity: str, *, settings: Mapping[str, str], resolver: Resolver
    ) -> RestOperation | None:
        del settings
        one = self._definition.entity(entity)
        if one.one_operation is None:
            return None
        return self._reading.bound(entity, one.one_operation, resolver=resolver)


def ask_rows(definition: CustomDefinition) -> AskRows:
    """What Ask answers from it: each mapped field behind its own capability, as classified."""
    return AskRows(
        scoped_by=DEPARTMENT_FIELD,
        entities=tuple(
            AskEntity(
                entity=one.entity,
                fields=tuple(
                    FieldRule(
                        entity=one.entity,
                        field=field.target,
                        required_capability=Capability(value=f"read:{one.entity}.{field.target}"),
                        classification=field.classification,
                    )
                    for field in one.fields
                ),
                description=one.description,
                named_by=one.named_by,
                live_only=one.live_only(),
            )
            for one in definition.entities
        ),
    )


def declaration_of(definition: CustomDefinition) -> ConnectorDeclaration:
    """The definition as the declaration a shipped connector would make, read the same way.

    Built from a stored definition that was judged at submit; a definition that can no longer be
    compiled raises, and the store leaves it out of the catalogue rather than offering half of it.
    """
    if definition.ceiling is None:
        raise _refused("ceiling", "missing", AN_UNMEASURED_SOURCE_IS_NOT_OFFERED)
    reading = CustomReading(definition)
    lookup = CustomLiveLookup(definition, reading)
    shape = definition.credential_shape

    def build(settings: Mapping[str, str], ref: SecretRef) -> ConnectorManifest:
        return manifest_of(definition, settings, ref)

    return ConnectorDeclaration(
        name=definition.name,
        label=definition.label,
        read_back=ReadBack(
            reading=classified_reading, recorded=(), findings=(NOTHING_IS_RECORDED,)
        ),
        recorded=Recorded(tested=False),
        console=ConsoleForm(
            settings=(
                Setting(
                    name=DEPARTMENT_FIELD,
                    label="Department",
                    hint=(
                        f"The department this connector was reviewed for, "
                        f"{definition.department}. Its people may be granted its records."
                    ),
                    refused=(
                        "That is not the department this connector was reviewed for. Type the "
                        "department its review names."
                    ),
                ),
            ),
            credential_label=(
                "No key" if shape is CredentialShape.NONE else f"The key {definition.label} issued"
            ),
            credential_hint=(
                "Ask the vendor for a key that can only read. It is kept in the vault and never "
                "shown again."
            ),
            build=build,
            credential_shape=shape,
        ),
        reading=reading,
        live=lookup if lookup.entities() else None,
        ask=ask_rows(definition),
        ceiling=ConnectorLimit(
            name=definition.name,
            per_minute=definition.ceiling.per_minute,
            per_day=definition.ceiling.per_day,
            raisable=False,
            note=f"As the vendor states it at {definition.ceiling.cited}",
        ),
    )
