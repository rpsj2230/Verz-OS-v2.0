"""What a connector module says about itself, and how the platform finds every one at start-up.

Until this module a connector was one module and four lists somewhere else. The console's list of
what can be connected was `brain.ops.connectable`, the read-backs were a table in
`brain.connectors.write_verification`, the scheduled readings were a table in
`brain.ops.connector_sync`, and what the Connectors screen says a connector was tested against was
a table in `brain.ops.connector_recordings`. Each was held total over the package by its own test,
so a new connector was a module plus four edits in four modules other packages were also editing,
plus a fifth list in a test file. **Now a connector declares all of it once, as `CONNECTOR` in its
own module, and every one of those tables is derived from the declarations `shipped` finds.** A new
connector is its module and its cassette file, and nothing else in the repository is touched.

**Found by walking `brain.connectors`, not by a plugin entry point.** These are the connectors this
product ships, reviewed in this repository and installed on every server. A company's own connector
is a plugin (`brain.plugins`), which is reviewed and installed per install and arrives through a
different door on purpose: a shipped declaration is evidence about this release, and a plugin's is
evidence about one company's.

**A malformed declaration stops start-up rather than being skipped.** A `CONNECTOR` that is not a
`ConnectorDeclaration`, or one filed under a module of another name, raises `DeclarationError`
from `shipped`, which the console and the worker both call as they start. Skipping it would take a
source off the screen silently, and "a connector nobody can see" reads exactly like "a connector
nobody shipped". A module that builds a manifest and declares nothing is a finding in
`declaration_gaps` and a red invariant, rather than a start-up failure, because it is a connector
somebody is still writing and the rest of the product has nothing to say about it yet.

**The owner's rule is part of the declaration's contract, and it is checked, not trusted.**
Connectors never bulk-sync: the Brain keeps a minimal index (ids, names, dates, status, and the
fields a manifest names up to its cap) and reads every value live at question time. Every declared
module's docstring says it `KEEPS_A_MINIMAL_INDEX`, and `declaration_gaps` refuses one that does
not; the words are the least of it, and `brain.connectors.minimal_index` is what proves them
against the rows a connector's own code keeps. See `CONNECTORS_NEVER_BULK_SYNC`.

**A connector says how one of its records is read live in the same declaration (M11.9.2).** `live`
is a `LiveLookup`: the entities read live while somebody waits, whose credentials each read runs
under (the requester's own unless it declares the service's, M11.2.5), and the arguments that
narrow the source's list operation to the one record an index row names. A connector adds it in its
own module, and nothing else in the repository is touched.

Rejected: one declaration per concern, each in the module that consumes it (a `READING` beside a
`READ_BACK` beside a `CONSOLE`). It moves the four lists into the connector without making them one
thing, so the rule that ties them (a scheduled reading needs a console form, because the connection
row is where its settings come from) would have nowhere to be stated.

**A reading is told its connection's settings when it builds its operation, and names how its key
is presented.** Both were fixed for every source until Freshdesk, whose address is the helpdesk's
own and whose key is sent as HTTP Basic rather than as a bearer token. The key still reaches one
header in the worker's run and nowhere else: a reading names a `KeyScheme` and never sees the key.
See `A_READING_NAMES_HOW_ITS_KEY_IS_SENT_AND_NEVER_HOLDS_IT`.

**A connector says how an administrator connects it, step by step, in the same declaration.**
`guide` is the screens the console's connect flow shows for this source, each with its words, a
picture of the vendor screen it happens on and a link to that page where the vendor has one
(`brain.ops.connect_steps`). A source connected from the console ends its guide with the screen
that holds its form, asking for exactly the form's settings and its key, so the steps and the
form cannot drift apart; a source connected at the server ends with the hand-over and asks for
nothing. See `A_GUIDE_ENDS_WHERE_THE_SOURCE_IS_CONNECTED`.

**A reading may list one entity under each record of another (M11.7.3).** Cloudflare lists a DNS
record only under its zone, so its reading says so with `ListedUnder`, the worker reads the entity
once per parent it kept earlier in the same run, and the index names each record by both ids. The
capability is optional and asked with `isinstance` (`ReadsListedUnder`), so no other reading
changes. See `A_RECORD_LISTED_UNDER_ANOTHER_IS_NAMED_BY_BOTH`.

Scope: domain logic. Nothing here opens a connection or reads a table; `shipped` imports the modules
of one package, and that is all it does.

Task ids: M11.1.1, M11.1.6, M11.9.1, M11.6.2, M11.9.2, M11.2.5, M27.11.9, M11.7.7, M11.7.3
"""

