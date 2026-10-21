"""What each department is told of its coverage, and which first questions it is offered.

`brain.console.adoption_coverage` decides from values handed in, so these tests hand it values and
read what comes back. The route half (the switch, the wiring to the connection and record stores) is
`tests/unit/test_adoption_coverage_routes.py`.

Task ids: M34.1.1.1, M34.1.1.2, M34.1.1.3, M34.1.2.1, M34.1.2.2, M34.1.2.3
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Final

from brain.adoption import (
    Action,
    Coverage,
    Need,
    SourceKind,
    StarterQuestion,
    Unanswered,
    coverage_gaps,
)
from brain.connectors.contract import HealthState
from brain.connectors.freshdesk import DEPARTMENT_SETTING as FRESHDESK_DEPARTMENT_SETTING
from brain.connectors.manifest import ConnectorManifest, manifest_digest
from brain.console.adoption_coverage import (
    DEPARTMENT_SETTING,
    UNNAMED_SOURCE,
    WHOLE_COMPANY,
    CoverageLine,
    CoverageStatement,
    addresses_a_department,
    coverage_for_reader,
    offers_of,
    start_with,
    starter_for_reader,
)
from brain.console.connector_trust import THE_SCREEN
from brain.console.screens import screen
from brain.console.spend_view import USAGE_AUTHORITY
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.knowledge.rows import entity_capability
from brain.ops.connectable import manifest_for
from brain.ops.connector_catalogue import declarations
from brain.ops.connector_store import Connection
from brain.ops.connector_sync import SyncOutcome, SyncState

#: Far outside any plausible wall clock, so no grant here can lapse while the suite runs.
NOW: Final = datetime(2999, 1, 1, 12, 0, tzinfo=UTC)
SYNCED: Final = datetime(2999, 1, 1, 9, 30, tzinfo=UTC)

CONNECTORS: Final[Capability] = screen(THE_SCREEN).read.requires

SUPPORT_SETTINGS: Final = {"domain": "example.freshdesk.com", "department": "support"}


def a_freshdesk(
    settings: Mapping[str, str] = SUPPORT_SETTINGS,
) -> tuple[Connection, ConnectorManifest]:
    manifest = manifest_for("freshdesk", dict(settings))
    return (
        Connection(
            connector="freshdesk",
            settings=dict(settings),
            digest=manifest_digest(manifest),
            connected_by="u_admin",
            connected_at=SYNCED,
        ),
        manifest,
    )


def a_state(last: datetime | None = SYNCED) -> SyncState:
    return SyncState(
        connector="freshdesk",
        finished_at=SYNCED,
        outcome=SyncOutcome.SYNCED if last is not None else SyncOutcome.FAILED,
        health=HealthState.OK,
        consecutive_failures=0,
        next_attempt_at=NOW,
        detail="read",
        last_synced_at=last,
    )


def a_reader(
    *, usage: Scope | None, connectors: Scope | None = None, rows: Mapping[str, Scope] | None = None
) -> EntitlementSet:
    grants: list[Grant] = []
    if usage is not None:
        grants.append(Grant(capability=USAGE_AUTHORITY, scope=usage))
    if connectors is not None:
        grants.append(Grant(capability=CONNECTORS, scope=connectors))
    for entity, scope in (rows or {}).items():
        grants.append(Grant(capability=entity_capability(entity), scope=scope))
    return EntitlementSet(principal_id="p_reader", grants=tuple(grants))


#: The ticket counts the store would return: support's own, and sales' that nobody connected.
COUNTS: Final = {
    ("freshdesk", "support", "ticket"): 120,
    ("freshdesk", "support", "company"): 7,
    ("freshdesk", "sales", "ticket"): 4242,
}


def statement(
    reader: EntitlementSet,
    *,
    departments: tuple[str, ...] = ("sales", "support"),
    synced: Mapping[str, SyncState] | None = None,
    connect: bool = True,
    unanswered: tuple[Unanswered, ...] = (),
) -> tuple[CoverageLine, ...]:
    return full_statement(
        reader, departments=departments, synced=synced, connect=connect, unanswered=unanswered
    ).lines


def full_statement(
    reader: EntitlementSet,
    *,
    departments: tuple[str, ...] = ("sales", "support"),
    synced: Mapping[str, SyncState] | None = None,
    connect: bool = True,
    unanswered: tuple[Unanswered, ...] = (),
) -> CoverageStatement:
    connection, manifest = a_freshdesk()
    return coverage_for_reader(
        departments=departments,
        entitlement=reader,
        now=NOW,
        connections=(connection,) if connect else (),
        manifests={"freshdesk": manifest} if connect else {},
        synced={"freshdesk": a_state()} if synced is None else synced,
        counts=COUNTS,
        declared=declarations(),
        unanswered=unanswered,
    )


# ------------------------------------------------------------------ the statement per department
def test_a_department_with_a_connected_source_is_told_its_records_and_its_last_read() -> None:
    """The positive case: support has freshdesk connected and read, so its line names the source,
    says it is connected, and carries the count of the index rows for support and the instant of the
    last read. Delete this and every refusal test below is satisfied by a function that returns
    nothing at all."""
    reader = a_reader(usage=Scope.unrestricted(), connectors=Scope.unrestricted())
    [line] = [one for one in statement(reader) if one.department == "support"]
    assert (line.source, line.state) == ("freshdesk", Coverage.CONNECTED)
    assert (line.records, line.last_sync) == (127, SYNCED)


def test_a_department_with_nothing_connected_is_said_to_be_so_and_is_not_a_zero() -> None:
    """Sales has no source connected, so its line is not-connected with no count and no time, which
    is a different fact from a connected source that returned nothing. Delete this and a department
    nobody has connected anything for reads as 0 records, telling it the system looked and found
    nothing when it never looked."""
    reader = a_reader(usage=Scope.unrestricted(), connectors=Scope.unrestricted())
    [line] = [one for one in statement(reader) if one.department == "sales"]
    assert line.state is Coverage.NOT_CONNECTED
    assert (line.records, line.last_sync) == (None, None)
    assert line.source is not None
    assert line.source != "freshdesk", "a source that is connected already is never recommended"


def test_a_connected_source_that_has_never_been_read_is_connected_with_no_records() -> None:
    """A connection whose worker has not yet read it to the end has no count and no time, and says
    connected with no records yet, which is not the same as not connected. Delete this and a fresh
    connection reads as not connected for a day and the champion authorises it twice."""
    reader = a_reader(usage=Scope.unrestricted(), connectors=Scope.unrestricted())
    [line] = [
        one
        for one in statement(reader, synced={"freshdesk": a_state(None)})
        if one.department == "support"
    ]
    assert (line.state, line.records, line.last_sync) == (Coverage.CONNECTED_NO_RECORDS, None, None)


def test_a_source_the_reader_may_not_name_is_merged_and_never_dropped_or_named() -> None:
    """A reader who may read usage for support but holds no Connectors grant is told support is
    connected, with its records, under a label that names nothing. Delete this and the department
    reads not connected, which is false, or the line names the source, which tells the reader what
    the company runs."""
    reader = a_reader(usage=Scope.department("support"))
    [line] = statement(reader)
    assert (line.department, line.source, line.state) == (
        "support",
        UNNAMED_SOURCE,
        Coverage.CONNECTED,
    )
    assert (line.records, line.last_sync) == (127, SYNCED)
    assert "freshdesk" not in repr(line)


def test_a_merged_source_that_was_never_read_is_connected_with_no_records() -> None:
    """A reader who may not name the source, and whose department's source has not been read to the
    end, is told connected with no records and no time, the same as a named source. Delete this and
    the merged line either counts a source that was never read or fails to build."""
    reader = a_reader(usage=Scope.department("support"))
    [line] = statement(reader, synced={"freshdesk": a_state(None)})
    assert (line.source, line.state, line.records, line.last_sync) == (
        UNNAMED_SOURCE,
        Coverage.CONNECTED_NO_RECORDS,
        None,
        None,
    )


def test_a_reader_is_told_only_of_the_departments_their_usage_grant_admits() -> None:
    """With usage for support alone, sales has no line at all, though the directory holds it and
    the store was given its counts; and nothing in what comes back carries sales' figure. Delete
    this and a department lead reads another department's record count, or the existence of one
    they may not see."""
    reader = a_reader(usage=Scope.department("support"), connectors=Scope.unrestricted())
    given = full_statement(reader)
    assert {one.department for one in given.lines} == {"support"}
    assert "4242" not in repr(given) and "sales" not in repr(given)
    assert all(one.department == "support" for one in given.shopping)


def test_a_reader_with_no_usage_grant_is_told_nothing_and_not_refused() -> None:
    """An empty statement for a reader holding no usage grant, as the adoption figures answer
    them: a refusal would tell them a coverage view exists. Delete this and the view answers an
    ungranted reader with lines."""
    given = full_statement(a_reader(usage=None, connectors=Scope.unrestricted()))
    assert given.lines == () and given.shopping == ()


def test_sources_pinned_to_an_organisation_belong_to_no_departments_line() -> None:
    """Xero's rule names no department, so it is not attributed to any: connecting it leaves
    support and sales exactly as they were. Delete this and the same figure appears in every
    department's line."""
    reader = a_reader(usage=Scope.unrestricted(), connectors=Scope.unrestricted())
    settings = {"tenant_id": "11111111-2222-3333-4444-555555555555"}
    manifest = manifest_for("xero", settings)
    xero = Connection(
        connector="xero",
        settings=settings,
        digest=manifest_digest(manifest),
        connected_by="u_admin",
        connected_at=SYNCED,
    )
    with_xero = coverage_for_reader(
        departments=("sales", "support"),
        entitlement=reader,
        now=NOW,
        connections=(xero,),
        manifests={"xero": manifest},
        synced={},
        counts={},
        declared=declarations(),
        unanswered=(),
    )
    assert all(one.source != "xero" for one in with_xero.lines)
    assert {one.department for one in with_xero.lines} == {"sales", "support"}
    assert all(one.state is Coverage.NOT_CONNECTED for one in with_xero.lines)


