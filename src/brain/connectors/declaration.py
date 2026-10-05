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

**A source that is views in a company's own database is read by a `ViewReading`, which is a small
typed branch of the one worker loop rather than a second loop (M11.6.1).** A REST reading hands the
worker an operation, a page's arguments and one header, and the worker makes the call. A database
has no operation, no page and no header: one read of one view is one bounded statement, and what the
worker holds for it is a user and a password. So `reading` is either shape, the worker, the test
of a connection and the live read each branch on which it is, and everything else about a reading
(the entities, the interval, the projection into the minimal index, the ceiling admitting each read,
the lease on the credential) is the same code for both. The login is a `DatabaseLogin` the worker
builds from the lease for one attempt, sealed so a traceback prints no password. See
`A_DATABASE_IS_READ_BY_THE_SAME_LOOP`. Rejected: a second worker loop for databases, which would
be a second copy of the admission, the lease, the page write and the backoff, each free to drift
from the first; and a `RestOperation` that pretended a view read was a GET, which would put a
statement's parts in a URL.

**A write a connector can make is a grant of its own (M11.7.3).** `writes` declares each, with the
key it asks for and what an approver is told without it; the key is kept in a slot of its own and
the grant is off until it is given. See `A_WRITE_IS_A_GRANT_OF_ITS_OWN_WITH_A_KEY_OF_ITS_OWN`.

**A reading may list one entity under each record of another (M11.7.3).** Cloudflare lists a DNS
record only under its zone, so its reading says so with `ListedUnder`, the worker reads the entity
once per parent it kept earlier in the same run, and the index names each record by both ids. The
capability is optional and asked with `isinstance` (`ReadsListedUnder`), so no other reading
changes. See `A_RECORD_LISTED_UNDER_ANOTHER_IS_NAMED_BY_BOTH`.

**A source whose values are figures, not records, says how its figures are read (M11.7.1).**
Google Analytics keeps an index of one property and answers a question with that property's
traffic for a named date range, which is not the property read again: it is a report, asked for
with a body, from another endpoint than the index's. `report` is a `LiveReport`: the entities whose
figures are read that way, whose credentials, and the one call and its interpretation. It is a
second field beside `live` rather than a second shape of `LiveLookup`, because a lookup's rule (the
record read live is the index's own endpoint, interpreted once) is right for a record and is exactly
what a report is not; one entity is read one way, and the declaration refuses both for one entity.
See `A_FIGURE_IS_READ_BY_A_REPORT_AND_A_RECORD_BY_ITS_OWN_ENDPOINT`.

**And a source whose key is a service account's key file names a scope for the token it is
exchanged for.** `KeyScheme.GOOGLE_SERVICE_ACCOUNT` is presented as a bearer token the run mints
from the key file for one read (`brain.connectors.google_token`), and a reading naming it is a
`ScopedReading`, which says which read-only scope that token carries. See
`A_READING_NAMES_THE_SCOPE_ITS_KEY_FILE_IS_EXCHANGED_FOR`.

**And a connector says what the rest of the product used to type about it by hand (M11.1.6).**
Its Ask rows (`ask`, `brain.connectors.ask`), the scopes its vault slot is defined with (`scopes`),
and the settings a test or an acceptance check connects it with (`ConsoleForm.example`). Each was a
literal in a module or a test that every connector PR appended to, so every connector that landed
put every other open one in conflict. See `A_CONNECTOR_IS_ITS_OWN_MODULE_AND_ITS_OWN_FIXTURES`.

**A source that is an MCP server's tools, or that only custom code can read, is a reading of its
own shape (M11.1.2, M11.1.5).** `ToolReading` and `CodeReading` are the other two transports of
`brain.connectors.transports`, read by one more typed branch of the same worker loop and the same
live read; `Reading` is the four together. Neither reading holds a key or a socket: an MCP session
and a custom connector's planned calls are made by the run, and a custom connector's code runs in
a sandbox that is never handed the key (`brain.connectors.custom_code`).