from __future__ import annotations

import enum
import importlib
import inspect
import pkgutil
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import cache
from types import MappingProxyType, ModuleType
from typing import Any, Final, Protocol, runtime_checkable

import brain.connectors
from brain.connectors.contract import ConnectorContractError
from brain.connectors.manifest import ConnectorManifest
from brain.connectors.projection import ProjectedRecord
from brain.connectors.rest import RestOperation
from brain.connectors.throttle import CallOutcome
from brain.connectors.transports import SourceRecord
from brain.connectors.write_verification import ReadBack, builds_a_manifest
from brain.core.envelope import OBJECT_NAME_PATTERN, IdentityMode, TypedResult
from brain.ops.connect_steps import GuideStep
from brain.ops.secrets import SecretRef
from brain.tools.fetch import Resolver

# ------------------------------------------------------------------ written-down reasons
#: The owner's rule, stated on 18 and 21 September and restated in every connector brief since.
CONNECTORS_NEVER_BULK_SYNC: Final = (
    "Connectors never bulk-sync. The Brain keeps a minimal index of a source (identifiers, "
    "display names, dates, status, and the fields its manifest names up to the twelve-field cap) "
    "and reads every value live from the source at question time, at the asker's reach. No "
    "document body and no business value from a source is stored, embedded or logged."
)

#: The words every declared connector module's docstring carries. Checked as a phrase because it
#: is the owner's own phrasing; what makes it true is `brain.connectors.minimal_index`.
KEEPS_A_MINIMAL_INDEX: Final = "keeps a minimal index and reads every value live"

#: Why a scheduled reading needs a console form.
A_READING_NEEDS_A_CONNECTION_TO_READ: Final = (
    "The worker reads a source from the connection an administrator made on the Connectors "
    "screen: its settings are that row's, its key is the slot that connection wrote, and its "
    "pinned digest is the manifest those settings built. A source the console cannot connect has "
    "no such row, so a reading declared for it is a reading nothing can ever start."
)

#: Why a reading declares a scheme rather than building the header itself.
A_READING_NAMES_HOW_ITS_KEY_IS_SENT_AND_NEVER_HOLDS_IT: Final = (
    "Sources take a key in different shapes: a bearer token, or HTTP Basic with the key as the "
    "user name. A reading that built the header would be handed the key, and a reading is an "
    "object a later edit can make keep it. So a reading names one of a closed set of schemes, "
    "and the worker's run, which already holds the key for one request, is the only code that "
    "writes it into a header. A new scheme is a new member here, reviewed where the key is "
    "handled."
)

#: Why a guide's last screen is where the source is connected, and what it asks for.
A_GUIDE_ENDS_WHERE_THE_SOURCE_IS_CONNECTED: Final = (
    "A source connected from the console ends its guide with the screen holding its form, and "
    "that screen asks for exactly the form's settings and its key, so a setting added to the "
    "form is a step's field too. A source connected at the server ends with the hand-over and "
    "asks for nothing, because this screen has nothing to take."
)

#: What the last screen of a console source's guide asks for besides its settings.
CREDENTIAL_ASK: Final = "credential"

#: The name every connector module declares itself under.
DECLARATION_ATTRIBUTE: Final = "CONNECTOR"

_NAME_RE: Final = re.compile(OBJECT_NAME_PATTERN)