def test_the_statement_carries_no_total_percentage_or_how_many_of_how_many() -> None:
    """Whatever the page says per line passes `coverage_gaps`, and the statement object has no field
    that adds lines together. Delete this and a progress figure can be added beside the list
    without a test noticing, which `brain.adoption` exists to prevent."""
    reader = a_reader(usage=Scope.unrestricted(), connectors=Scope.unrestricted())
    given = full_statement(reader)
    said = [
        f"{one.department} {one.source} {one.state.value} {one.records} {one.last_sync}"
        for one in given.lines
    ]
    assert coverage_gaps(said) == ()
    assert set(type(given).__dataclass_fields__) == {"lines", "shopping"}


def test_the_shopping_list_puts_the_department_people_asked_about_first() -> None:
    """Two departments with nothing connected: the one whose questions went unanswered the most
    comes first, and a connected department has no action. Delete this and the champion is handed
    the list in alphabetical order, which is about the product and not about the company."""
    reader = a_reader(usage=Scope.unrestricted(), connectors=Scope.unrestricted())
    asked = tuple(Unanswered("ops", "cloudflare") for _ in range(3))
    given = full_statement(
        reader,
        departments=("legal", "ops", "support"),
        connect=True,
        unanswered=asked,
    )
    assert [one.department for one in given.shopping] == ["ops", "legal"]
    assert all(
        isinstance(one, Action) and one.need is Need.AUTHORISE_THE_SOURCE for one in given.shopping
    )