Scope: domain logic. Nothing here opens a connection or reads a table; `shipped` imports the modules
of one package, and that is all it does.

Task ids: M11.1.1, M11.1.6, M11.9.1, M11.6.2, M11.9.2, M11.2.5, M27.11.9, M11.7.7, M11.7.4, M11.6.1
Task ids: M11.7.3, M11.7.1, M11.1.2, M11.1.5
"""

from __future__ import annotations

import enum
import importlib
import inspect
import pkgutil
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from functools import cache
from types import MappingProxyType, ModuleType
from typing import TYPE_CHECKING, Any, Final, Protocol, runtime_checkable

import brain.connectors
from brain.connectors.ask import AskRows
from brain.connectors.contract import ConnectorContractError, FetchRequest
from brain.connectors.date_range import DateWindow
from brain.connectors.manifest import ConnectorManifest
from brain.connectors.projection import ProjectedRecord
from brain.connectors.resolves import ResolvesAs
from brain.connectors.rest import RestOperation
from brain.connectors.throttle import CallOutcome
from brain.connectors.transports import SourceRecord
from brain.connectors.write_verification import ReadBack, builds_a_manifest
from brain.core.envelope import OBJECT_NAME_PATTERN, IdentityMode, TypedResult
from brain.ops.connect_steps import GuideStep
from brain.ops.leases import SealedSecret
from brain.ops.limits import ConnectorLimit
from brain.ops.secrets import SecretRef
from brain.tools.fetch import Resolver

if TYPE_CHECKING:
    from brain.connectors.custom_code import PlannedCall
    from brain.gate.leash import Action
    from brain.tools.run_skill import SandboxSpec

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

#: Why a database's views are read by a branch of the one worker loop, not by a loop of their own.
A_DATABASE_IS_READ_BY_THE_SAME_LOOP: Final = (
    "A source that is views in a company's own database is read one bounded statement per view, "
    "with a user and a password rather than a key in a header. Everything else about reading it is "
    "what every source has: the ceiling admits each read, the credential is leased for the attempt "
    "and given back, each record is held to the minimal index before it is written, and a failure "
    "backs off. So the worker, the connection test and the live read each take one typed branch "
    "for it, and a second loop that would copy all of that is not written."
)

#: Why a source's figures are declared apart from its records.
A_FIGURE_IS_READ_BY_A_REPORT_AND_A_RECORD_BY_ITS_OWN_ENDPOINT: Final = (
    "A record read live is the index's own endpoint asked for one id and read by the same "
    "interpretation, so the two cannot come to disagree about what the source said. A figure is "
    "not the record read again: it is a report over a date range, asked for with a body from "
    "another endpoint. So a declaration names its figures as a report of their own, and one "
    "entity is read live one way or the other, never both."
)

#: Why a reading presented as a minted token names the token's scope.
A_READING_NAMES_THE_SCOPE_ITS_KEY_FILE_IS_EXCHANGED_FOR: Final = (
    "A service account's key file is exchanged for a token carrying the scopes asked for, and "
    "which scope a source's reads need is a fact about that source. The run that mints the token "
    "is shared by every source, so the scope comes from the reading, which is the source's own "
    "declaration, and a reading naming the Google scheme without one is refused before any key "
    "is read."
)

#: Why the lists that named every connector are read off the declarations.
A_CONNECTOR_IS_ITS_OWN_MODULE_AND_ITS_OWN_FIXTURES: Final = (
    "Every list that names each connector is a place two connector changes edit at once, and on "
    "2026-10-05 six open connector changes conflicted in such lists one after another. So what a "
    "connector is asked about, the scopes its key may carry and the settings it is connected with "
    "in a test are declared in its own module, and every list is derived from the declarations, "
    "so adding a connector is its module and its own test and fixture files."
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
    #: No key at all: a source whose publisher gives its record to anybody who asks, as a registry
    #: gives its RDAP record (M11.7.4). The worker takes no lease and sends no `Authorization`.
    NONE = "none"
    #: A service account's key file, exchanged by the run for a bearer token carrying the
    #: reading's scope (`ScopedReading`) and sent as `Authorization: Bearer <token>`, which is how
    #: Google documents a server reading its APIs as itself
    #: (https://developers.google.com/identity/protocols/oauth2/service-account). The key file is
    #: never sent: see `brain.connectors.google_token.A_KEY_FILE_IS_NEVER_SENT_IN_A_HEADER`.
    GOOGLE_SERVICE_ACCOUNT = "google_service_account"


#: The schemes a key is sent in as it is, with no exchange first. An MCP or custom-code reading
#: names one of these: only a REST reading says which scope a key file's token carries.
SCHEMES_SENT_AS_THEY_ARE: Final = frozenset(
    {KeyScheme.BEARER, KeyScheme.BASIC_KEY_AS_USER, KeyScheme.NONE}
)


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
    #: Nothing: the source's record is published to anybody who asks, and nothing is kept in the
    #: vault because there is nothing to keep (M11.7.4). The form says so and asks for nothing.
    NONE = "none"


#: Why a credential is asked for in its own shape rather than as one pasted key.
A_CREDENTIAL_IS_ASKED_FOR_IN_THE_SHAPE_THE_SOURCE_ISSUES_IT: Final = (
    "A key is pasted, a key file is chosen as a file, and a database user is typed as a name and a "
    "password, because that is how each is issued. Asking for a key file as a pasted key would "
    "have a person copy a private key through a text box, and asking for a name and password as "
    "one string would have them invent a separator. Each shape is judged before anything is sent "
    "and kept in the vault whole, and none is ever shown again."
)


#: The longest setting accepted unless a setting says otherwise, which is `ConnectorScope`'s own
#: ceiling on a selector.
DEFAULT_SETTING_CHARS: Final = 200


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
    #: The longest value accepted. A list the connection is scoped to, such as the domains a
    #: domains connection reads, is longer than one identifier (M11.7.4), and so is a certificate
    #: authority's certificate (M11.6.1).
    max_chars: int = DEFAULT_SETTING_CHARS


@dataclass(frozen=True)
class ConnectExample:
    """The settings a test or an acceptance check connects this source with.

    `settings` are fixed and name nobody, shaped as the source's own identifiers would be, and are
    what every unit test builds this source's manifest from. `fresh` is what an acceptance check on
    a running install connects it with: identifiers nothing else holds, made up per call, with
    every department taken from `departments`, which are the ones that check may write grants in.
    `edit` is the setting a person would change after connecting, and `edited` a new value for it.
    """

    settings: Mapping[str, str]
    fresh: Callable[[Sequence[str]], dict[str, str]]
    edit: str
    edited: Callable[[], str]

    def __post_init__(self) -> None:
        if self.edit not in self.settings:
            msg = f"an example edits {self.edit!r}, which is not one of its settings"
            raise DeclarationError(msg)


@dataclass(frozen=True)
class KeyScopes:
    """What a source's key must be allowed to do, and what it must never be given.

    The vault slot `brain.ops.connector_slots` defines for the source carries these as its
    metadata, and the form's credential hint names every one it requests.
    """

    request: tuple[str, ...]
    refuse: tuple[str, ...]


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
    #: What a test or an acceptance check connects it with. See `ConnectExample`.
    example: ConnectExample | None = None

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
        if self.example is not None:
            asked = [one.name for one in self.settings]
            if sorted(self.example.settings) != sorted(asked):
                msg = (
                    f"a console form asks for {asked} and its example gives "
                    f"{sorted(self.example.settings)}"
                )
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


#: Why a reading may send each page to a server of its own.
A_PAGE_MAY_BE_READ_FROM_ITS_OWN_SERVER: Final = (
    "Most sources are one service, so a reading's pages all go to one address. A registry's RDAP "
    "record is not: each top-level domain is published by its own registry at its own address, "
    "so a domains connection's pages go one to a domain, each to the server that domain's "
    "registry publishes. A routed reading is told the connection's settings for every page, "
    "because the pages are the connection's own list, and a domain it cannot route is written "
    "into the index as unpublished without a call rather than left out."
)


@runtime_checkable
class RoutedReading(Protocol):
    """A reading whose pages each go to a server of their own (M11.7.4).

    The worker's run and the live read ask a reading that is one of these for each page's
    operation, and for the first and next page with the connection's settings; every other method
    is `SourceReading`'s. See `A_PAGE_MAY_BE_READ_FROM_ITS_OWN_SERVER`.
    """

    def first_route(self, entity: str, *, settings: Mapping[str, str]) -> Mapping[str, str] | None:
        """The arguments of the first page this connection reads, or None when it reads none."""
        ...

    def next_route(
        self, entity: str, asked: Mapping[str, str], *, settings: Mapping[str, str]
    ) -> Mapping[str, str] | None:
        """The arguments of the page after `asked`, or None when that was the last."""
        ...

    def operation_for(
        self,
        entity: str,
        page: Mapping[str, str],
        *,
        settings: Mapping[str, str],
        resolver: Resolver,
    ) -> RestOperation:
        """The operation one page is read by, at the server that page's record is published at."""
        ...

    def unrouted(
        self, entity: str, *, settings: Mapping[str, str], seen_at: datetime
    ) -> tuple[ProjectedRecord, ...]:
        """The index entries of records no server publishes, kept without a call."""
        ...

    def unpublished(
        self, entity: str, source_id: str, *, settings: Mapping[str, str], fetched_at: str
    ) -> TypedResult[SourceRecord] | None:
        """What a live read of a record no server publishes is told, or None for a routed one.

        The record said as unpublished, read with no call, so a question about it is answered
        with that rather than with a source that could not be reached.
        """
        ...