class DeclarationError(ConnectorContractError):
    """A connector declared itself in a shape the platform cannot hold. Raised at start-up."""


class SettingRefusedError(ConnectorContractError):
    """A connector refused one console setting, and says which.

    A form asking for two settings cannot otherwise say which one was wrong: the console would mark
    both, and a person would retype the one that was right. `brain.ops.connectable` shows only the
    named setting's `refused` sentence, and never this message, which may quote what was typed.
    """

    def __init__(self, message: str, *, setting: str) -> None:
        super().__init__(message)
        self.setting = setting


class KeyScheme(enum.StrEnum):
    """How the worker's run presents a source's key. See
    `A_READING_NAMES_HOW_ITS_KEY_IS_SENT_AND_NEVER_HOLDS_IT`."""

    #: `Authorization: Bearer <key>`, which Xero and HubSpot take.
    BEARER = "bearer"
    #: HTTP Basic with the key as the user name and `X` as the password, which is how Freshdesk
    #: documents its API key (https://developers.freshdesk.com/api/#authentication).
    BASIC_KEY_AS_USER = "basic_key_as_user"


# ---------------------------------------------------------------- connecting from the console
class CredentialShape(enum.StrEnum):
    """What a source's credential is, as the console collects it and the vault keeps it (M11.7.7).

    Closed, because each member is a way the console asks and a judgement before anything is sent.
    Until 2026-09-30 every source took one unbroken key, and the two that did not (a service
    account key file, a database user's name and password) could only be connected at the server.
    See `A_CREDENTIAL_IS_ASKED_FOR_IN_THE_SHAPE_THE_SOURCE_ISSUES_IT`.
    """

    #: One unbroken key, pasted: Xero's, HubSpot's, Freshdesk's.
    KEY = "key"
    #: A key file the vendor issues, chosen as a file and kept whole: a service account's JSON.
    KEY_FILE = "key_file"
    #: A user's name and password, typed as two: a read-only database user.
    DATABASE_USER = "database_user"


#: Why a credential is asked for in its own shape rather than as one pasted key.
A_CREDENTIAL_IS_ASKED_FOR_IN_THE_SHAPE_THE_SOURCE_ISSUES_IT: Final = (
    "A key is pasted, a key file is chosen as a file, and a database user is typed as a name and a "
    "password, because that is how each is issued. Asking for a key file as a pasted key would "
    "have a person copy a private key through a text box, and asking for a name and password as "
    "one string would have them invent a separator. Each shape is judged before anything is sent "
    "and kept in the vault whole, and none is ever shown again."
)


@dataclass(frozen=True)
class Setting:
    """One identifier a source is connected with: its name, its label, and where to find it."""

    name: str
    label: str
    hint: str
    #: What a person is told when the connector refuses what was typed here.
    refused: str
    #: Whether the value is a person's id here, which the connect route checks names somebody live
    #: on this install before anything is written (M11.7.7). A connector cannot: it reads no table.
    names_a_person: bool = False


@dataclass(frozen=True)
class ConsoleForm:
    """What the Connectors screen asks for to connect this source, and how it builds the manifest.

    `build` takes the settings, already given and fitting, and the reference to where the key is
    kept, and returns the manifest or raises the connector's own refusal.
    """

    settings: tuple[Setting, ...]
    credential_label: str
    credential_hint: str
    build: Callable[[Mapping[str, str], SecretRef], ConnectorManifest]
    #: How the credential is asked for and kept. One key unless the source issues another shape.
    credential_shape: CredentialShape = CredentialShape.KEY

    def __post_init__(self) -> None:
        if not self.settings:
            msg = (
                "a console form asks for no setting, so the manifest it builds would be scoped "
                "by whatever the key happens to reach; scope is fixed at connect"
            )
            raise DeclarationError(msg)
        if not (self.credential_label.strip() and self.credential_hint.strip()):
            msg = "a console form must say which key it asks for and what that key may do"
            raise DeclarationError(msg)


