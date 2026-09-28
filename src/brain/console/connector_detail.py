"""One source on the Connectors module: every source the product declares, and one source whole.

`brain.console.connector_trust` answers what a connected source is trusted to read, and it answers
it only for connections. What the module's list and a source's own page need besides is the
product's side: every source this release declares, connected or not, how each one is connected
(from this screen, through Connect Lark, or at the server), what the worker reads and how often,
what a connection keeps and what it reads live, the department its records answer to, its history,
and the agents and skills that lean on it. This module decides all of that from values handed in,
and holds no client, for the split CLAUDE.md names.

**The list is total over the shipped declarations, and a connection only ever adds to a row.**
Every source `brain.connectors.declaration.shipped` finds is a row, so a source that is not
connected reads "not connected" on the same list as one that is, and a source this reader may not
be told is connected reads exactly the same, because the connection is looked up only through
`connector_trust.admitted_connections`. See
`A_SOURCE_NOBODY_CONNECTED_AND_ONE_YOU_MAY_NOT_SEE_READ_ALIKE`.

**Connectors keep a minimal index and read every value live, and the page shows both halves as the
manifest declares them.** What a connection keeps is each projected entity and its field names,
read off the manifest its settings build today; what it reads live is the manifest's tools. Neither
is a value from the source, and nothing here reads one. See
`brain.connectors.declaration.CONNECTORS_NEVER_BULK_SYNC`.

**The department a source answers to is read off its own visibility rule.** Freshdesk is connected
for one department and its rule is an equality on `department`; Xero and HubSpot are pinned to an
organisation and name none. A source whose rule names no department says so rather than guessing
one from who connected it. See `department_of`.

**The agents and the skills that use a source are narrowed as their own screens narrow them.** An
agent is listed only when its audience admits the reader (`brain.agents.model.visible_agent_ids`,
decided by the caller), and a skill only for a reader of the skill library; both only for a reader
this source is admitted to, so the lists cannot name a source's users to somebody the source is
hidden from. No count of what was left out (M27.15.58).

Rejected: a second list of sources written here. `brain.ops.connectable` already reads the console
forms off the declarations; a list kept here would be the third, and the first place a new
connector was missing.

Scope: reads values and returns values. Nothing here opens a connection or writes anything.

Task ids: M27.11.9, M27.15.39, M27.15.58, M11.7.7, M11.2.1, M11.2.4
"""

from __future__ import annotations

import enum
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Final

from brain.connectors.declaration import shipped
from brain.connectors.manifest import ConnectorManifest, manifest_digest
from brain.console.connector_trust import (
    admitted_connections,
    ceiling_in_words,
    ceiling_named_in_words,
    connectors_reachable,
)
from brain.console.screens import offerable
from brain.console.skill_library import LibrarySkill
from brain.core.entitlement import EntitlementSet
from brain.core.scope import Op
from brain.ops.connector_admin import may_connect_source
from brain.ops.connector_store import Connection
from brain.ops.connector_sync import READINGS, SyncOutcome, SyncState
from brain.ops.lark_connect import USES, Use
from brain.tools.registry import ToolRegistry

# ------------------------------------------------------------ written-down reasons

#: Why a hidden connection and an absent one draw the same row.
A_SOURCE_NOBODY_CONNECTED_AND_ONE_YOU_MAY_NOT_SEE_READ_ALIKE: Final = (
    "Every source this release ships is a row on the list, because what the product can read is "
    "the same on every install and tells a reader nothing. Whether one is connected here is "
    "looked up only among the connections this reader may be told of, so a connection they may "
    "not see leaves the row reading not connected, word for word what a source nobody connected "
    "reads. A row that said hidden, or that was missing, would be the disclosure."
)

#: What a source's page says about reading when nothing reads it on a schedule.
READ_LIVE_ONLY: Final = (
    "Nothing reads it on a schedule. A page or a record is read live from the source when a "
    "question needs it, at the asker's own reach, and nothing is kept but its small index."
)

#: What a source's page says about reading when it is connected at the server.
READ_AT_THE_SERVER: Final = (
    "It is connected and read at the server, not from this screen, so how it is read is set there."
)

#: What the department line says when the source's rule names none.
NO_DEPARTMENT: Final = (
    "Its records answer to the organisation or account it is pinned to, not to one department."
)


class ConnectFrom(enum.StrEnum):
    """Where a source is connected, which decides the control its page offers."""

    #: This screen's own form: settings and one key.
    CONSOLE = "console"
    #: Connect Lark, on this screen, which creates the app and switches each use on.
    LARK = "lark"
    #: The server, because this screen has no way to collect what the source needs.
    SERVER = "server"