class OneCall(Protocol):
    """One GET, as the worker's and the live read's caller makes it. Never raises."""

    def get(self, url: str, *, address: str, headers: Mapping[str, str], max_bytes: int) -> Any:
        """The answer: a status, headers and a body, or that it came back not at all."""
        ...


@runtime_checkable
class ChecksLiveFacts(Protocol):
    """A live lookup that adds facts read from somewhere other than its source's record (M11.7.4).

    A domain's registry says who registered it and until when; whether its site answers is asked
    of the site itself. The facts are values read for the question and kept nowhere, like every
    other value a live read returns.
    """

    def facts(
        self, entity: str, source_id: str, *, caller: OneCall, resolver: Resolver
    ) -> Mapping[str, str]:
        """The facts one record carries besides its source's record, by field name."""
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


@runtime_checkable
class ScopedReading(Protocol):
    """A reading whose key is exchanged for a token, and the read-only scopes that token carries.

    Asked for only when `SourceReading.key_scheme` is `KeyScheme.GOOGLE_SERVICE_ACCOUNT`. Checked
    at run time rather than added to `SourceReading`, so a source whose key is sent as it is owes
    nothing here. See `A_READING_NAMES_THE_SCOPE_ITS_KEY_FILE_IS_EXCHANGED_FOR`.
    """

    def token_scopes(self) -> tuple[str, ...]:
        """The scopes the token minted for this source's reads carries. Read-only, every one."""
        ...


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