# ------------------------------------------------------------------ what the tests were run on
@dataclass(frozen=True)
class Recorded:
    """What this connector was tested against in this release, as the Connectors screen says it.

    Declared rather than computed, because the recordings are `tests/fixtures/cassettes/`, which
    is not shipped in the image; `tests/unit/test_cassette_replay.py` compares every declaration
    with the corpus, so the sentence cannot outlive the evidence behind it without a red build.
    `brain.ops.connector_recordings` holds the words.
    """

    tested: bool
    live_capture: bool = False
    #: Declared behaviour no recording can replay yet, each with the reason.
    not_replayed: tuple[str, ...] = ()
    #: What replaying the recordings found the connector does with them, when a reader who saw
    #: only "tested" would expect otherwise. Pinned by a test in the replay file.
    finding: str = ""


# ------------------------------------------------------------------ reading on a schedule
@dataclass(frozen=True)
class PageReply:
    """One page, as the connector's own `interpret` read it: the call's outcome and any rows."""

    call: CallOutcome
    rows: TypedResult[SourceRecord] | None


class SourceReading(Protocol):
    """How the worker reads one source page by page, into its minimal index and nothing else.

    Everything a reading does is a connector's own function called with the right arguments: the
    operation, the paging parameters, the one header a connection contributes, the interpretation
    of a response and the projection of a row. A reading decides nothing about who may see a row,
    which is the manifest's predicate and the reader's grant, and holds no key.

    **There is no method returning a document, and adding one is the regression.** A reading once
    also handed each row to the corpus as a document; that was the bulk sync the owner's rule
    forbids, and it was removed with this declaration. See `CONNECTORS_NEVER_BULK_SYNC`.
    """

    def entities(self) -> tuple[str, ...]:
        """Every entity kind the source projects, in the order a run reads them."""
        ...

    def refresh_interval(self) -> timedelta:
        """How often a healthy source is read, which is the interval its freshness is judged by."""
        ...

    def operation(
        self, entity: str, *, settings: Mapping[str, str], resolver: Resolver
    ) -> RestOperation:
        """The bound operation that lists one entity kind, at the address the connection names."""
        ...

    def key_scheme(self) -> KeyScheme:
        """How the worker's run sends this source's key. The reading never sees the key."""
        ...

    def first_page(self, entity: str) -> Mapping[str, str]:
        """The arguments of the first page of one entity kind."""
        ...

    def next_page(
        self, entity: str, asked: Mapping[str, str], body: Any, returned: int
    ) -> Mapping[str, str] | None:
        """The arguments of the page after this one, or None when this was the last."""
        ...

    def call_headers(self, settings: Mapping[str, str]) -> Mapping[str, str]:
        """The headers the connection contributes to a call. Never `Authorization`."""
        ...

    def interpret(
        self, operation: RestOperation, *, status: int, body: Any, fetched_at: str
    ) -> PageReply:
        """One answered call, as the connector's own `interpret` classifies it."""
        ...

    def retry_after(self, headers: Mapping[str, str]) -> float | None:
        """What the source asked to wait, or None when it said nothing."""
        ...

    def allowance_spent(self, headers: Mapping[str, str]) -> bool:
        """Whether the source said its allowance is spent, on an answer that was not a refusal."""
        ...

    def projected(
        self, entity: str, row: Mapping[str, Any], *, seen_at: datetime
    ) -> ProjectedRecord | None:
        """The index entry kept for one row, or None for a row with nothing to keep."""
        ...


# ---------------------------------------------------------- a record listed under another
#: Why an entity may be read under each record of another, and is named by both ids.
A_RECORD_LISTED_UNDER_ANOTHER_IS_NAMED_BY_BOTH: Final = (
    "Some sources list a record only under another: Cloudflare lists a DNS record under its zone, "
    "and neither its list nor its one-record call can be reached without the zone's id. So the "
    "worker reads such an entity once under each record of its parent kept earlier in the same "
    "run, with the parent's id laid into the path, and the index names the record by both ids, "
    "the parent's first. A question then reads the record live from its index row alone, and the "
    "record read live is named the same way, so the one is matched to the other."
)