# ------------------------------------------------------------------ the first connector
def test_a_source_that_asks_for_a_department_answers_for_one_and_the_widest_reach_wins() -> None:
    """Of the sources the console can connect, the recommendation is a records source and, because
    one pinned to an organisation reaches every reachable department where one asking for a
    department reaches one, it is one pinned to an organisation. Delete this and the recommendation
    drifts to whichever name sorts first."""
    chosen = start_with(offers_of(declarations(), set(), ["sales", "support"]))
    assert chosen is not None
    assert chosen.kind is SourceKind.RECORDS
    assert not addresses_a_department(declarations()[chosen.name])
    assert chosen.departments == ("sales", "support")


def test_what_could_be_connected_for_one_department_is_only_what_asks_for_a_department() -> None:
    """Asked for one department, the offers are the sources that ask which department a connection
    is for, each reaching that department alone; a source pinned to an organisation is not among
    them. Delete this and a not-connected department is told to authorise a source that cannot be
    connected for it, which would then belong to every department and to none."""
    offered = offers_of(declarations(), set(), ["sales", "support"], only_for="sales")
    assert offered
    assert all(addresses_a_department(declarations()[one.name]) for one in offered)
    assert all(one.departments == ("sales",) for one in offered)
    organisation = offers_of(declarations(), set(), ["sales", "support"])
    assert any(not addresses_a_department(declarations()[one.name]) for one in organisation)


def test_a_source_already_connected_is_never_offered_again() -> None:
    """Offers exclude the connected, so a source that cannot be connected twice is never the
    recommendation. Delete this and the screen recommends the thing already done."""
    everything = {name for name, one in declarations().items() if one.console is not None}
    assert offers_of(declarations(), everything, ["sales"]) == ()
    assert start_with(()) is None


def test_a_new_install_with_no_department_is_offered_a_source_for_the_whole_company() -> None:
    """With no department founded yet the offers are made for the company as a whole, so the
    first-connector card works on the first day of an install. Delete this and a new install, the
    one that most needs the recommendation, is told nothing."""
    offered = offers_of(declarations(), set(), [])
    assert offered and all(WHOLE_COMPANY in one.departments for one in offered)


def test_the_department_setting_is_the_name_the_sources_ask_for() -> None:
    """The module's constant is held against a source's own, which is the name its form uses. Delete
    this and a rename in the sources leaves every source reading as pinned to an organisation."""
    assert DEPARTMENT_SETTING == FRESHDESK_DEPARTMENT_SETTING
    assert addresses_a_department(declarations()["freshdesk"])
    assert not addresses_a_department(declarations()["xero"])