# ------------------------------------------------------------ reading a database's views
class DatabaseLogin:
    """A database user's name and password, for the reads of one attempt, and nothing else.

    Built by whoever holds the lease, from the slot's two fields
    (`brain.ops.credentials.user_and_password`), and handed to a `ViewReading` for as long as the
    attempt's reads take. The password stays a `SealedSecret` until the one line that opens the
    connection reveals it, and this object has no rendering of its own that could show it, so a
    traceback or a log line holding one prints the user and not the password. Not a dataclass, for
    `SealedSecret`'s reason: a generated `__repr__` is a rendering nobody chose.
    """

    __slots__ = ("password", "user")

    def __init__(self, user: str, password: SealedSecret) -> None:
        if not user.strip():
            msg = "a database login names no user; the vault holds the password beside a user"
            raise ConnectorContractError(msg)
        self.user = user
        self.password = password

    def __repr__(self) -> str:
        return f"DatabaseLogin(user={self.user!r})"

    __str__ = __repr__


@runtime_checkable
class ViewReading(Protocol):
    """How the worker reads a source that is views in a company's own database (M11.6.1).

    One bounded read per entity: the connector's `read` builds the read from the connection's
    settings, checks the address the connection names, runs it through its own executor and
    classifies the answer, so the worker holds no statement, no address and no driver. A failure the
    database gave is a `PageReply` whose call is REJECTED or UNAVAILABLE; an address the rule
    refuses raises `brain.tools.fetch.UnsafeAddressError`, as a REST reading's operation does.
    See `A_DATABASE_IS_READ_BY_THE_SAME_LOOP`.

    **There is no method returning a document**, for `SourceReading`'s reason.
    """

    def entities(self) -> tuple[str, ...]:
        """Every entity kind the source projects, in the order a run reads them."""
        ...

    def refresh_interval(self) -> timedelta:
        """How often a healthy source is read, which is the interval its freshness is judged by."""
        ...

    def read(
        self,
        request: FetchRequest,
        *,
        settings: Mapping[str, str],
        login: DatabaseLogin,
        resolver: Resolver,
        fetched_at: str,
    ) -> PageReply:
        """One bounded read of the view this request's entity is kept in, as the source answered."""
        ...

    def projected(
        self, entity: str, row: Mapping[str, Any], *, seen_at: datetime
    ) -> ProjectedRecord | None:
        """The index entry kept for one row, or None for a row with nothing to keep."""
        ...