#: What joins a parent's id to the record's own in the id the index keeps. A dot, because the
#: joined id is still a record id the redactor cites by (`brain.core.redaction`'s id grammar is
#: letters, digits and `_.@-`), and a record it cannot cite is dropped whole. A slash was the first
#: choice and the Cloudflare install check found every live record dropped as unidentified.
LISTED_UNDER_SEPARATOR: Final = "."


@dataclass(frozen=True)
class ListedUnder:
    """Where one entity's records are listed: under each record of `parent`, by `parameter`.

    See `A_RECORD_LISTED_UNDER_ANOTHER_IS_NAMED_BY_BOTH`. The id both halves agree on is built and
    taken apart here and nowhere else, so the worker's walk and the live read cannot come to name
    one record two ways.
    """

    parent: str
    #: The path parameter the parent's id is laid into, and the field it is carried in on a row.
    parameter: str

    def __post_init__(self) -> None:
        for one in (self.parent, self.parameter):
            if not _NAME_RE.match(one):
                msg = f"{one!r} is not a name, and a record listed under another is named by it"
                raise DeclarationError(msg)

    def source_id(self, parent_id: str, own_id: str) -> str:
        """The id the index keeps for a record of this entity read under `parent_id`."""
        for one in (parent_id, own_id):
            if not one.strip() or LISTED_UNDER_SEPARATOR in one:
                msg = (
                    "an id holding nothing or the separator cannot be joined, because the joined "
                    "id would be taken apart differently. "
                    f"{A_RECORD_LISTED_UNDER_ANOTHER_IS_NAMED_BY_BOTH}"
                )
                raise ConnectorContractError(msg)
        return f"{parent_id}{LISTED_UNDER_SEPARATOR}{own_id}"

    def split(self, source_id: str) -> tuple[str, str]:
        """The parent's id and the record's own, from the id the index keeps."""
        parent_id, joined, own_id = source_id.partition(LISTED_UNDER_SEPARATOR)
        if not (joined and parent_id.strip() and own_id.strip()) or (
            LISTED_UNDER_SEPARATOR in own_id
        ):
            msg = (
                f"an id of a {self.parent}'s record names its {self.parent} and itself, and this "
                "one does not"
            )
            raise ConnectorContractError(msg)
        return parent_id, own_id

    def named(self, rows: TypedResult[SourceRecord], parent_id: str) -> TypedResult[SourceRecord]:
        """Rows read under `parent_id`, each named by both ids and carrying the parent's id."""
        return TypedResult[SourceRecord](
            records=tuple(
                SourceRecord.model_validate(
                    {
                        **one.model_dump(),
                        "id": self.source_id(parent_id, one.id),
                        self.parameter: parent_id,
                    }
                )
                for one in rows.records
            ),
            source=rows.source,
            fetched_at=rows.fetched_at,
            truncated=rows.truncated,
        )


@runtime_checkable
class ReadsListedUnder(Protocol):
    """A reading one of whose entities is listed under each record of another.

    Optional, and asked with `isinstance`, so a reading whose every entity is listed on its own
    says nothing and needs no change.
    """

    def listed_under(self, entity: str) -> ListedUnder | None:
        """Where `entity` is listed, or None for an entity listed on its own."""
        ...


def listed_under(reading: object, entity: str) -> ListedUnder | None:
    """How this reading lists `entity`: under a parent, or on its own (None)."""
    if isinstance(reading, ReadsListedUnder):
        return reading.listed_under(entity)
    return None


# ------------------------------------------------------------------ reading one record live
#: Why a live lookup may name an operation of its own.
A_RECORD_IS_READ_BY_THE_CALL_THAT_HOLDS_IT: Final = (
    "A record is read live by the source's own call for one record where the source has one and "
    "its list cannot be narrowed to one id, or does not carry what a question asks for. The "
    "reading's interpretation of the reply is still the one used, so a record read live and a "
    "page read on a schedule are understood the same way; only the address differs."
)