class SourceStatus(enum.StrEnum):
    """What a row says about a source, in three words. Closed; there is no fourth."""

    CONNECTED = "connected"
    NOT_CONNECTED = "not_connected"
    #: Connected, and the worker's newest attempt at it failed.
    FAILING = "failing"


#: The shipped sources Connect Lark switches on, by name, read off its own uses: a use's slot is
#: the connector's name, which is how the Lark connectors find their key.
LARK_SOURCES: Final[Mapping[str, Use]] = MappingProxyType(
    {spec.slot: use for use, spec in USES.items() if spec.slot in shipped()}
)


# ------------------------------------------------------------------------ the rows


@dataclass(frozen=True)
class SourceRow:
    """One source on the list. Nothing here is a value from the source."""

    name: str
    label: str
    status: SourceStatus
    #: The worker's newest word about it, or None when it is not connected or never tried.
    health: str | None
    department: str | None
    #: When the worker last read it to the end.
    last_read_at: datetime | None
    connected_at: datetime | None
    #: What this release declares is not what was agreed to when it was connected.
    declaration_changed: bool
    connect_from: ConnectFrom
    #: Whether this reader may connect, edit or disconnect it. Their own grant; it narrows nothing.
    may_manage: bool


def connect_from(name: str) -> ConnectFrom:
    """Where a shipped source is connected. A name nothing ships is refused by the caller first."""
    declared = shipped()[name]
    if declared.console is not None:
        return ConnectFrom.CONSOLE
    if name in LARK_SOURCES:
        return ConnectFrom.LARK
    return ConnectFrom.SERVER


def may_be_told_of(name: str, reader: EntitlementSet, now: datetime | None = None) -> bool:
    """Whether this reader may be told anything about this source's connection here.

    The same two narrowings `connector_trust.admitted_connections` applies to a connection,
    asked of the name alone, so a source with no live connection (a history, a Lark use) is
    narrowed exactly as one with a connection.
    """
    return name in offerable([name], connectors_reachable([name], reader, now))


def status_of(connected: bool, state: SyncState | None) -> SourceStatus:
    """Connected or not, and failing when the worker's newest attempt at a connection failed.

    A quota wait is not a failure, for
    `brain.connectors.throttle.A_QUOTA_REFUSAL_IS_NOT_ILL_HEALTH`'s reason: the source asked to be
    read later and will be.
    """
    if not connected:
        return SourceStatus.NOT_CONNECTED
    if state is not None and state.outcome is SyncOutcome.FAILED:
        return SourceStatus.FAILING
    return SourceStatus.CONNECTED


def department_of(manifest: ConnectorManifest | None) -> str | None:
    """The one department every projected entity's visibility rule names, or None.

    An equality on `department` in the source's own rule, as Freshdesk declares it. A rule that
    names none, or entities that name different ones, is None: a page naming one department for a
    source whose records answer to several would be telling the reader the wrong people can see it.
    """
    if manifest is None or not manifest.projections:
        return None
    named: set[str] = set()
    for projection in manifest.projections:
        found = {
            one.value
            for one in projection.visibility.clauses
            if one.field == "department" and one.op is Op.EQ and isinstance(one.value, str)
        }
        if len(found) != 1:
            return None
        named |= found
    return next(iter(named)) if len(named) == 1 else None


def source_rows(
    *,
    connections: Sequence[Connection],
    synced: Mapping[str, SyncState],
    lark_on: Collection[str],
    manifests: Mapping[str, ConnectorManifest],
    reader: EntitlementSet,
    now: datetime,
) -> tuple[SourceRow, ...]:
    """Every source this release ships, each with what this reader may be told of its connection.

    `connections` are every live connection; only those `admitted_connections` admits are looked
    at. `lark_on` names the sources Connect Lark has switched on, and each is narrowed by
    `may_be_told_of` in the same way. `manifests` are the manifests the admitted connections'
    settings build today, by source, missing where one cannot be built. No count of anything left
    out: see `A_SOURCE_NOBODY_CONNECTED_AND_ONE_YOU_MAY_NOT_SEE_READ_ALIKE`.
    """
    live = {one.connector: one for one in admitted_connections(connections, reader, now)}
    rows: list[SourceRow] = []
    for name, declared in shipped().items():
        one = live.get(name)
        state = synced.get(name) if one is not None else None
        through_lark = name in lark_on and may_be_told_of(name, reader, now)
        manifest = manifests.get(name) if one is not None else None
        rows.append(
            SourceRow(
                name=name,
                label=declared.label,
                status=status_of(one is not None or through_lark, state),
                health=None if state is None else state.health.value,
                department=department_of(manifest),
                last_read_at=None if state is None else state.last_synced_at,
                connected_at=None if one is None else one.connected_at,
                declaration_changed=(
                    one is not None
                    and manifest is not None
                    and manifest_digest(manifest) != one.digest
                ),
                connect_from=connect_from(name),
                may_manage=may_connect_source(reader, name, now),
            )
        )
    return tuple(rows)