# ------------------------------------------------------------ an MCP server's tools, read
@runtime_checkable
class ToolReading(Protocol):
    """How the worker and a question read a source that is an MCP server's tools (M11.1.2).

    The worker's run opens one MCP session per attempt over the leased key, checks every tool
    the reading calls is listed as it was pinned, and calls one declared tool per entity; the
    reading only says which tool, with which arguments, and what its answer means. It holds no
    key, no session and no socket, so it is tested with no server at all. See
    `brain.connectors.mcp`, which argues the shape, and `brain.ops.mcp_session`, which talks.

    **There is no method returning a document**, for `SourceReading`'s reason.
    """

    def entities(self) -> tuple[str, ...]:
        """Every entity kind the source projects, in the order a run reads them."""
        ...

    def refresh_interval(self) -> timedelta:
        """How often a healthy source is read, which is the interval its freshness is judged by."""
        ...

    def key_scheme(self) -> KeyScheme:
        """How the run sends this source's key. The reading never sees the key."""
        ...

    def endpoint(self, settings: Mapping[str, str]) -> str:
        """The address of the MCP server this connection reads."""
        ...

    def pinned(self) -> Mapping[str, str]:
        """Every remote tool this reading calls, with the digest of its definition as reviewed."""
        ...

    def tool_call(self, entity: str, source_id: str | None) -> tuple[str, Mapping[str, Any]]:
        """The remote tool and arguments that list `entity`, or read the one record `source_id`."""
        ...

    def interpret_tool(
        self, entity: str, result: Mapping[str, Any], *, fetched_at: str
    ) -> PageReply:
        """One `tools/call` result, as the declared field mapping reads it."""
        ...

    def projected(
        self, entity: str, row: Mapping[str, Any], *, seen_at: datetime
    ) -> ProjectedRecord | None:
        """The index entry kept for one row, or None for a row with nothing to keep."""
        ...