class LiveLookup(Protocol):
    """How one record an index row names is read from the source while somebody waits (M11.9.2).

    Only the narrowing is the lookup's own. The operation, the headers a connection contributes and
    the interpretation of the reply are the source's `SourceReading`, which is why a declaration
    with a lookup must also declare a reading: a record read live and a page read on a schedule
    are one call to the same endpoint, and two interpretations of one reply would be two answers
    to what the source said.
    """

    def entities(self) -> tuple[str, ...]:
        """Every entity kind whose records are read live."""
        ...

    def identity_mode(self, entity: str) -> IdentityMode:
        """Whose credentials a live read of this entity runs under (M11.2.5).

        The requester's own (`contract.identity_mode_default`) unless the connector declares the
        service's, and a service read is only ever made with the connection's own key.
        """
        ...

    def arguments_for(self, entity: str, source_id: str) -> Mapping[str, str]:
        """The arguments that name the one record with this id.

        The list operation's, narrowed, where `operation` answers None; otherwise the arguments
        of the operation it answers. Raises for an id that is not the shape the source issues,
        because an id is laid into the source's own query language or address, and a value that
        could change either is refused here rather than escaped.
        """
        ...

    def operation(
        self, entity: str, *, settings: Mapping[str, str], resolver: Resolver
    ) -> RestOperation | None:
        """The operation one record is read by, or None to narrow the reading's list operation.

        Its own operation where the list cannot be narrowed to one record, or does not carry the
        values a question asks for: a helpdesk's ticket list names no ticket by id and carries no
        body, and its one-ticket read does both. See `A_RECORD_IS_READ_BY_THE_CALL_THAT_HOLDS_IT`.
        """
        ...


# ------------------------------------------------------------------------ the declaration
@dataclass(frozen=True)
class ConnectorDeclaration:
    """Everything the platform needs to know about one shipped connector, in its own module.

    `console` and `not_from_the_console` are exactly one: a source either has a form an
    administrator fills in on the Connectors screen, or a sentence saying why it has none yet. The
    screen shows the sentence rather than leaving the source out, so "not connectable here" is
    never confused with "not shipped".
    """

    name: str
    label: str
    read_back: ReadBack
    recorded: Recorded
    console: ConsoleForm | None = None
    #: Why the console cannot connect this source yet. Empty exactly when `console` is set.
    not_from_the_console: str = ""
    #: How the worker reads it on a schedule, or None when nothing does.
    reading: SourceReading | None = None
    #: How one of its records is read live at question time, or None when none is.
    live: LiveLookup | None = None
    #: The screens the console's connect flow shows for it. See the module docstring.
    guide: tuple[GuideStep, ...] = ()

    def __post_init__(self) -> None:
        if not _NAME_RE.match(self.name):
            msg = f"connector {self.name!r} is not a name"
            raise DeclarationError(msg)
        if not self.label.strip():
            msg = f"connector {self.name!r} has no label, and the screen shows the label"
            raise DeclarationError(msg)
        if (self.console is None) == (not self.not_from_the_console.strip()):
            msg = (
                f"connector {self.name!r} must either give a console form or say why it has none, "
                "and this declaration does both or neither"
            )
            raise DeclarationError(msg)
        if self.reading is not None and self.console is None:
            msg = (
                f"connector {self.name!r} declares a reading. "
                f"{A_READING_NEEDS_A_CONNECTION_TO_READ}"
            )
            raise DeclarationError(msg)
        if self.guide:
            last = self.guide[-1].asks
            wanted = (
                ()
                if self.console is None
                else (*(one.name for one in self.console.settings), CREDENTIAL_ASK)
            )
            if tuple(last) != wanted:
                msg = (
                    f"connector {self.name!r} ends its guide asking for {list(last)}, and "
                    f"its form takes {list(wanted)}. {A_GUIDE_ENDS_WHERE_THE_SOURCE_IS_CONNECTED}"
                )
                raise DeclarationError(msg)
        if self.live is not None and self.reading is None:
            msg = (
                f"connector {self.name!r} declares a live lookup and no reading; a record read "
                "live is read through the reading's operation and interpretation"
            )
            raise DeclarationError(msg)
        if self.reading is not None:
            read = self.reading.entities()
            for index, entity in enumerate(read):
                under = listed_under(self.reading, entity)
                if under is not None and under.parent not in read[:index]:
                    msg = (
                        f"connector {self.name!r} lists {entity!r} under {under.parent!r}, which "
                        "it does not read first, so the walk would have no parent to list it "
                        f"under. {A_RECORD_LISTED_UNDER_ANOTHER_IS_NAMED_BY_BOTH}"
                    )
                    raise DeclarationError(msg)


