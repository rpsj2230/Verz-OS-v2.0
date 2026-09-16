"""What one connector is trusted to read, in words, for somebody deciding whether to connect it.

`brain.console.operate` already answers whether a source is answering and when it last did, and
this does not repeat it: `reachable_connectors` is imported and called rather than reimplemented,
so the health table and this one are narrowed by one filter and cannot disagree about which
sources a reader may be told exist. What this adds is the other half of the question the owner
of a fresh install actually asks, which is not "is it up" but **"what did I just give it"**.

**Everything on a row is read off the manifest, which is the thing that was pinned.** The scope,
the access mode, the permission-sync claim and the ceiling name are all fields
`brain.connectors.manifest.manifest_digest` covers, so a row here is a rendering of the document
`brain.connectors.registry.reconnect` compares the far side against. A row assembled from
anywhere else would be a second description of a connector, and the one a reader trusts would be
the one nothing pins.

**A sentence, not a badge, and the sentences are total over their enumerations.** `AccessMode`
has two members and `PermissionSync` three, and every one of them has a sentence below written
for somebody with a server and no source tree. The alternative is the console composing prose
out of a word it was sent, which puts half the meaning of a permission decision in a browser.
`brain.console.version_view.ANSWERS` is the shape this follows.

**No count of anything, and in particular no count of selectors.** A scope names the folders,
tables or views this connector was connected to and the sentence lists them; what it must never
carry is "3 of 14", which is the subtraction disclosure arriving on the screen whose whole
subject is reach. See `A_SCOPE_SENTENCE_NAMES_WHAT_IT_REACHES_AND_NEVER_WHAT_IT_DOES_NOT`.

**A source with no verified ceiling says so and does not report a number.**
`brain.ops.limits.connector_ceiling` returns `None` for a name nobody has measured, and
`brain.ops.limits.source_limits` already refuses to invent one in that case. The sentence here
is the same refusal said to a person: a blank in the ceiling column reads as no ceiling, which
is the opposite of what it means. See `NO_VERIFIED_CEILING_IS_NOT_AN_UNLIMITED_ONE`.

**There is no vault path on a row, and that is a decision rather than an omission.**
`brain.connectors.contract.CredentialBinding` says a `SecretRef` is safe in a configuration row,
and it is: it is useless to anybody who cannot already reach the vault. It is still not on this
screen, because `brain.ops.openbao._call` goes out of its way to name the mount and never the
path in an error message, on the argument that a path names which credential was being borrowed,
and `brain.console.operate.ConnectorRow` already refuses a credential, a host and an endpoint on
a console row on the argument that a console row is the obvious second place for one to appear.
Two modules that far apart agreeing is worth more than the convenience. See
`A_VAULT_PATH_IS_NOT_A_CREDENTIAL_AND_IS_STILL_NOT_A_CONSOLE_ROW`.

**What is listed is what this install connected, and the product's list of what could be is a
different list served beside it.** Until 2026-09-17 nothing in the repository declared which
sources are connectable, so there was no second list; `brain.ops.connectable` declares it
now, total over the manifest builders. It is the same on every install, so offering it tells a
reader nothing about this one. A connection is `brain.ops.connector_store.Connection`, and
`connected_rows` turns each into a row by rebuilding the manifest it was connected with, so every
sentence on the row is still read off a manifest and the digest pinned at connect says whether
what it declares today is what was agreed to. See `WHAT_IS_SHOWN_IS_WHAT_IT_DECLARES_NOW`.

**A connection this build cannot rebuild is listed, and says so.** A source dropped from the
connectable list, or settings a stricter connector now refuses, still has a key in the vault and a
row saying it was connected. Leaving it off would make the one connection nobody can account for
the one nobody sees. See `A_CONNECTION_THIS_BUILD_CANNOT_REBUILD_IS_STILL_A_CONNECTION`.

Rejected: a "connect" verb here. This package writes nothing, and connecting a source is
`brain.ops.connector_admin`'s judgement, `brain.ops.credentials`' write and
`brain.ops.connector_store`'s row, asked for by `brain.connector_routes`.

Scope: reads values and returns values. Nothing here opens a connection, reads a clock of its
own or writes anything.

Task ids: M42.6.5
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from types import MappingProxyType
from typing import Any, Final

from brain.connectors.contract import (
    AccessMode,
    ConnectorContractError,
    ConnectorHealth,
    ConnectorScope,
)
from brain.connectors.manifest import ConnectorManifest, PermissionSync, manifest_digest
from brain.connectors.registry import ConnectorState, RegisteredConnector
from brain.console.operate import reachable_connectors
from brain.console.screens import offerable, screen
from brain.core.entitlement import EntitlementSet
from brain.core.projection import MAX_LABEL_CHARS, MAX_PROJECTED_FIELDS
from brain.ops.connectable import NotConnectableError, manifest_for
from brain.ops.connector_store import Connection
from brain.ops.credentials import Held, VaultState
from brain.ops.limits import connector_ceiling

#: The screen this module serves, as `brain.ops.console_screens` reads a declaration.
#:
#: A module-level constant and not a `screen()` call inside a function, which is that module's
#: one distinction: a capability borrowed for a dropdown is not a screen being served.
THE_SCREEN: Final = "connectors"


# ------------------------------------------------------------ written-down reasons

#: Why a scope sentence lists what it reaches and carries no figure beside it.
A_SCOPE_SENTENCE_NAMES_WHAT_IT_REACHES_AND_NEVER_WHAT_IT_DOES_NOT: Final = (
    "A connector's scope is the narrowing decided at connect: one folder rather than the whole "
    "drive, three views rather than the schema. Naming those is the point of the screen and "
    "discloses nothing the reader does not already reach, because a connector outside their "
    "reach produces no row at all. What must never appear beside it is a figure for how many "
    "resources the credential could have reached, or how many the scope left out, because both "
    "are a count of what is being withheld arriving on the one screen whose subject is reach, "
    "and one of them is recoverable from the other by subtraction."
)

#: Why a source nobody has measured says so rather than showing an empty ceiling.
NO_VERIFIED_CEILING_IS_NOT_AN_UNLIMITED_ONE: Final = (
    "brain.ops.limits.connector_ceiling answers None for a source nobody has measured and "
    "source_limits returns no windows at all rather than a default, because a ceiling invented "
    "for an unmeasured source is a number that looks verified and is not. On a screen the same "
    "absence is worse, because a blank in a column of rates reads as no limit: the reader plans "
    "a backfill against a source that will start refusing at a figure nobody has written down. "
    "So the sentence says that no ceiling has been recorded and that the source's own remains "
    "whatever it is."
)

#: Why the vault path a connector is bound to is not on the row.
A_VAULT_PATH_IS_NOT_A_CREDENTIAL_AND_IS_STILL_NOT_A_CONSOLE_ROW: Final = (
    "A SecretRef is safe in a configuration row and useless to anybody who cannot already reach "
    "the vault, and brain.connectors.contract.CredentialBinding says so. It is still not shown "
    "here. brain.ops.openbao builds its error messages out of the mount and never the path, on "
    "the argument that a path names which credential was being borrowed, and "
    "brain.console.operate.ConnectorRow refuses a credential, a host and an endpoint on the "
    "argument that a console row is the obvious second place for one to appear. What a reader "
    "needs from this screen is what the connector may read, which is the scope and the mode, "
    "and neither of those is the path."
)

#: Why a connector nobody installed and one this reader cannot see are the same absence.
AN_UNINSTALLED_CONNECTOR_AND_AN_UNREACHABLE_ONE_ARE_ONE_ABSENCE: Final = (
    "brain.console.operate.NAMING_A_SOURCE_IS_A_DISCLOSURE_ON_A_LIST_TOO already holds this for "
    "the health table and this list is narrowed by the same function, so a source that is out "
    "of this reader's reach and a source nobody connected produce an identical screen. The list "
    "of sources that could be connected is brain.ops.connectable's, the same on every "
    "install, so it is served whole and says nothing about which of them this company reads."
)

#: Why a connected source's row is built from its manifest as it is declared today.
WHAT_IS_SHOWN_IS_WHAT_IT_DECLARES_NOW: Final = (
    "A connection keeps its settings and the digest of the manifest agreed to, and not the "
    "manifest, because the manifest is the product's code and a release can change a connector's "
    "tools. So the row is built from what the connector declares today with those settings, and "
    "when the digest differs the row says that this is not what was agreed to, rather than "
    "showing the new declaration as though somebody had accepted it."
)

#: Why a connection whose manifest cannot be rebuilt stays on the list.
A_CONNECTION_THIS_BUILD_CANNOT_REBUILD_IS_STILL_A_CONNECTION: Final = (
    "A source can leave the connectable list, or a connector can come to refuse settings it once "
    "accepted, and the connection still has a key in the vault and a row saying who connected it. "
    "It is listed with nothing said about what it may read, because nothing can be read off a "
    "manifest that cannot be built, and with the one thing to do, which is to disconnect it."
)

#: Why the design's budget bar carries a ceiling and no figure for today's use.
NOTHING_HERE_COUNTS_TODAYS_CALLS: Final = (
    "docs/screens.html draws a bar of calls made today against the source's ceiling, and the "
    "denominator is the only half this install can answer. The numerator is a live counting "
    "window, and brain.ops.limit_store.ValkeyWindowStore checks and records the keys it is "
    "handed and offers no way to ask which windows exist, which is the same absence "
    "brain.install_routes.NOTHING_HERE_ENUMERATES_THE_LIVE_WINDOWS reports on the rate limits "
    "screen. A bar drawn from a number nobody measured would be the one element on this screen "
    "somebody reads before deciding a backfill is safe, so there is no bar and the ceiling is "
    "stated in words instead."
)

#: Why the design's last-read column carries the last probe instead.
A_LAST_PROBE_IS_NOT_A_LAST_READ: Final = (
    "The design's column is the time this source last answered a question, and nothing in this "
    "repository records one: brain.connectors.contract.ConnectorHealth carries checked_at, "
    "which is when somebody probed the source, and a probe happens whether or not anybody "
    "asked it anything. The two differ exactly when it matters, which is a source nothing has "
    "used all day and which probes green every minute. So the column carries the probe's time "
    "under the probe's name, and a reader is not invited to read a health check as traffic."
)

#: Why a count of projected fields is allowed on a screen that refuses counts.
A_COUNT_OF_WHAT_IS_COPIED_IS_NOT_A_COUNT_OF_WHAT_IS_HIDDEN: Final = (
    "The rule this repository keeps is that no figure may let a reader work out how much they "
    "were not shown. A projected field count is the opposite figure: it says how many fields of "
    "somebody else's system we hold a copy of, it is bounded by "
    "brain.core.projection.MAX_PROJECTED_FIELDS per entity, and it is the number the twelve-"
    "field cap exists to keep small. Nothing is subtracted from it, because the size of the "
    "source's own schema is not on this screen and is not ours to state."
)

#: Why no credential expiry is shown although the design asks for one.
NO_EXPIRY_IS_READABLE_FROM_HERE: Final = (
    "No expiry is shown, and that is not the same as no expiry existing. Nothing holds a "
    "connector credential between runs: a lease is minted for the length of one call and given "
    "back, so there is no standing expiry to read, and the static keys that do have one expire "
    "in a vendor's dashboard rather than in anything this install can ask."
)

#: What is said when this process has no database to ask which sources are connected.
NOTHING_HERE_CAN_SAY_WHICH_SOURCES_ARE_CONNECTED: Final = (
    "This process has no database, so nothing on this screen can say which sources this install "
    "has connected. It is not that none is connected: it is that nothing here has looked. Treat "
    "this screen as empty of information rather than as an empty list."
)

#: The sentence a connected source's key column carries, by what the vault said.
KEY_HELD: Final = (
    "Held in the vault since it was connected, and never shown again. Nothing on this install "
    "reads it yet, because no worker runs a connector."
)
KEY_NOT_HELD: Final = (
    "The vault holds no key for this source, so nothing could read from it even once a worker "
    "runs connectors. Disconnect it and connect it again with its key."
)
KEY_NOT_KNOWN: Final[Mapping[VaultState, str]] = MappingProxyType(
    {
        VaultState.ABSENT: (
            "This install runs no secrets vault, so whether a key for this source is held is not "
            "known here."
        ),
        VaultState.UNREACHABLE: (
            "Whether the vault holds this source's key is not known, because the vault did not "
            "answer."
        ),
        VaultState.REFUSED: (
            "Whether the vault holds this source's key is not known, because the vault refused to "
            "say."
        ),
        VaultState.READY: "Whether the vault holds this source's key was not asked.",
    }
)

#: The sentence beside a connection, by whether what it declares is what was agreed to.
DECLARATION_AGREED: Final = "What it declares is what was agreed to when it was connected."
DECLARATION_CHANGED: Final = (
    "What this release of the connector declares is not what was agreed to when the source was "
    "connected, and what is shown is what it declares now. Disconnect it and connect it again to "
    "agree to it."
)
DECLARATION_UNREADABLE: Final = (
    "This release cannot rebuild what the source was connected as, so nothing is said about what "
    "it may read. Disconnect it, and connect it again if the screen still offers it."
)


# ----------------------------------------------------------------- the sentences

#: What each access mode means, for somebody with a server and no source tree.
#:
#: Total over `AccessMode`, and `_assert_total` below holds it there. A mapping with a default
#: would render a mode nobody had written a sentence for as the safe-sounding one, and the
#: safe-sounding one is the wrong half of a two-member enumeration to guess.
ACCESS_SAYS: Final[Mapping[AccessMode, str]] = MappingProxyType(
    {
        AccessMode.READ_ONLY: (
            "Reads only. Nothing this connector runs can create, change or delete anything in "
            "the source, and a tool declaring a side effect is refused when the manifest is "
            "built rather than when the source returns a 403."
        ),
        AccessMode.WRITE: (
            "Reads and writes. Somebody granted this deliberately and is named on the binding; "
            "a draft counts as a write, because a draft is a row in somebody else's system that "
            "we created."
        ),
    }
)

#: What each permission-sync claim means. Total over `PermissionSync`.
PERMISSION_SYNC_SAYS: Final[Mapping[PermissionSync, str]] = MappingProxyType(
    {
        PermissionSync.NONE: (
            "The source tells us nothing about who may see a row, so the grants written here "
            "are the only permissions there are over what it returns."
        ),
        PermissionSync.PREDICATE: (
            "The source's own visibility rule is stored beside the projection and is applied to "
            "whoever is asking, so a person who moves department gets a different set of rows "
            "with nothing being rewritten."
        ),
        PermissionSync.DELEGATED: (
            "Every call runs as the person asking, so the source applies its own rules to them "
            "as well as ours, and somebody the source has never heard of gets nothing."
        ),
    }
)


def assert_total(
    pairs: Iterable[tuple[Mapping[Any, str], type[enum.Enum]]],
) -> None:
    """Refuse a sentence table with a member missing.

    Called at import rather than only from a test, because the failure it prevents is a
    `KeyError` inside a request for a connector nobody had thought about, and because a table
    this module owns is a table this module can hold itself to.

    **The tables are a parameter and not read off the module, and that is the whole reason this
    function has a signature at all.** Written to close over `ACCESS_SAYS` and
    `PERMISSION_SYNC_SAYS` it could only ever be called with two tables that are already
    complete, so the guard could be deleted whole and nothing would notice: mutation testing on
    2026-09-16 reported exactly that. A parameter lets a test hand it an incomplete table, which
    is the only state it exists to refuse.
    """
    for table, enumeration in pairs:
        missing = sorted(str(one.value) for one in enumeration if one not in table)
        if missing:
            msg = (
                f"{enumeration.__name__} members {missing} have no sentence, so a connector "
                "declaring one renders with nothing said about what it may do"
            )
            raise ValueError(msg)


assert_total(((ACCESS_SAYS, AccessMode), (PERMISSION_SYNC_SAYS, PermissionSync)))


def scope_in_words(scope: ConnectorScope) -> str:
    """What this connector was connected to, as a sentence naming each resource.

    The selectors are the source's own identifiers and they are listed rather than counted; see
    `A_SCOPE_SENTENCE_NAMES_WHAT_IT_REACHES_AND_NEVER_WHAT_IT_DOES_NOT`. Sorted, because the
    tuple's order is the order the manifest's author typed them and a reader comparing two
    installs would otherwise be reading a diff of somebody's typing.
    """
    named = ", ".join(sorted(scope.selectors))
    return f"Reaches {scope.resource_kind} {named}, and nothing else in the source."


def credential_in_words(manifest: ConnectorManifest) -> str:
    """Where this connector's credential is held and what it is allowed to be used for.

    The vault role travels and the path does not, which is the whole of this function's
    judgement. A role is one of three compiled-in names and says which policy the borrow runs
    under; a path says which credential, and see
    `A_VAULT_PATH_IS_NOT_A_CREDENTIAL_AND_IS_STILL_NOT_A_CONSOLE_ROW`.

    There is no expiry here and the design asks for one. See `NO_EXPIRY_IS_READABLE_FROM_HERE`.
    """
    binding = manifest.credential
    return (
        f"Held in the vault, borrowed as {binding.ref.role.value} for the length of one call. "
        f"{NO_EXPIRY_IS_READABLE_FROM_HERE}"
    )


def projected_field_count(manifest: ConnectorManifest) -> int:
    """How many fields this connector copies, across every entity it projects.

    A count of what is copied, which is the opposite of the count this repository refuses: it
    is a figure about our own store rather than about what a reader was not shown, and it is
    the figure the cap is written against. See
    `A_COUNT_OF_WHAT_IS_COPIED_IS_NOT_A_COUNT_OF_WHAT_IS_HIDDEN`.
    """
    return sum(len(projection.fields) for projection in manifest.projections)


def ceiling_in_words(manifest: ConnectorManifest) -> str:
    """What this connector's verified ceiling is, or that nobody has measured one.

    The manifest's `ceiling` field is a name looked up in `brain.ops.limits` rather than a
    figure carried on the manifest, so this asks that module. An empty name and a name with no
    row are one answer here deliberately: both mean nothing has been verified, and a connector
    naming a ceiling that does not exist is not a state a reader can act on differently.
    """
    measured = connector_ceiling(manifest.ceiling) if manifest.ceiling else None
    if measured is None:
        return (
            "No verified ceiling has been recorded for this source, so nothing here is pacing "
            f"it. {NO_VERIFIED_CEILING_IS_NOT_AN_UNLIMITED_ONE}"
        )
    if measured.per_day is None:
        daily = "and no daily figure has been verified"
    else:
        daily = f"and {measured.per_day:,} a day"
    if measured.raisable:
        movable = "This ceiling can be raised with the vendor."
    else:
        movable = "Asking for less is the only lever; no plan we can buy moves this number."
    note = f" {measured.note}" if measured.note else ""
    return f"{measured.per_minute:,} requests a minute {daily}. {movable}{note}"


# ------------------------------------------------------------------------ the row


@dataclass(frozen=True)
class TrustRow:
    """One connector, as the person who has to decide whether to trust it may see it.

    Every field is read off the pinned manifest or off the registry's own state, and there is no
    field for a credential, a vault path, a host or an endpoint. See
    `A_VAULT_PATH_IS_NOT_A_CREDENTIAL_AND_IS_STILL_NOT_A_CONSOLE_ROW`.

    `health` and `lifecycle` are both carried, and `brain.console.operate.ConnectorRow` gives
    the reason: a connector can be enabled and unreachable, and a screen showing one of the two
    sends an operator to chase the wrong thing. An unprobed source carries an empty health
    rather than a healthy one.
    """

    #: Source, in `docs/screens.html`'s column order from here down.
    name: str
    #: Wiring: MCP, REST, database or custom, which is the chip the design draws.
    wiring: str
    #: Credential: where it is held and under which vault role, and never the path or a value.
    credential: str
    #: Budget: the verified ceiling in words. The design draws a bar of today's use against
    #: it and there is no reader for the numerator; see `NOTHING_HERE_COUNTS_TODAYS_CALLS`.
    budget: str
    #: Projected: how many fields this connector copies, across every entity it projects.
    #: A count of what is copied and never of what is withheld; see
    #: `A_COUNT_OF_WHAT_IS_COPIED_IS_NOT_A_COUNT_OF_WHAT_IS_HIDDEN`.
    projected_fields: int
    #: Last checked: when the last probe ran, or null when nothing has probed it. The design
    #: asks for the last read, which nothing here records; see `A_LAST_PROBE_IS_NOT_A_LAST_READ`.
    checked_at: datetime | None
    #: State: what the last probe said, or empty when nothing has probed it.
    health: str
    #: What the registry says: registered, enabled, disabled or quarantined. Carried beside
    #: the health for `brain.console.operate.ConnectorRow`'s reason.
    lifecycle: str
    #: Whether it is serving traffic now. Read off the registry entry rather than compared
    #: against a word here, so there is one definition of serving.
    serving: bool
    version: str
    #: The sentences the row opens into: what it reaches, what it may do, and what the source
    #: contributes to who may see a row.
    reaches: str
    access: str
    permission_sync: str


def trust_row(one: RegisteredConnector, health: ConnectorHealth | None) -> TrustRow:
    """One registered connector as a row. Takes the probe rather than performing one.

    Handed in rather than gathered, for the reason `brain.console.operate.connector_rows` gives:
    each connector produces its own health through its own function with its own signature, and
    a console module calling five of them would be a sixth opinion about what healthy means.
    """
    manifest = one.manifest
    return TrustRow(
        name=one.name,
        wiring=manifest.transport.value,
        credential=credential_in_words(manifest),
        budget=ceiling_in_words(manifest),
        projected_fields=projected_field_count(manifest),
        checked_at=None if health is None else health.checked_at,
        health="" if health is None else health.state.value,
        lifecycle=one.state.value,
        serving=one.is_serving,
        version=manifest.version,
        reaches=scope_in_words(manifest.scope),
        access=ACCESS_SAYS[manifest.credential.mode],
        permission_sync=PERMISSION_SYNC_SAYS[manifest.permission_sync],
    )


_NOTHING_PROBED: Final[Mapping[str, ConnectorHealth]] = MappingProxyType({})


# ------------------------------------------------- what is copied and what never is


@dataclass(frozen=True)
class CopyLine:
    """One thing a connector either copies into this system or never does.

    `verdict` is one of two words and `why` is the sentence beside it, in the shape
    `brain.console.installation.Fact` uses: a table of nouns with a tick against half of them
    is read as a summary of a policy, and the half a reader gets wrong is the half they were
    about to store something under.
    """

    what: str
    #: `projected` or `never`. Two words, because the policy has two answers.
    verdict: str
    why: str


#: Whether a caller may have to read this table before believing a connector is safe.
PROJECTED: Final = "projected"
NEVER: Final = "never"

#: `docs/screens.html` SCREEN 9's second card, served rather than drawn in the browser.
#:
#: The two figures in it are read out of `brain.core.projection` rather than typed, because a
#: card quoting a cap is a card that goes stale silently the day somebody moves the cap, and
#: this is the card a reviewer reads to find out what is stored about their clients.
COPY_POLICY: Final[tuple[CopyLine, ...]] = (
    CopyLine(
        what="Identifiers and join keys",
        verdict=PROJECTED,
        why=(
            f"At most {MAX_PROJECTED_FIELDS} fields per entity kind, so a projection cannot "
            "grow into a copy of the source."
        ),
    ),
    CopyLine(
        what=f"Enums, timestamps and short labels of up to {MAX_LABEL_CHARS} characters",
        verdict=PROJECTED,
        why=(
            "One label per entity, because the character limit on its own does not stop six "
            "of them adding up to a document body."
        ),
    ),
    CopyLine(
        what="The source's own visibility rule",
        verdict=PROJECTED,
        why=(
            "The rule and never the people it currently admits. Move somebody between "
            "departments and the next question returns a different set of rows, with nothing "
            "re-crawled and nothing to invalidate."
        ),
    ),
    CopyLine(
        what="A resolved list of who may see a row",
        verdict=NEVER,
        why=(
            "A list is the rule evaluated at one instant, and it is wrong from the next "
            "joiner onwards while looking exactly as authoritative as the rule."
        ),
    ),
    CopyLine(
        what="Money, contract terms and document bodies",
        verdict=NEVER,
        why=(
            "Fetched at the moment a question is asked and never stored, so the system of "
            "record's own retention and deletion rules stay the only ones that apply to them."
        ),
    ),
)


def _connector_row(name: str) -> dict[str, str]:
    """The fields a connector grant's scope may be written against.

    One field, spelled as `brain.console.screens.Axis.CONNECTOR` spells it, because a grant
    narrowed to one source is written against the same word the screen's own filter axis uses
    and a second spelling here would be a clause that matches nothing while reading as a
    restriction. `brain.console.installation._limit_row` is the same construction.
    """
    return {"connector": name}


def connectors_reachable(
    names: Iterable[str], reader: EntitlementSet, now: datetime | None = None
) -> tuple[str, ...]:
    """Which of these source names this reader's own grant admits.

    `scope_for` rather than `holds`, so a grant narrowed to one connector narrows the list
    rather than admitting all of them, and a reader holding nothing gets an empty tuple rather
    than every name: `None` from `scope_for` is the absence of a grant and is never the
    unrestricted scope, which is the confusion `brain.console.operate.
    NO_READ_OF_THE_PLANE_IS_NOTHING_AND_NEVER_EVERYTHING` records about a different screen.

    Returns the names and no count of what was dropped. See
    `AN_UNINSTALLED_CONNECTOR_AND_AN_UNREACHABLE_ONE_ARE_ONE_ABSENCE`.
    """
    where = reader.scope_for(screen(THE_SCREEN).read.requires, now)
    if where is None:
        return ()
    return tuple(name for name in names if where.matches(_connector_row(name)))


def trust_rows(
    registry: Sequence[RegisteredConnector],
    reader: EntitlementSet,
    *,
    now: datetime | None = None,
    checked: Mapping[str, ConnectorHealth] = _NOTHING_PROBED,
) -> tuple[TrustRow, ...]:
    """Every connector this reader may be told exists, with what it is trusted to read.

    Two narrowings and they are not the same one. `connectors_reachable` asks what this
    reader's own grant admits, and `brain.console.operate.reachable_connectors` is the console's
    rule that a listing of sources is filtered the way a dropdown is. The second is called
    rather than reimplemented so that this list and the health table beside it cannot disagree
    about which sources a reader may be told exist, and the disagreement would be invisible to
    anybody reading either screen on its own.

    The reader is taken rather than a list of names, so there is no signature here a caller
    could pass an unrestricted list of connectors into by accident.
    """
    reachable = connectors_reachable([one.name for one in registry], reader, now)
    return tuple(
        trust_row(one, checked.get(one.name)) for one in reachable_connectors(registry, reachable)
    )


# ------------------------------------------------------------------ what was connected


@dataclass(frozen=True)
class ConnectedRow:
    """One source this install connected from the console, as a reader may be told of it.

    `trust` is the row this module has always drawn, built from the manifest the connection's
    settings make today, with its credential sentence saying what the vault holds rather than how
    a lease is borrowed, because nothing borrows this key. It is None when the manifest cannot be
    rebuilt; see `A_CONNECTION_THIS_BUILD_CANNOT_REBUILD_IS_STILL_A_CONNECTION`.
    """

    name: str
    connected_by: str
    connected_at: datetime
    #: Whether the vault holds its key, or None when the vault could not be asked.
    key_held: bool | None
    key_written_at: datetime | None
    #: Whether what it declares today is what was agreed to at connect.
    pinned: bool
    declaration: str
    trust: TrustRow | None


def key_in_words(held: Held | None, vault: VaultState) -> str:
    """What the vault said about one source's key, as the sentence its credential column carries."""
    if vault is not VaultState.READY or held is None:
        return KEY_NOT_KNOWN[vault]
    return KEY_HELD if held.held else KEY_NOT_HELD