# ------------------------------------------------------- custom code, run in a sandbox
@runtime_checkable
class CodeReading(Protocol):
    """How the worker and a question read a source through custom code in a sandbox (M11.1.5).

    The code plans calls and, where the connector needs it, interprets their answers; the host
    makes every call with the leased key. Both runs go through `brain.tools.run_skill.ScriptRunner`
    and neither is handed the key. See `brain.connectors.custom_code`, which argues the shape, and
    `brain.ops.custom_code_run`, which runs it.

    **There is no method returning a document**, for `SourceReading`'s reason.
    """

    def entities(self) -> tuple[str, ...]:
        """Every entity kind the source projects, in the order a run reads them."""
        ...

    def refresh_interval(self) -> timedelta:
        """How often a healthy source is read, which is the interval its freshness is judged by."""
        ...

    def key_scheme(self) -> KeyScheme:
        """How the host sends this source's key on a planned call. The code never sees the key."""
        ...

    def plan_spec(
        self, entity: str, *, settings: Mapping[str, str], source_id: str | None
    ) -> SandboxSpec:
        """The sandboxed run that plans the calls listing `entity`, or reading one record."""
        ...

    def planned(self, output: str) -> tuple[PlannedCall, ...]:
        """The calls a planning run printed, each on the declared egress allowlist, or a refusal."""
        ...

    def interpret_spec(self, entity: str, answers: tuple[bytes, ...]) -> SandboxSpec | None:
        """The sandboxed run interpreting the answers, or None when the field mapping reads them."""
        ...

    def from_answers(self, entity: str, answers: tuple[Any, ...], *, fetched_at: str) -> PageReply:
        """The decoded answers, read by the declared field mapping."""
        ...

    def from_output(self, entity: str, output: str, *, fetched_at: str) -> PageReply:
        """An interpreting run's output, read by the declared field mapping."""
        ...

    def projected(
        self, entity: str, row: Mapping[str, Any], *, seen_at: datetime
    ) -> ProjectedRecord | None:
        """The index entry kept for one row, or None for a row with nothing to keep."""
        ...


#: Every shape a connector's scheduled reading may take: a REST source's pages, a database's
#: views, an MCP server's tools, or custom code in a sandbox. The four transports of
#: `brain.connectors.transports`, each read by one typed branch of the one worker loop.
Reading = SourceReading | ViewReading | ToolReading | CodeReading


# ------------------------------------------------------------------ a write, granted apart
#: Why a connector's write is a grant of its own, with a key of its own.
A_WRITE_IS_A_GRANT_OF_ITS_OWN_WITH_A_KEY_OF_ITS_OWN: Final = (
    "A connection reads with a key that can only read, and the guide, the form and the vault slot "
    "say so. A write the connector can make is a separate, deliberate grant: its own step on the "
    "source's page, its own key in its own slot, off until that key is given, and used only to "
    "send a change a person approved, which is then read back with the read key before it is "
    "reported done. One key for both would make every read a call made with the power to change "
    "the source, and the approval would be the only thing standing between a question and a write."
)


# ---------------------------------------------------------- reading one record's figures live
#: Why a report may be several calls, and what one of them failing means.
A_REPORT_S_CALLS_ARE_MADE_AT_ONCE_AND_ANSWER_TOGETHER: Final = (
    "A source can need more than one call to answer one record's figures, reading its totals and "
    "its lists from different endpoints. The calls are made at once, so a report costs its "
    "slowest call rather than their sum, and a report any of whose calls did not answer is not "
    "answered: it is never shown with some of its figures missing, which would read as figures "
    "that are nought."
)


@dataclass(frozen=True)
class WriteCall:
    """One approved change as the call that sends it and the record it is read back by.

    `operation` is the source's own write, built from its specification like every read, so its
    address is prepared and checked by the same rule; `source_id` is the index id the change is
    read back by, through the connector's live lookup, with the read key.
    """

    operation: RestOperation
    arguments: Mapping[str, str]
    body: Mapping[str, Any]
    entity: str
    source_id: str


class PreparesWrite(Protocol):
    """How a connector turns an approved action into its call, and judges the record read back."""

    def call_for(self, action: Action) -> WriteCall:
        """The call that sends this approved action. Raises for an action it cannot send.

        Builds the call and sends nothing, which is why it is not named `call`: `brain.ops.effects`
        presumes a method of that name issues, and this one only reads the action.
        """
        ...

    def differs(self, action: Action, found: Mapping[str, Any]) -> tuple[str, ...]:
        """The names of the fields the record read back holds other than the action set them."""
        ...