# ------------------------------------------------------------------------ discovery
def discover(package: ModuleType) -> Mapping[str, ConnectorDeclaration]:
    """Every `CONNECTOR` declared by a module of this package, by module name, sorted.

    A parameter rather than a constant, so a test can point it at a package of its own and watch
    a malformed declaration refused.
    """
    found: dict[str, ConnectorDeclaration] = {}
    for info in pkgutil.iter_modules(package.__path__):
        module = importlib.import_module(f"{package.__name__}.{info.name}")
        declared = getattr(module, DECLARATION_ATTRIBUTE, None)
        if declared is None:
            continue
        if not isinstance(declared, ConnectorDeclaration):
            msg = (
                f"{module.__name__}.{DECLARATION_ATTRIBUTE} is a {type(declared).__name__}, not "
                "a ConnectorDeclaration, so this connector cannot be listed, read or checked"
            )
            raise DeclarationError(msg)
        if declared.name != info.name:
            msg = (
                f"{module.__name__} declares itself as {declared.name!r}; a connector is found "
                "by its module's name, and the cassette file, the key slot and the screen all "
                "look it up by that one string"
            )
            raise DeclarationError(msg)
        found[info.name] = declared
    return MappingProxyType(dict(sorted(found.items())))


@cache
def shipped() -> Mapping[str, ConnectorDeclaration]:
    """Every connector this release ships. Found once per process, at start-up."""
    return discover(brain.connectors)


def read_backs() -> Mapping[str, ReadBack]:
    """Every shipped connector's read-back, which `write_verification.read_back_gaps` is held to."""
    return MappingProxyType({name: one.read_back for name, one in shipped().items()})


def declaration_gaps(package: ModuleType = brain.connectors) -> tuple[str, ...]:
    """Every way a module of this package and the declarations disagree. Empty when they agree.

    Three findings. A module that builds a manifest and declares nothing is a connector the
    platform cannot see. A declared module that builds no manifest is a declaration of nothing.
    And a declared module whose docstring does not say it `KEEPS_A_MINIMAL_INDEX` has not made the
    owner's rule its own; `brain.connectors.minimal_index` is what proves the rule, and this is
    what makes every author write it down first.
    """
    declared = discover(package)
    gaps: list[str] = []
    for info in pkgutil.iter_modules(package.__path__):
        module = importlib.import_module(f"{package.__name__}.{info.name}")
        builds = builds_a_manifest(module)
        if builds and info.name not in declared:
            gaps.append(
                f"{module.__name__} builds a manifest and declares no {DECLARATION_ATTRIBUTE}, so "
                "the Connectors screen, the worker and the read-back table cannot see it"
            )
        if info.name in declared and not builds:
            gaps.append(
                f"{module.__name__} declares {DECLARATION_ATTRIBUTE} and builds no manifest"
            )
        text = " ".join((inspect.getdoc(module) or "").split())
        if info.name in declared and KEEPS_A_MINIMAL_INDEX not in text:
            gaps.append(
                f"{module.__name__}'s docstring does not say it {KEEPS_A_MINIMAL_INDEX}. "
                f"{CONNECTORS_NEVER_BULK_SYNC}"
            )
    return tuple(gaps)