def admitted_connections(
    connections: Sequence[Connection], reader: EntitlementSet, now: datetime | None = None
) -> tuple[Connection, ...]:
    """The connections this reader may be told exist, in the order given.

    Narrowed by the two functions `trust_rows` narrows by, in the same order, over names, so a
    connection whose manifest cannot be rebuilt is narrowed exactly as one whose manifest can.
    Public so a route asks the vault about these and no others. No count of what was left out.
    """
    names = [one.connector for one in connections]
    admitted = set(offerable(names, connectors_reachable(names, reader, now)))
    return tuple(one for one in connections if one.connector in admitted)


def connected_rows(
    connections: Sequence[Connection],
    reader: EntitlementSet,
    *,
    now: datetime | None = None,
    held: Mapping[str, Held],
    vault: VaultState,
) -> tuple[ConnectedRow, ...]:
    """Every connection this reader may be told exists, each with what it is trusted to read.

    Narrowed by `admitted_connections` whatever the caller already narrowed, so a reader holding
    nothing over a source is told of it by no path through this function. See
    `AN_UNINSTALLED_CONNECTOR_AND_AN_UNREACHABLE_ONE_ARE_ONE_ABSENCE`.

    No count of what was left out, and the reader is taken rather than a list of names, for
    `trust_rows`' reasons.
    """
    rows: list[ConnectedRow] = []
    for one in admitted_connections(connections, reader, now):
        key = held.get(one.connector) if vault is VaultState.READY else None
        written = None if key is None else key.set_at
        known = None if key is None else key.held
        try:
            manifest = manifest_for(one.connector, one.settings)
        except (NotConnectableError, ConnectorContractError):
            rows.append(
                ConnectedRow(
                    name=one.connector,
                    connected_by=one.connected_by,
                    connected_at=one.connected_at,
                    key_held=known,
                    key_written_at=written,
                    pinned=False,
                    declaration=DECLARATION_UNREADABLE,
                    trust=None,
                )
            )
            continue
        pinned = manifest_digest(manifest) == one.digest
        registered = RegisteredConnector(
            manifest=manifest, digest=one.digest, state=ConnectorState.REGISTERED
        )
        rows.append(
            ConnectedRow(
                name=one.connector,
                connected_by=one.connected_by,
                connected_at=one.connected_at,
                key_held=known,
                key_written_at=written,
                pinned=pinned,
                declaration=DECLARATION_AGREED if pinned else DECLARATION_CHANGED,
                trust=replace(trust_row(registered, None), credential=key_in_words(key, vault)),
            )
        )
    return tuple(rows)
