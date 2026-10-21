"""What is connected for each department, as one reader may be told it, and what to connect next.

`brain.adoption` holds the rules (`coverage_report`, `shopping_list`, `first_connector`,
`starter_questions`) and was called by nothing; this is where they met the install's own rows.
It takes the connections, manifests, sync states and record counts as values somebody else read,
decides what one reader may be told of them, and returns lines. It opens nothing and reads no clock.

**The departments a reader is told about are the ones the usage grant admits, and there is no
coverage capability.** A coverage line is a fact about a department's own activity in the same
sense an adoption line is, so it is narrowed by `brain.console.adoption_view.reachable_departments`
(which is `brain.console.spend_view.may_read_spend`) and not by a second rule. A champion or a
department lead sees their department's line because they hold usage for it, an administrator sees
all of them, and a change to who may read usage is a change to who may read coverage the same
afternoon. See `COVERAGE_IS_READ_UNDER_THE_GRANT_USAGE_IS_READ_UNDER`.

**A source this reader may not be told of is merged, never dropped and never shown as missing.** The
Connectors screen decides who may be told a source's name (`admitted_connections`). A department
whose only connected source is one the reader may not name would read "not connected" if the line
were dropped, which is false, and would read as the source if it were named, which is a disclosure.
So such sources are merged into one line for the department, labelled `UNNAMED_SOURCE`, with their
records and last read added together: a statement about the department the reader may see, naming
nothing they may not. This is the shape `brain.console.questions_view.gap_lines` gives the same
problem. See `A_SOURCE_YOU_MAY_NOT_NAME_IS_MERGED_AND_NEVER_DROPPED`.

**A department with nothing connected is a line, not a gap in the list.** Every reachable department
gets at least one line, so whether a department appears is a fact about the reader's reach and never
about what is connected: `brain.adoption.A_ZERO_AND_A_NOT_CONNECTED_SOURCE_ARE_DIFFERENT_FACTS`
made visible. The source such a line names is the one `first_connector` would start with, so the
shopping list can say what to authorise; where nothing on this install could answer on the day it is
connected, the line names no source and says only that nothing is connected.

**No total, no percentage, no count of the rest.** Lines are per department and per source; the
statement carries no field that adds them up, and `coverage_gaps` is held over what the page says
in this module's tests.

**Sources pinned to the whole organisation are not in a department's statement.** A source whose
visibility rule names no department (`brain.console.connector_detail.department_of`) answers to the
organisation; attributing its records to every department would make the same figure appear in each
line. They stay on the Connectors screen, which says so. This is a narrowing of M34.1.2.1 that the
page states in words rather than leaving a reader to wonder where an accounting source went.

**Starter questions are narrowed to what the reader may ask before they are ranked.**
`starter_for_reader` builds the questions a person's own department can ask from the kinds of
record actually indexed, but only kinds `row_scope_for` admits them to in that department, and
chooses the top three among those. Ranking first and cutting after would let the order of what
they may not reach decide what they are offered. Each question names the system to check the
answer in (M34.1.1.3), and a source whose records cannot be opened by their id in that system
contributes none.

Rejected: reading the counts from the connector's own API at the time the page is opened. A
connector keeps a small index and reads values live (`CONNECTORS_NEVER_BULK_SYNC`); a count made
live would be one call per source per page view against a rate ceiling shared with every question.

Scope: domain logic. Nothing here opens a connection, reads a clock or renders anything.

Task ids: M34.1.1.1, M34.1.1.2, M34.1.1.3, M34.1.2.1, M34.1.2.2, M34.1.2.3
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.adoption import (
    Action,
    AdoptionError,
    ConnectorOffer,
    Coverage,
    ScopeCoverage,
    SourceKind,
    StarterQuestion,
    Unanswered,
    connector_demand,
    coverage_report,
    first_connector,
    shopping_list,
    starter_questions,
)
from brain.connectors.declaration import ConnectorDeclaration
from brain.connectors.manifest import ConnectorManifest
from brain.console.adoption_view import reachable_departments
from brain.console.connector_detail import department_of
from brain.console.connector_trust import admitted_connections
from brain.core.entitlement import EntitlementSet
from brain.knowledge.rows import row_scope_for
from brain.ops.connector_store import Connection
from brain.ops.connector_sync import SyncState

# ------------------------------------------------------------------ written-down reasons
#: Why there is no coverage capability.
COVERAGE_IS_READ_UNDER_THE_GRANT_USAGE_IS_READ_UNDER: Final = (
    "How many records a source holds for a department and when it was last read are facts about "
    "that department's activity, like the questions it asked. A second grant would let a reader "
    "hold one and not the other and read across the gap, and a second scope check would drift, so "
    "the departments shown are exactly the ones the usage grant admits."
)

#: Why a source the reader may not name is merged.
A_SOURCE_YOU_MAY_NOT_NAME_IS_MERGED_AND_NEVER_DROPPED: Final = (
    "Dropping a connected source the reader may not be told of would make its department read "
    "not connected, which is false, and naming it would tell the reader what the company runs. "
    "The sources are added together under one label that names nothing, so the line is a true "
    "statement about the department."
)

#: What the merged line calls its source. Not a connector name, so it cannot be mistaken for one:
#: a connector's name is a lower-case word with no spaces.
UNNAMED_SOURCE: Final = "sources you are not shown by name"

#: The console setting that says which department a connection is for. Every source whose records
#: answer to one department asks for it under this name, and `department_of` reads the rule it
#: builds, so a test holds this against a source's own constant.
DEPARTMENT_SETTING: Final = "department"

#: The one scope an offer is made for when the reader reaches no named department, which is a new
#: install before its departments are founded. A source then answers for the company as a whole.
WHOLE_COMPANY: Final = "the whole company"


@dataclass(frozen=True)
class CoverageLine:
    """One department's statement about one source (or the merged ones), as a reader is told it.

    `source` is None only for a department with nothing connected where nothing on the install
    could be recommended, and then `state` is `NOT_CONNECTED` and there is nothing else to say.
    """

    department: str
    source: str | None
    state: Coverage
    #: A count of live index rows, and only with `last_sync`: see `ScopeCoverage`.
    records: int | None
    last_sync: datetime | None


@dataclass(frozen=True)
class CoverageStatement:
    """Everything the coverage view says to one reader. There is no total anywhere in it."""

    lines: tuple[CoverageLine, ...]
    shopping: tuple[Action, ...]


def addresses_a_department(one: ConnectorDeclaration) -> bool:
    """Whether the console form asks which department a connection is for.

    Such a source is connected for one department, and its records answer to that department alone
    (`department_of`); a source with no such setting is pinned to an organisation or an account.
    """
    return one.console is not None and any(
        setting.name == DEPARTMENT_SETTING for setting in one.console.settings
    )


def offers_of(
    declared: Mapping[str, ConnectorDeclaration],
    connected: Collection[str],
    departments: Iterable[str],
    *,
    only_for: str | None = None,
) -> tuple[ConnectorOffer, ...]:
    """The sources that could be connected here, described by what they would buy in week one.

    A source is `RECORDS` when its rows can be read on a schedule and each record can be read live
    by its id (a `reading` and a `live`), because that is a source with rows already there that a
    person can open in its own interface and compare; anything else is `DOCUMENTS`, which is the
    kind `first_connector` refuses to start with. Only sources the console can connect are offered,
    and none that is connected already: a source is connected once, so offering it again would
    recommend a thing that cannot be done.

    **How many departments an offer reaches is the property the widest-reach rule reads.** A source
    that asks which department it is for answers for one of them; one pinned to an organisation
    answers for all that are reachable. `only_for` asks what could be connected for one department
    and so offers only the sources that address a department. The reach arrives as a parameter and
    is narrowed by the caller, never here.
    """
    reachable = tuple(sorted(set(departments))) or (WHOLE_COMPANY,)
    offers: list[ConnectorOffer] = []
    for name, one in sorted(declared.items()):
        if one.console is None or name in connected:
            continue
        scoped = addresses_a_department(one)
        if only_for is not None and not scoped:
            continue
        if only_for is not None:
            places: tuple[str, ...] = (only_for,)
        elif scoped:
            places = reachable[:1]
        else:
            places = reachable
        offers.append(
            ConnectorOffer(
                name=name,
                kind=(
                    SourceKind.RECORDS
                    if one.reading is not None and one.live is not None
                    else SourceKind.DOCUMENTS
                ),
                departments=places,
                checkable_in_its_own_interface=one.live is not None,
            )
        )
    return tuple(offers)


def start_with(offers: Sequence[ConnectorOffer]) -> ConnectorOffer | None:
    """The source to connect first, or None when nothing offered could answer before an upload.

    `first_connector` refuses when every offer is a document source, and that refusal is a
    sentence for a conversation, not a state for a page: the page says nothing rather than
    recommending a week of uploading.
    """
    try:
        return first_connector(offers)
    except AdoptionError:
        return None


def coverage_for_reader(
    *,
    departments: Iterable[str],
    entitlement: EntitlementSet,
    now: datetime,
    connections: Sequence[Connection],
    manifests: Mapping[str, ConnectorManifest],
    synced: Mapping[str, SyncState],
    counts: Mapping[tuple[str, str, str], int],
    declared: Mapping[str, ConnectorDeclaration],
    unanswered: Sequence[Unanswered],
) -> CoverageStatement:
    """The coverage lines and the shopping list this reader may be shown (M34.1.2.1 to M34.1.2.3).

    `connections` are every live connection, unnarrowed, because a connection the reader may not
    be told of still makes its department connected; `counts` are `proj.record` counts per
    `(source, department, entity)` for the reachable departments only (the store takes them as its
    `WHERE`). `unanswered` are the recorded gaps as `Unanswered` rows, counted by
    `connector_demand` for the shopping list's order and for nothing else.
    """
    reachable = reachable_departments(departments, entitlement, now=now)
    nameable = {one.connector for one in admitted_connections(connections, entitlement, now)}
    rows: list[ScopeCoverage] = []
    merged: dict[str, list[tuple[datetime | None, int]]] = {}
    for connection in connections:
        place = department_of(manifests.get(connection.connector))
        if place is None or place not in reachable:
            continue
        state = synced.get(connection.connector)
        last = None if state is None else state.last_synced_at
        entities = tuple(
            sorted(
                (
                    (entity, held)
                    for (source, department, entity), held in counts.items()
                    if source == connection.connector and department == place and held > 0
                ),
                key=lambda one: (-one[1], one[0]),
            )
        )
        held = sum(count for _, count in entities)
        if connection.connector in nameable:
            rows.append(
                ScopeCoverage(
                    department=place,
                    source=connection.connector,
                    connected=True,
                    records=None if last is None else held,
                    last_sync=last,
                    entities=entities,
                )
            )
        else:
            merged.setdefault(place, []).append((last, held))
    for place, parts in merged.items():
        synced_parts = [(last, held) for last, held in parts if last is not None]
        rows.append(
            ScopeCoverage(
                department=place,
                source=UNNAMED_SOURCE,
                connected=True,
                records=sum(held for _, held in synced_parts) if synced_parts else None,
                last_sync=max((last for last, _ in synced_parts), default=None),
            )
        )
    covered = {one.department for one in rows}
    taken = {one.connector for one in connections}
    unsuggested: list[str] = []
    for place in sorted(reachable - covered):
        suggestion = start_with(offers_of(declared, taken, [place], only_for=place))
        if suggestion is None:
            unsuggested.append(place)
        else:
            rows.append(ScopeCoverage(department=place, source=suggestion.name, connected=False))
    report = coverage_report(rows, reachable)
    lines = [
        CoverageLine(
            department=one.department,
            source=one.source,
            state=one.state,
            records=one.records,
            last_sync=one.last_sync,
        )
        for one in report
    ]
    lines.extend(
        CoverageLine(
            department=place,
            source=None,
            state=Coverage.NOT_CONNECTED,
            records=None,
            last_sync=None,
        )
        for place in unsuggested
    )
    demand = connector_demand(unanswered, reachable)
    return CoverageStatement(
        lines=tuple(sorted(lines, key=lambda one: (one.department, one.source or ""))),
        shopping=shopping_list(report, reachable, demand),
    )


def starter_for_reader(
    *,
    department: str,
    entitlement: EntitlementSet,
    now: datetime,
    connections: Sequence[Connection],
    manifests: Mapping[str, ConnectorManifest],
    synced: Mapping[str, SyncState],
    counts: Mapping[tuple[str, str, str], int],
    declared: Mapping[str, ConnectorDeclaration],
) -> tuple[StarterQuestion, ...]:
    """Up to three questions about what this person's own department has indexed (M34.1.1.2).

    **The reader's own reach is applied before anything is ranked.** An entity is a candidate only
    when `row_scope_for` admits the reader to rows of that kind in this department (the same
    function the answer lane reads, so "may this person ask about it" has one answer), and the
    top three are chosen among those. Ranking first and filtering after would let the order of
    what the reader may not reach decide which of the rest they are offered, which is a signal
    about it. The department is the person's own and one, so a list of departments cannot be
    built from this. No count is returned or implied: a thin department gets fewer questions, as
    `brain.adoption.starter_questions` argues it should.

    A question names the source to check the answer in, and a source with no live lookup of a
    record by its id (`checkable`) contributes none: see
    `brain.adoption.AN_ANSWER_NOBODY_CAN_CHECK_IS_A_DEMONSTRATION`.
    """
    rows: list[ScopeCoverage] = []
    place: dict[str, object] = {"department": department}
    for connection in connections:
        if department_of(manifests.get(connection.connector)) != department:
            continue
        state = synced.get(connection.connector)
        last = None if state is None else state.last_synced_at
        entities = tuple(
            sorted(
                (
                    (entity, held)
                    for (source, place_of, entity), held in counts.items()
                    if source == connection.connector
                    and place_of == department
                    and held > 0
                    and _may_ask_about(entity, entitlement, now, place)
                ),
                key=lambda one: (-one[1], one[0]),
            )
        )
        rows.append(
            ScopeCoverage(
                department=department,
                source=connection.connector,
                connected=True,
                records=None if last is None else sum(held for _, held in entities),
                last_sync=last,
                entities=entities,
            )
        )
    checkable = frozenset(name for name, one in declared.items() if one.live is not None)
    return starter_questions(rows, department, checkable=checkable)


def _may_ask_about(
    entity: str, entitlement: EntitlementSet, now: datetime, place: Mapping[str, object]
) -> bool:
    """Whether the reader holds rows of this kind in this department: `row_scope_for`, matched."""
    held = row_scope_for(entity, entitlement, now)
    return held is not None and held.matches(dict(place))