def test_a_documents_only_install_is_recommended_nothing_rather_than_an_upload() -> None:
    """Offers that are all documents recommend nothing, so the card is not shown. Delete this and
    the recommendation becomes a week of uploading files."""
    only_documents = {
        name: one
        for name, one in declarations().items()
        if name in {"google_drive", "slack_messages"}
    }
    assert start_with(offers_of(only_documents, set(), ["sales"])) is None


# ------------------------------------------------------------------ the starter questions
def questions(
    reader: EntitlementSet, *, department: str = "support", live: bool = True
) -> tuple[StarterQuestion, ...]:
    connection, manifest = a_freshdesk()
    declared = declarations()
    return starter_for_reader(
        department=department,
        entitlement=reader,
        now=NOW,
        connections=(connection,),
        manifests={"freshdesk": manifest},
        synced={"freshdesk": a_state()},
        counts=COUNTS,
        declared=declared if live else {k: v for k, v in declared.items() if k != "freshdesk"},
    )


def test_a_person_is_offered_questions_about_the_records_they_may_read_in_their_department() -> (
    None
):
    """With the ticket grant over support, the person is offered a question about tickets that
    names the system to check it in. Delete this and the refusals below are satisfied by a function
    that never suggests anything."""
    reader = a_reader(usage=None, rows={"ticket": Scope.department("support")})
    found = questions(reader)
    assert [(one.entity, one.check_in) for one in found] == [("ticket", "freshdesk")]


def test_a_kind_of_record_the_person_may_not_read_is_never_suggested() -> None:
    """The company kind has fewer rows than tickets, but even with a larger count a kind the person
    holds no grant for is not offered, and one granted for another department is not either. Delete
    this and a suggestion discloses a kind of record the person cannot reach."""
    other_department = a_reader(usage=None, rows={"ticket": Scope.department("sales")})
    assert questions(other_department) == ()
    nothing = a_reader(usage=None)
    assert questions(nothing) == ()
    only_company = a_reader(usage=None, rows={"company": Scope.department("support")})
    assert [one.entity for one in questions(only_company)] == ["company"]


def test_the_order_of_what_the_person_may_not_reach_does_not_decide_what_they_are_offered() -> None:
    """Reach is applied before the ranking: a reader of company alone is offered company even
    though tickets, which they cannot read, are far more numerous. Delete this and the ranking runs
    first and the reader gets nothing, or the top of the unreachable list decides the rest."""
    reader = a_reader(usage=None, rows={"company": Scope.unrestricted()})
    assert [one.entity for one in questions(reader)] == ["company"]


def test_a_source_declared_with_no_live_lookup_contributes_no_question_either() -> None:
    """The source is still declared, but its declaration reads no record live by its id, so there is
    no record to open in its own system and no question. Delete this and removing a source from
    the declarations is the only way a source is kept out, and one that is declared and cannot be
    checked is offered."""
    reader = a_reader(usage=None, rows={"ticket": Scope.department("support")})
    connection, manifest = a_freshdesk()
    declared = dict(declarations())
    declared["freshdesk"] = dataclasses.replace(declared["freshdesk"], live=None)
    found = starter_for_reader(
        department="support",
        entitlement=reader,
        now=NOW,
        connections=(connection,),
        manifests={"freshdesk": manifest},
        synced={"freshdesk": a_state()},
        counts=COUNTS,
        declared=declared,
    )
    assert found == ()


def test_a_source_a_person_cannot_check_in_its_own_system_contributes_no_question() -> None:
    """With the source's live lookup absent from the declarations, there is no system to check the
    answer in, so there is no question. Delete this and a first answer nobody can verify is offered,
    which `brain.adoption` calls a demonstration."""
    reader = a_reader(usage=None, rows={"ticket": Scope.department("support")})
    assert questions(reader, live=False) == ()


def test_rows_an_earlier_connection_left_for_another_department_are_not_offered() -> None:
    """A source reconnected for sales still has the rows it indexed for support. Support's person is
    offered nothing from them, because the connection is no longer support's. Delete this and a
    department is suggested questions about a source that is connected for a different one."""
    connection, manifest = a_freshdesk({"domain": "example.freshdesk.com", "department": "sales"})
    reader = a_reader(usage=None, rows={"ticket": Scope.department("support")})
    found = starter_for_reader(
        department="support",
        entitlement=reader,
        now=NOW,
        connections=(connection,),
        manifests={"freshdesk": manifest},
        synced={"freshdesk": a_state()},
        counts=COUNTS,
        declared=declarations(),
    )
    assert found == ()


def test_no_department_means_no_question_and_nothing_is_said_about_other_departments() -> None:
    """A person in a department with no source connected for it is offered none. Delete this and a
    question about another department's records is offered because the data exists."""
    reader = a_reader(usage=None, rows={"ticket": Scope.unrestricted()})
    assert questions(reader, department="legal") == ()