@dataclass(frozen=True)
class WriteGrant:
    """A write a connector can be allowed to make, off until its own key is given (M11.7.3).

    `tools` are the prepared actions the grant sends; `not_allowed` is what an approver is told
    about one of them on an install that has not given the key. See
    `A_WRITE_IS_A_GRANT_OF_ITS_OWN_WITH_A_KEY_OF_ITS_OWN`.
    """

    name: str
    label: str
    tools: tuple[str, ...]
    credential_label: str
    credential_hint: str
    not_allowed: str
    #: How an approved action becomes its call and how the record read back is judged.
    prepares: PreparesWrite
    credential_shape: CredentialShape = CredentialShape.KEY
    #: What its own key must be allowed to do and never be given, which its slot is defined with.
    scopes: KeyScopes | None = None

    def __post_init__(self) -> None:
        if not _NAME_RE.match(self.name):
            msg = f"write grant {self.name!r} is not a name, and its key slot is named by it"
            raise DeclarationError(msg)
        if not self.tools:
            msg = f"write grant {self.name!r} sends no tool, so the key it asks for sends nothing"
            raise DeclarationError(msg)
        for one in (self.label, self.credential_label, self.credential_hint, self.not_allowed):
            if not one.strip():
                msg = (
                    f"write grant {self.name!r} must say what it allows, which key it asks for "
                    "and what an approver is told without it"
                )
                raise DeclarationError(msg)


@dataclass(frozen=True)
class ReportCall:
    """One call of a report: where, and the JSON body saying what, or none for a read by GET.

    The connector builds it and never resolves or connects; the run that holds the key checks the
    address with `brain.tools.fetch.assert_fetchable` before anything is sent.
    """

    url: str
    body: bytes | None = field(default=None, repr=False)