# ------------------------------------------------------------------ one source, whole


@dataclass(frozen=True)
class KeptEntity:
    """One kind of record a connection keeps an index of, and the field names it keeps."""

    entity: str
    fields: tuple[str, ...]


@dataclass(frozen=True)
class LiveRead:
    """One thing a connection reads live at question time: its tool and what the tool says."""

    tool: str
    entity: str
    description: str


def kept_index(manifest: ConnectorManifest | None) -> tuple[KeptEntity, ...]:
    """What a connection keeps: each projected entity and its field names, never a value."""
    if manifest is None:
        return ()
    return tuple(
        KeptEntity(entity=one.entity, fields=tuple(field.name for field in one.fields))
        for one in manifest.projections
    )


def read_live(manifest: ConnectorManifest | None) -> tuple[LiveRead, ...]:
    """What a connection reads live: the manifest's tools, in their declared order."""
    if manifest is None:
        return ()
    return tuple(
        LiveRead(tool=one.name, entity=one.entity, description=one.description)
        for one in manifest.tools
    )


def _every(interval: timedelta) -> str:
    minutes = int(interval.total_seconds() // 60)
    if minutes % 60 == 0:
        hours = minutes // 60
        return "every hour" if hours == 1 else f"every {hours} hours"
    return f"every {minutes} minutes"


def reading_in_words(name: str) -> str:
    """How a shipped source is read, in one sentence, from its own declaration."""
    reading = READINGS.get(name)
    if reading is not None:
        kinds = list(reading.entities())
        entities = kinds[0] if len(kinds) == 1 else f"{', '.join(kinds[:-1])} and {kinds[-1]}"
        return (
            f"The worker reads its {entities} records {_every(reading.refresh_interval())}, under "
            "its verified call ceiling, and keeps only the index its declaration names. Every "
            "value is read live when a question needs it."
        )
    if connect_from(name) is ConnectFrom.LARK:
        return READ_LIVE_ONLY
    return READ_AT_THE_SERVER


def ceiling_for(name: str, manifest: ConnectorManifest | None) -> str:
    """The verified ceiling in words: the manifest's own when connected, the source's otherwise."""
    return ceiling_in_words(manifest) if manifest is not None else ceiling_named_in_words(name)


# ------------------------------------------------------------- who leans on a source


@dataclass(frozen=True)
class NamedAgent:
    """An agent whose manifest names a source: its id for the link and its name for the page."""

    agent_id: str
    display_name: str


@dataclass(frozen=True)
class NamedSkill:
    """A skill whose tools come from a source: its name and the newest version's state."""

    name: str
    version: str
    state: str


def agents_naming(
    name: str,
    *,
    connectors_by_agent: Mapping[str, Sequence[str]],
    names: Mapping[str, str],
    visible: Collection[str],
) -> tuple[NamedAgent, ...]:
    """The agents whose effective manifest names this source, among those the reader may see.

    `visible` is the audience's answer, decided by the caller with `visible_agent_ids`; an agent
    outside it is never looked at, whatever its manifest names. Ordered by name.
    """
    found = [
        NamedAgent(agent_id=agent_id, display_name=names.get(agent_id, agent_id))
        for agent_id, connectors in connectors_by_agent.items()
        if agent_id in visible and name in connectors
    ]
    return tuple(sorted(found, key=lambda one: (one.display_name.casefold(), one.agent_id)))


def skills_from(
    name: str, library: Iterable[LibrarySkill], registry: ToolRegistry
) -> tuple[NamedSkill, ...]:
    """The skills whose newest version names a tool this source provides, by name.

    A tool's source is the registry's, never the skill's word for it. The newest version of each
    skill is the one judged, because that is the one the library offers next.
    """
    newest: dict[str, LibrarySkill] = {}
    for one in library:
        held = newest.get(one.name)
        if held is None or one.submitted_at > held.submitted_at:
            newest[one.name] = one
    found = [
        NamedSkill(
            name=one.name,
            version=one.imported.skill.version,
            state=one.imported.state.value,
        )
        for one in newest.values()
        if any(
            registry.has(tool) and registry.get(tool).definition.source == name
            for tool in one.imported.skill.tools
        )
    ]
    return tuple(sorted(found, key=lambda one: one.name.casefold()))