class LiveReport(Protocol):
    """How the figures one index row names are read from the source while somebody waits (M11.7.1).

    The report is asked for once per record, with the record's id, the day it is asked on and the
    range, as the calls it takes, made at once; when every call answered, their bodies are
    interpreted into one `SourceRecord` whose id is that record's, so the lane lays its figures
    over the index row exactly as it lays a live record's fields. With no range it is the report a
    question on Ask reads, every range its fields name; with a `DateWindow` it is that one range,
    which is what a figure tool asks for (`brain.knowledge.connector_figures`). See
    `A_FIGURE_IS_READ_BY_A_REPORT_AND_A_RECORD_BY_ITS_OWN_ENDPOINT` and
    `A_REPORT_S_CALLS_ARE_MADE_AT_ONCE_AND_ANSWER_TOGETHER`.
    """

    def entities(self) -> tuple[str, ...]:
        """Every entity kind whose figures are read by a report."""
        ...

    def identity_mode(self, entity: str) -> IdentityMode:
        """Whose credentials a report on this entity is read under (M11.2.5)."""
        ...

    def request_for(
        self,
        entity: str,
        source_id: str,
        *,
        settings: Mapping[str, str],
        today: date,
        window: DateWindow | None,
    ) -> tuple[ReportCall, ...]:
        """The calls the report for the record with this id is, as of `today`, in order: for the
        ranges a question names when `window` is None, or for that one window.

        Raises for an id that is not the shape the source issues, because an id is laid into the
        report's addresses, and a value that could change which report is read is refused here.
        """
        ...

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
        """Every call's decoded body, in the order asked, as one record with this id and figures.

        `today` is the day the calls were built for, handed back so a report that counts days does
        not keep it between the two. Called only when every call answered; a reply this does not
        read raises.
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
    #: How the worker reads it on a schedule, or None when nothing does. A REST source's reading,
    #: a database's views (`ViewReading`; see `A_DATABASE_IS_READ_BY_THE_SAME_LOOP`), an MCP
    #: server's tools (`ToolReading`) or custom code in a sandbox (`CodeReading`).
    reading: Reading | None = None
    #: How one of its records is read live at question time, or None when none is.
    live: LiveLookup | None = None
    #: How the figures one of its records names are read live, or None when it has none (M11.7.1).
    report: LiveReport | None = None
    #: The screens the console's connect flow shows for it. See the module docstring.
    guide: tuple[GuideStep, ...] = ()
    #: The writes it can be allowed to make, each off until its own key is given. See `WriteGrant`.
    writes: tuple[WriteGrant, ...] = ()
    #: What Ask answers from it, or None when Ask answers nothing from it yet.
    ask: AskRows | None = None
    #: What its key must be allowed to do and never be given, which its vault slot is defined with.
    scopes: KeyScopes | None = None
    #: Its verified rate ceiling, or None when nobody has measured one. Named for this source, so
    #: `brain.ops.limits.connector_ceiling` finds it. See `A_CEILING_LIVES_WITH_ITS_CONNECTOR`.
    ceiling: ConnectorLimit | None = None
    #: Which of its records entity resolution reads, as what type, by which field, and whether
    #: they carry money. Empty when none of its records is a company, a person or a project.
    #: See `brain.connectors.resolves`.
    resolves: tuple[ResolvesAs, ...] = ()

    def __post_init__(self) -> None:
        if not _NAME_RE.match(self.name):
            msg = f"connector {self.name!r} is not a name"
            raise DeclarationError(msg)
        if self.ceiling is not None and self.ceiling.name != self.name:
            msg = (
                f"connector {self.name!r} declares the ceiling of {self.ceiling.name!r}; a source "
                "is admitted by its own vendor's figure, found under its own name"
            )
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
            wanted: tuple[str, ...] = ()
            if self.console is not None:
                wanted = tuple(one.name for one in self.console.settings)
                if self.console.credential_shape is not CredentialShape.NONE:
                    wanted = (*wanted, CREDENTIAL_ASK)
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
        if self.writes and self.console is None:
            msg = (
                f"connector {self.name!r} declares a write and no console form; a write is granted "
                f"to a connection. {A_WRITE_IS_A_GRANT_OF_ITS_OWN_WITH_A_KEY_OF_ITS_OWN}"
            )
            raise DeclarationError(msg)
        granted = [one.name for one in self.writes]
        if len(granted) != len(set(granted)):
            msg = f"connector {self.name!r} declares one write grant twice"
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
        resolved = [one.entity for one in self.resolves]
        if len(resolved) != len(set(resolved)):
            msg = f"connector {self.name!r} declares one entity for resolution twice"
            raise DeclarationError(msg)
        unread = (
            ()
            if self.reading is None
            else tuple(sorted(set(resolved) - set(self.reading.entities())))
        )
        if unread:
            msg = (
                f"connector {self.name!r} declares {unread} for resolution and its reading keeps "
                "no record of them, so nothing would ever be resolved"
            )
            raise DeclarationError(msg)
        if self.report is not None and self.reading is None:
            msg = (
                f"connector {self.name!r} declares a report and no reading; a report is read with "
                "the reading's key, headers and scope, and names a record its index holds"
            )
            raise DeclarationError(msg)
        both = sorted(
            set(() if self.live is None else self.live.entities())
            & set(() if self.report is None else self.report.entities())
        )
        if both:
            msg = (
                f"connector {self.name!r} reads {both} live both as a record and as a report. "
                f"{A_FIGURE_IS_READ_BY_A_REPORT_AND_A_RECORD_BY_ITS_OWN_ENDPOINT}"
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


def write_grant_for(tool: str) -> tuple[str, WriteGrant] | None:
    """The shipped connector and the write grant that sends `tool`, or None for any other tool."""
    for name, declared in shipped().items():
        for grant in declared.writes:
            if tool in grant.tools:
                return name, grant
    return None


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
