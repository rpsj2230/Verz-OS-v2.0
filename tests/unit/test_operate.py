"""The operate and report screens held to honest counting, screen by screen.

Every test below hands over grants and rows and asks what comes back. Nothing appoints
anybody to a role, because no function in the module reads one.

The spine is the landing screen. A figure is over everybody exactly when the reader could
open the screen behind it and count the rows there, a figure with no narrower version is
withheld rather than narrowed, and two figures for one screen are refused because the
difference between them is a count of work belonging to people the reader cannot see
(M27.2.1). The register's claim about which figures narrow is checked against the row types
themselves rather than believed, so mutating one entry fails a test that never reads the
register.

Then, screen by screen: a run is visible to the person it runs for and otherwise needs a
grant whose scope matches the row, and a run row carries no arguments (M27.2.2). A source out
of reach is absent from the health table rather than shown without detail (M27.2.4). A reader
holding no read of the knowledge plane is shown no coverage at all, an area they do not reach
has no row, and an area they reach holding nothing they may see is a row at zero (M27.2.5).
The queue's depth is over the waiting jobs the reader may see and its basis is the same answer
an agent's schedule tab gets from the same screen (M27.2.6). An incident on a source out of
reach is absent, and what a degradation blocks is the tools its own manifest declares
(M27.2.7). A halt on everything reaches a reader whose scope admits no target, because it
stops them, and an unreadable halt store is not reported as nothing being stopped (M27.2.8).
A refusal is not counted as a gap (M27.4.1). The ceiling panel carries no amount (M27.4.3). A
canary finding naming a field out of reach is absent (M27.4.4).

Real `EntitlementSet`s, real `JobRecord`s, a real `ConnectorManifest`, real `KnowledgeItem`s
and a real `Reach` built by `brain.knowledge.search.reach_for` throughout. The coverage tests
in particular build items from their own visibility rather than asserting on a verdict handed
in, because `Reach.admits` is the producer here and a test that supplied the answer would be
testing the consumer twice.

Task ids: M27.2.1, M27.2.2, M27.2.4, M27.2.5, M27.2.6, M27.2.7, M27.2.8
Task ids: M27.4.1, M27.4.3, M27.4.4
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import UTC, datetime, timedelta

import pytest

from brain.chat.turns import Turn, TurnKind
from brain.connectors.contract import (
    ConnectorHealth,
    ConnectorScope,
    CredentialBinding,
    HealthState,
    TransportKind,
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
from brain.connectors.registry import ConnectorState, RegisteredConnector
from brain.console.agent_automations import schedule_basis
from brain.console.agent_output import basis_over
from brain.console.operate import (
    ATTRIBUTION_FIELD,
    COVERAGE_BANDS,
    EXECUTING,
    GAP_REASONS,
    LANDING,
    MATRIX_SURFACES,
    NAMES_A_FIGURE_WOULD_ARRIVE_THROUGH,
    OPERATE_ROWS,
    PANEL_COUNT,
    PANELS,
    WAITING,
    Attribution,
    ConnectorRow,
    CoverageRow,
    Gap,
    OperateError,
    Overview,
    Panel,
    RunRow,
    Tile,
    blocked_by,
    ceiling_effect,
    ceilings_in_reach,
    connector_rows,
    coverage,
    findings_in_reach,
    freshness_of,
    gaps,
    incidents,
    may_watch,
    operate_gaps,
    overview,
    panel,
    queue_basis,
    queue_summary,
    reachable_connectors,
    run_rows,
    stop_is_unknown,
    stopped_for,
    tile,
    usage_gaps,
    visible_questions,
    visible_runs,
)
from brain.console.reads import Plane, plane_capability
from brain.console.screens import SCREENS, Group, screen
from brain.console.workspace import Basis, intersections_in
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Clause, Op, Scope
from brain.gate.abstain import AbstentionReason, SearchScope, nothing_connected, nothing_retrieved
from brain.gate.context import TrafficClass
from brain.gate.provenance import Freshness
from brain.knowledge.item import KnowledgeItem, KnowledgeState
from brain.knowledge.visibility import KnowledgeVisibility
from brain.ops.budgets import Allowance, BudgetLevel, BudgetPeriod, BudgetRow
from brain.ops.canaries import CanaryFinding, Finding
from brain.ops.halt import Halt, HaltScope, HaltState, stop_everything
from brain.ops.jobs import (
    STATES_WITHOUT_AN_ATTEMPT,
    TERMINAL,
    JobRecord,
    JobState,
    hidden_count_fields,
)
from brain.ops.queue import Job
from brain.ops.secrets import SecretRef, VaultRole
from brain.ops.spend import LADDER, Refusal

#: A fixed moment, so a freshness test cannot pass because the machine's clock happened to
#: sit on the convenient side of a band boundary.
NOW = datetime(2027, 5, 4, 10, 0, tzinfo=UTC)

#: Two departments, so a scoped reader has somewhere to be refused.
MAINTENANCE = "maintenance"
FINANCE = "finance"

READER = "u_reader"
COLLEAGUE = "u_colleague"

#: What each screen's own tool asks for, read off the registry rather than spelled again, so
#: repointing a screen's capability moves the tests with it.
RUN_READ = screen("runs").read.requires.value
QUEUE_READ = screen("queue").read.requires.value
HALT_ADMIN = screen("halt").read.requires.value
BUDGET_READ = screen("budget").read.requires.value
QUESTION_READ = screen("questions").read.requires.value
KNOWLEDGE_READ = "read:knowledge"


def holding(
    *capabilities: str,
    planes: tuple[Plane, ...] = (Plane.CONFIGURATION,),
    scope: Scope | None = None,
    principal_id: str = READER,
) -> EntitlementSet:
    """A reader holding these capabilities in one scope, plus the plane grants named.

    Built here rather than taken from a fixture so a test can hold the tool's capability and
    not the plane, or hold the same capability in two different scopes, which is what most of
    the narrowing tests below vary.
    """
    where = scope if scope is not None else Scope(clauses=())
    grants = [Grant(capability=Capability(value=one), scope=where) for one in capabilities]
    grants += [Grant(capability=plane_capability(one), scope=where) for one in planes]
    return EntitlementSet(principal_id=principal_id, grants=tuple(grants))


def a_job(
    *,
    job_id: str = "j1",
    principal_id: str = READER,
    task: str = "answer",
    state: JobState = JobState.RUNNING,
    attempts: int = 1,
    args: dict[str, str | int] | None = None,
    scheduled_at: datetime = NOW,
) -> JobRecord:
    return JobRecord(
        job_id=job_id,
        job=Job(task=task, traffic_class=TrafficClass.HUMAN_INTERACTIVE, args=args or {}),
        principal_id=principal_id,
        scheduled_at=scheduled_at,
        state=state,
        attempts=attempts,
    )


def an_item(
    *,
    item_id: str,
    visibility: KnowledgeVisibility,
    owner_id: str = COLLEAGUE,
    state: KnowledgeState = KnowledgeState.PUBLISHED,
    verified_at: datetime | None = None,
) -> KnowledgeItem:
    verified = {"verified_by": "u_steward", "verified_at": verified_at} if verified_at else {}
    return KnowledgeItem(
        item_id=item_id,
        content="something written down",
        visibility=visibility,
        owner_id=owner_id,
        state=state,
        **verified,  # type: ignore[arg-type]
    )


def a_manifest(
    *, name: str = "laravel", tools: tuple[str, ...] = ("laravel.read_client",)
) -> ConnectorManifest:
    return ConnectorManifest(
        name=name,
        version="1.0.0",
        transport=TransportKind.DATABASE,
        scope=ConnectorScope(resource_kind="view", selectors=("portal.v_client",)),
        credential=CredentialBinding(
            ref=SecretRef(path="database/creds/ro", role=VaultRole.APPLICATION)
        ),
        tools=tuple(
            ToolDeclaration(name=one, description="One row from the source.", entity="client")
            for one in tools
        ),
        projections=(
            ProjectedEntity(
                entity="client",
                fields=(
                    ProjectedField(name="id", shape=FieldShape.IDENTIFIER, uses=(HotUse.IDENTIFY,)),
                ),
                change_signal=ChangeSignal.UPDATED_SINCE,
                visibility=Scope.department(MAINTENANCE),
            ),
        ),
        ceiling="xero",
    )


def a_registered(name: str, state: ConnectorState = ConnectorState.ENABLED) -> RegisteredConnector:
    return RegisteredConnector(manifest=a_manifest(name=name), digest="d" * 64, state=state)


def a_budget_row(
    *, level: BudgetLevel = BudgetLevel.DEPARTMENT, subject: str = MAINTENANCE
) -> BudgetRow:
    return BudgetRow(
        level=level,
        subject=subject,
        period=BudgetPeriod.MONTH,
        ceiling_minor=100_000,
        version=1,
        author="u_owner",
        effective_from=NOW - timedelta(days=1),
    )


def department_scope(name: str) -> Scope:
    return Scope(clauses=(Clause(field="department", op=Op.EQ, value=name),))


# ------------------------------------------------------- honest counting (M27.2.1)
def test_a_front_page_figure_is_everybodys_only_when_the_screen_behind_it_could_be_opened():
    """Deleting this lets the landing screen publish the size of what a reader cannot see.
    A figure over everybody's rows is exactly as sensitive as the screen it came from, and
    the whole rule is that the grant behind the number is the grant behind the page."""
    rows = [a_job(job_id="j1", principal_id=READER), a_job(job_id="j2", principal_id=COLLEAGUE)]

    granted = tile(panel("runs"), rows, holding(RUN_READ), NOW)
    assert granted == Tile(key="runs", basis=Basis.EVERYONE, value=2)

    without = tile(panel("runs"), rows, holding(), NOW)
    assert without == Tile(key="runs", basis=Basis.OWN, value=1)


def test_a_figure_with_no_narrower_version_is_withheld_rather_than_narrowed():
    """Deleting this lets the corpus be narrowed to the reader's own documents and rendered
    under a heading reading documents. Your share of the corpus is not a smaller true figure,
    it is a different one, and it would be read as the size of everything."""
    items = ["not a row type, and never read on this branch"]

    assert tile(panel("knowledge_coverage"), items, holding(), NOW) is None

    granted = holding(screen("knowledge_coverage").read.requires.value)
    assert tile(panel("knowledge_coverage"), items, granted, NOW) == Tile(
        key="knowledge_coverage", basis=Basis.EVERYONE, value=1
    )


def test_a_per_person_figure_over_rows_belonging_to_nobody_is_refused():
    """Deleting this lets a per-person panel be pointed at rows carrying no principal, where
    the narrower figure silently comes out zero for everybody and the front page reads as an
    idle system rather than as a misconfigured register."""

    @dataclass(frozen=True)
    class Anonymous:
        what: str

    with pytest.raises(OperateError, match=ATTRIBUTION_FIELD):
        tile(panel("runs"), [Anonymous(what="x")], holding(), NOW)


def test_a_tile_reporting_fewer_than_no_rows_is_refused():
    """**Written because a mutation of this guard survived the whole file.** Every tile built
    anywhere in these tests was counted from a list, so the refusal could be deleted and
    nothing would have noticed.

    A negative figure is not a count of anything, and the way one arrives is arithmetic: a
    subtraction of what was hidden from what exists is exactly the operation this module is
    built to make impossible, and it is the operation that produces a negative number when
    the two figures come from different filters. So a tile carrying one is the shape of the
    disclosure this whole screen refuses, arriving as a rendering bug.

    Zero is the sibling and it is not the same case: a reader who may see nothing is shown a
    nought, which is honest and is the point of several of these screens.

    Delete this and a subtraction reaches the front page as a minus sign."""
    with pytest.raises(OperateError, match="not a count of anything"):
        Tile(key="runs", basis=Basis.EVERYONE, value=-1)

    assert Tile(key="runs", basis=Basis.OWN, value=0).value == 0


def test_the_landing_screen_says_nothing_about_a_figure_it_withheld():
    """Deleting this lets a placeholder, a greyed panel or a count of withheld tiles back
    onto the front page. Each says the same thing a number would: that there is a screen here
    the reader may not open, which the menu already declines to say."""
    shown = overview([Tile(key="runs", basis=Basis.OWN, value=1), None, None])

    assert shown == Overview(tiles=(Tile(key="runs", basis=Basis.OWN, value=1),))
    assert [one.name for one in fields(Overview)] == ["tiles"]


def test_two_figures_for_one_screen_are_refused_because_the_difference_is_a_count():
    """Deleting this lets a reader see their own runs beside everybody's runs, which hands
    them the difference. That is a count of other people's work arrived at without anybody
    publishing it, and it is the subtraction disclosure with two labels on it."""
    with pytest.raises(OperateError, match="two figures"):
        overview(
            [
                Tile(key="runs", basis=Basis.OWN, value=1),
                Tile(key="runs", basis=Basis.EVERYONE, value=9),
            ]
        )


def test_the_landing_screen_puts_its_figures_in_the_registers_order():
    """Deleting this leaves the order to whatever the caller assembled, so two readings of an
    unchanged system put the same figure in different places and a reader comparing two
    screenshots reads a change that did not happen."""
    shown = overview(
        [
            Tile(key="quality", basis=Basis.EVERYONE, value=1),
            Tile(key="runs", basis=Basis.EVERYONE, value=2),
            Tile(key="connectors", basis=Basis.EVERYONE, value=3),
        ]
    )

    order = [one.key for one in PANELS]
    assert [one.key for one in shown.tiles] == sorted(
        ["quality", "runs", "connectors"], key=order.index
    )


def test_a_figure_from_a_screen_nobody_registered_is_refused():
    """Deleting this lets a tile whose key matches no panel onto the front page, where it
    carries a basis nothing decided and a number nothing counted."""
    with pytest.raises(OperateError, match="unregistered"):
        overview([Tile(key="invented", basis=Basis.EVERYONE, value=1)])


# ------------------------------------------------------------ the register (M27.2.1)
def test_a_screen_whose_rows_carry_a_principal_is_the_one_declared_per_person():
    """Deleting this lets the register claim an attribution its rows cannot support, in
    either direction: a whole-install label on attributable rows withholds a figure that
    could honestly have been narrowed, and a per-person label on rows belonging to nobody
    makes every reader's figure zero. Neither shows up as an error."""
    assert operate_gaps() == ()

    real = panel("runs")
    mislabelled = Panel(
        key=real.key,
        row=real.row,
        counts=real.counts,
        attribution=Attribution.WHOLE_INSTALL,
        shows=real.shows,
        never=real.never,
    )
    found = operate_gaps(panels=[*[one for one in PANELS if one.key != "runs"], mislabelled])
    assert any("carries principal_id" in one for one in found)

    corpus = panel("knowledge_coverage")
    other = Panel(
        key=corpus.key,
        row=corpus.row,
        counts=corpus.counts,
        attribution=Attribution.PER_PERSON,
        shows=corpus.shows,
        never=corpus.never,
    )
    found = operate_gaps(
        panels=[*[one for one in PANELS if one.key != "knowledge_coverage"], other]
    )
    assert any("carries no principal_id" in one for one in found)


def test_every_operate_and_report_screen_but_the_landing_one_lends_a_figure():
    """Deleting this lets a screen exist with no rule about what its front-page figure may
    say, which is the state every one of these leaks starts from: somebody adds a number to
    the landing screen because the screen exists and nothing says how it must be counted."""
    wanted = {
        one.key
        for one in SCREENS
        if one.group in (Group.OPERATE, Group.REPORT) and one.key != LANDING
    }

    assert {one.key for one in PANELS} == wanted
    assert len(PANELS) == PANEL_COUNT

    short = [one for one in PANELS if one.key != "quality"]
    assert any("lends the landing screen no figure" in one for one in operate_gaps(panels=short))


def test_the_landing_screen_may_not_lend_itself_a_figure():
    """Deleting this lets the overview count its own panels, and the only figure it could
    produce is how many of the others it managed to show, which is the count of what it hid."""
    with pytest.raises(OperateError, match="lending itself a figure"):
        Panel(
            key=LANDING,
            row="brain.ops.jobs.JobRecord",
            counts="panels it managed to show",
            attribution=Attribution.WHOLE_INSTALL,
            shows="everything",
            never="nothing",
        )


def test_no_row_on_these_surfaces_can_say_how_much_was_withheld():
    """Deleting this lets a total, a hidden count or an of_total field be added to a row by
    somebody making a screen more useful, which is how this failure always arrives."""
    assert hidden_count_fields(OPERATE_ROWS) == ()
    assert operate_gaps(rows=[*OPERATE_ROWS, _WithATotal]) != ()


@dataclass(frozen=True)
class _WithATotal:
    """A row carrying the field the check exists to refuse. Declared so the refusal has
    something to fire on; there is deliberately no such type in the module."""

    total: int


def test_a_landing_figure_cannot_be_handed_in_already_counted():
    """Deleting this lets a counting function grow a parameter carrying a precomputed total.
    Filtering first and counting what is left is what makes the rule structural, and a total
    that arrives as an argument was counted somewhere with no filter in front of it."""

    def counts_what_it_was_told(one, rows, reader, now=None, *, total=0):
        return total

    assert operate_gaps(counter=counts_what_it_was_told) != ()
    assert operate_gaps() == ()
    assert "total" in NAMES_A_FIGURE_WOULD_ARRIVE_THROUGH


def test_a_panel_naming_a_row_that_does_not_resolve_is_reported():
    """Deleting this lets the register claim a module that is not there, which makes the
    attribution check silently skip that panel and the claim rest on nobody's word."""
    real = panel("halt")
    broken = Panel(
        key=real.key,
        row="brain.ops.halt.NoSuchType",
        counts=real.counts,
        attribution=real.attribution,
        shows=real.shows,
        never=real.never,
    )
    found = operate_gaps(panels=[*[one for one in PANELS if one.key != "halt"], broken])
    assert any("does not resolve" in one for one in found)


def a_panel(
    *,
    key: str = "runs",
    row: str = "brain.ops.jobs.JobRecord",
    counts: str = "runs executing right now",
    attribution: Attribution = Attribution.PER_PERSON,
    shows: str = "what is executing, for whom and since when",
    never: str = "a job's arguments, which are identifiers of records",
) -> Panel:
    """One panel with a single field replaced, for the refusals below.

    Explicit parameters rather than a keyword splat, because a splat into a frozen dataclass
    is untyped at the call site and these refusals are about the fields as much as the values.
    """
    return Panel(key=key, row=row, counts=counts, attribution=attribution, shows=shows, never=never)


def test_a_panel_that_does_not_say_what_its_figure_counts_is_refused():
    """**Written because a mutation of this guard survived the whole file.** Every panel this
    suite built was copied from a registered one, so the refusal could be deleted with nothing
    red.

    A number on the landing screen with no unit is a number the reader supplies a unit for,
    and the units available on this front page are documents, runs, halts and pounds. The
    reader who guesses wrong reads the corpus as a queue depth or a queue depth as a bill.

    The blank case is separate from the empty one: a panel registered through anything that
    trims input arrives with a space in it, and a bare falsiness check passes that.

    Delete this and a screen lends the front page a bare integer."""
    with pytest.raises(OperateError, match="says nothing about what its figure counts"):
        a_panel(counts="")

    with pytest.raises(OperateError, match="says nothing about what its figure counts"):
        a_panel(counts="   ")

    assert a_panel().counts


def test_a_panel_whose_row_is_not_a_dotted_path_is_refused():
    """**Written because a mutation of this guard survived the whole file.**

    The attribution claim in the register is only worth anything because it is checked against
    the row type rather than believed, and `operate_gaps` does that by importing the dotted
    path. A bare name imports nothing, `row_type` raises, and the diagnostic records the panel
    as unresolvable and moves on: the panel then carries whatever attribution somebody typed,
    with nothing at all holding it to the rows.

    Delete this and a register entry can claim a per-person figure over rows that belong to
    nobody, with the one check that would have caught it skipping that entry."""
    with pytest.raises(OperateError, match="not a dotted path"):
        a_panel(row="JobRecord")

    assert a_panel().row_type() is JobRecord


def test_a_panel_missing_either_sentence_about_what_it_shows_is_refused():
    """**Written because a mutation of this guard survived the whole file.**

    Two sentences, and the second is the one a screen gets built without: what it shows is
    written by whoever wanted the screen, and what it must never show is written by whoever
    thought about the reader who may not open it. A panel carrying only the first is a screen
    with a specification and no constraint, which is the state every leak on this front page
    would start from.

    Blank as well as empty, in both fields, because prose arriving through a form that trims
    nothing is whitespace rather than absent.

    Delete this and a panel ships with the constraint half of its register entry missing."""
    for missing in ("", "   "):
        with pytest.raises(OperateError, match="does not say both"):
            a_panel(shows=missing)
        with pytest.raises(OperateError, match="does not say both"):
            a_panel(never=missing)

    assert a_panel().shows and a_panel().never


def test_a_panel_naming_something_that_is_not_a_type_is_refused():
    """**Written because a mutation of this guard survived the whole file.** The existing test
    covers a dotted path that resolves to nothing; nothing covered one that resolves to
    something which is not a type.

    That is the quieter failure of the two. A constant, a function or a module answers
    `getattr` perfectly well, and `_field_names` then asks it for dataclass fields and pydantic
    fields, gets neither, and reports it as a row carrying no principal. So the register's
    attribution claim would be checked against an object that has no fields at all, and the
    check would come back with an opinion.

    Delete this and a panel can name a frozenset as the row its figure counts, and the
    diagnostic will tell you confidently that the figure cannot be narrowed."""
    with pytest.raises(OperateError, match="which is not a type"):
        a_panel(row="brain.ops.jobs.TERMINAL").row_type()

    assert panel("runs").row_type() is JobRecord


def test_a_screen_registered_as_a_panel_twice_is_reported():
    """**Written because a mutation of this guard survived the whole file.** The register is
    correct today, and the diagnostic's own duplicate check had nothing to fire on.

    Two panels for one screen is two figures for one screen assembled a step earlier than
    `overview` refuses it. The pair hands the reader the difference between them, which is a
    count of work belonging to people they cannot see, and it arrives as a copy-and-paste in a
    tuple of eleven near-identical entries rather than as anything anybody decided.

    Delete this and the register can grow a second entry for a screen, and the only thing
    standing behind it is `overview` refusing the two tiles at render time."""
    twice = operate_gaps(panels=[*PANELS, panel("runs")])

    assert any("registered as a panel 2 times" in one for one in twice)
    assert operate_gaps() == ()


def test_a_panel_for_a_screen_outside_this_group_is_reported():
    """**Written because a mutation of this guard survived the whole file.**

    The register and the screen registry are two lists that have to say the same thing, and
    this is the direction the completeness test does not cover: that one checks every operate
    and report screen has a panel, and this checks that every panel is one of those screens. A
    panel for a screen in another group, or for a key no screen has, lends the landing page a
    figure governed by a grant nobody registered against it.

    Delete this and the front page can carry a number from a screen whose own group decided
    something different about who may read it."""
    stray = operate_gaps(panels=[*PANELS, a_panel(key="not_a_registered_screen")])

    assert any("is not an operate or report screen" in one for one in stray)
    assert operate_gaps() == ()


# --------------------------------------------------------------- live runs (M27.2.2)
def test_a_run_is_visible_to_the_person_it_runs_for_without_any_grant():
    """Deleting this leaves the only person who knows what a job was for unable to see that
    it is running, which is the refusal `brain.ops.jobs.may_see` exists to avoid one state
    later, and it would make the screen useless to everybody but an administrator."""
    mine = a_job(principal_id=READER)

    assert may_watch(mine, holding(), NOW) is True


def test_a_run_belonging_to_somebody_else_needs_a_grant_whose_scope_matches_it():
    """Deleting this turns the live runs screen into a minute-by-minute list of what
    colleagues are asking for, readable by anybody who can open the page."""
    theirs = a_job(principal_id=COLLEAGUE, task="answer")

    assert may_watch(theirs, holding(), NOW) is False
    assert may_watch(theirs, holding(RUN_READ), NOW) is True

    elsewhere = Scope(clauses=(Clause(field="task", op=Op.EQ, value="ingest"),))
    assert may_watch(theirs, holding(RUN_READ, scope=elsewhere), NOW) is False


def test_the_visible_runs_are_identical_to_a_queue_the_invisible_ones_were_never_in():
    """Deleting this permits a placeholder, a gap in an ordering or a count that differs by
    one, and each of the three reconstructs exactly what was hidden. This is the only form of
    indistinguishable worth having."""
    mine = a_job(job_id="j1", principal_id=READER)
    theirs = a_job(job_id="j2", principal_id=COLLEAGUE)

    assert visible_runs([mine, theirs], holding(), NOW) == visible_runs([mine], holding(), NOW)


def test_a_run_row_carries_no_arguments():
    """Deleting this puts a job's arguments on a screen. They are identifiers of records, so
    a row reading client=447 tells the reader that client 447 exists and is being worked on,
    from a screen whose own purpose says the question rather than the answer."""
    record = a_job(principal_id=READER, args={"client_id": "447"})

    row = run_rows([record], holding(), NOW)[0]

    assert "447" not in repr(row)
    assert {one.name for one in fields(RunRow)} == {
        "job_id",
        "task",
        "principal_id",
        "state",
        "attempts",
        "since",
    }


def test_the_executing_states_have_spent_an_attempt_and_none_of_them_is_terminal():
    """Deleting this lets the live runs screen show finished work, or miss a job the moment
    it is cancelled and leave it running with nothing watching. Both are the same edit: a
    state added to one list in `brain.ops.jobs` and not to this one."""
    assert EXECUTING and not EXECUTING & TERMINAL
    assert not EXECUTING & STATES_WITHOUT_AN_ATTEMPT
    assert WAITING <= STATES_WITHOUT_AN_ATTEMPT
    assert not WAITING & EXECUTING


def test_the_live_runs_screen_shows_only_what_is_executing():
    """Deleting this puts settled work on a screen headed live, which is the figure an
    operator reads to decide whether the system is busy."""
    running = a_job(job_id="j1", state=JobState.RUNNING, attempts=1)
    queued = a_job(job_id="j2", state=JobState.QUEUED, attempts=0)
    done = a_job(job_id="j3", state=JobState.SUCCEEDED, attempts=1)

    rows = run_rows([running, queued, done], holding(), NOW)

    assert [one.job_id for one in rows] == ["j1"]


# ------------------------------------------------------ queue and automations (M27.2.6)
def test_the_queue_depth_counts_only_the_waiting_jobs_this_reader_may_see():
    """Deleting this makes a queue depth a count of other people's asking, published as a
    single number that nobody reviews because it looks like a system metric."""
    mine = a_job(job_id="j1", principal_id=READER, state=JobState.QUEUED, attempts=0)
    theirs = a_job(
        job_id="j2", principal_id=COLLEAGUE, state=JobState.QUEUED, attempts=0, task="ingest"
    )
    already_running = a_job(
        job_id="j3", principal_id=READER, state=JobState.RUNNING, attempts=1, task="export"
    )
    rows = [mine, theirs, already_running]

    narrow = queue_summary(rows, holding(), NOW)
    assert narrow.by_task == {"answer": 1}

    wide = queue_summary(rows, holding(QUEUE_READ), NOW)
    assert wide.by_task == {"answer": 1, "ingest": 1}


def test_a_retry_is_recognised_from_the_attempt_counter_and_not_from_a_state():
    """Deleting this makes a retried job indistinguishable from a first attempt on the
    screen, because scheduling is a timestamp rather than a state and both rows read QUEUED.
    An operator would then have no way to see a job going round."""
    first = a_job(job_id="j1", state=JobState.QUEUED, attempts=0)
    again = a_job(job_id="j2", state=JobState.QUEUED, attempts=2)

    assert queue_summary([first, again], holding(), NOW).retrying == 1


def test_a_grant_over_the_queue_does_not_reach_live_traffic():
    """Deleting this lets one job row be governed by whichever of two screens' capabilities
    was read first. The queue and the live runs screen are granted separately, and somebody
    given the queue would otherwise be watching colleagues work minute by minute."""
    theirs = a_job(principal_id=COLLEAGUE, state=JobState.RUNNING, attempts=1)

    assert may_watch(theirs, holding(QUEUE_READ), NOW, screen_key="runs") is False
    assert may_watch(theirs, holding(QUEUE_READ), NOW, screen_key="queue") is True
    assert may_watch(theirs, holding(RUN_READ), NOW, screen_key="runs") is True
    assert run_rows([theirs], holding(QUEUE_READ), NOW) == ()


def test_the_queue_screen_gives_the_same_basis_an_agents_schedule_tab_gets():
    """Deleting this lets the two surfaces drift. Both ask whether this reader may be shown
    scheduled work that is not theirs, both are behind the same screen, and two answers to
    one grant is the shape where the permissive one wins."""
    for reader in (holding(), holding(QUEUE_READ)):
        assert queue_basis(reader, NOW) == schedule_basis(reader, NOW)
        assert queue_basis(reader, NOW) == basis_over("queue", reader, NOW)


def test_the_oldest_waiting_job_is_the_oldest_one_this_reader_may_see():
    """Deleting this lets the stuck-queue indicator be computed over rows the reader cannot
    see, so a date appears on the screen that belongs to somebody else's work."""
    mine = a_job(
        job_id="j1", state=JobState.QUEUED, attempts=0, scheduled_at=NOW - timedelta(hours=1)
    )
    older = a_job(
        job_id="j2",
        principal_id=COLLEAGUE,
        state=JobState.QUEUED,
        attempts=0,
        scheduled_at=NOW - timedelta(days=3),
    )

    assert queue_summary([mine, older], holding(), NOW).oldest_at == NOW - timedelta(hours=1)


# ------------------------------------------------------- connector health (M27.2.4)
def test_a_source_out_of_reach_is_absent_from_the_health_table():
    """Deleting this names every source this install reads to whoever can open the page.
    Naming a source is a disclosure, and a health table is that disclosure once per row."""
    registry = [a_registered("laravel"), a_registered("xero")]

    rows = connector_rows(registry, ["laravel"])

    assert [one.name for one in rows] == ["laravel"]
    assert "xero" not in repr(rows)


def test_a_source_nothing_has_checked_reports_no_health_rather_than_a_healthy_one():
    """Deleting this makes a source nobody has reached look identical to one answering
    normally, which is the row an operator scans past when something is wrong."""
    registry = [a_registered("laravel")]
    checked = {
        "laravel": ConnectorHealth(connector="laravel", state=HealthState.DEGRADED, checked_at=NOW)
    }

    assert connector_rows(registry, ["laravel"]) == (
        ConnectorRow(name="laravel", lifecycle="enabled", health="", checked_at=None),
    )
    assert connector_rows(registry, ["laravel"], checked=checked) == (
        ConnectorRow(name="laravel", lifecycle="enabled", health="degraded", checked_at=NOW),
    )


def test_a_disabled_source_in_reach_is_still_shown():
    """Deleting this hides a source somebody switched off, which is the state an operator
    most often opens this screen to find. A guard tested only by what it refuses is satisfied
    by a table that refuses everything."""
    registry = [a_registered("laravel", ConnectorState.DISABLED)]

    assert reachable_connectors(registry, ["laravel"])[0].state is ConnectorState.DISABLED


# --------------------------------------------- knowledge coverage and staleness (M27.2.5)
def knowledge_reader(*departments: str, principal_id: str = READER) -> EntitlementSet:
    """A reader holding `read:knowledge` over one department, or over everything."""
    if not departments:
        return holding(KNOWLEDGE_READ, principal_id=principal_id)
    clauses = tuple(Clause(field="department", op=Op.EQ, value=one) for one in departments)
    return holding(KNOWLEDGE_READ, scope=Scope(clauses=clauses[:1]), principal_id=principal_id)


def test_a_reader_with_no_read_of_the_knowledge_plane_is_shown_no_coverage_at_all():
    """Deleting this turns a missing grant into an unfiltered coverage screen. An empty reach
    reads exactly like a caller who has no departments yet, which is why
    `brain.knowledge.search.reach_for` returns None rather than an unrestricted reach, and
    this is the surface where that would be undone."""
    item = an_item(item_id="k1", visibility=KnowledgeVisibility.of_department(MAINTENANCE))

    assert coverage([item], holding(), areas=[MAINTENANCE], now=NOW) == ()


def test_an_area_the_reader_does_not_reach_has_no_coverage_row():
    """Deleting this puts every department in the company on a coverage screen, with a number
    beside each. The list of areas is a listing of the org chart and is filtered like one."""
    here = an_item(item_id="k1", visibility=KnowledgeVisibility.of_department(MAINTENANCE))
    there = an_item(item_id="k2", visibility=KnowledgeVisibility.of_department(FINANCE))

    rows = coverage(
        [here, there], knowledge_reader(MAINTENANCE), areas=[MAINTENANCE, FINANCE], now=NOW
    )

    assert [one.area for one in rows] == [MAINTENANCE]
    assert FINANCE not in repr(rows)


def test_an_item_is_counted_against_its_own_area_and_no_other():
    """Deleting this lets every visible item be counted into every row, so an area with
    nothing behind it reads as covered and the gaps disappear from the screen whose whole
    purpose is to show them. A reader holding an unrestricted knowledge grant is the case
    that exposes it, because a single-department reader never has a second row to be wrong
    about."""
    here = an_item(item_id="k1", visibility=KnowledgeVisibility.of_department(MAINTENANCE))
    there = an_item(item_id="k2", visibility=KnowledgeVisibility.of_department(FINANCE))
    everywhere = holding(KNOWLEDGE_READ)

    rows = coverage([here, there], everywhere, areas=[MAINTENANCE, FINANCE], now=NOW)

    assert {one.area: one.items for one in rows} == {MAINTENANCE: 1, FINANCE: 1}


def test_an_area_the_reader_reaches_and_which_holds_nothing_is_a_row_at_zero():
    """Deleting this hides the gaps, and the gaps are what the screen is for. An area
    somebody may see and which holds nothing they may see is the roadmap entry; what must
    never appear beside it is the number that was there instead."""
    rows = coverage([], knowledge_reader(MAINTENANCE), areas=[MAINTENANCE], now=NOW)

    assert rows == (
        CoverageRow(area=MAINTENANCE, items=0, by_freshness=dict.fromkeys(COVERAGE_BANDS, 0)),
    )
    assert {one.name for one in fields(CoverageRow)} == {"area", "items", "by_freshness"}


def test_somebody_elses_draft_is_not_counted_as_coverage():
    """Deleting this counts unfinished notes as answers behind an area, and worse, counts
    somebody's draft in their colleague's name. The visibility is built from the item here
    rather than handed in as a verdict, because `Reach.admits` is the producer being tested."""
    theirs = an_item(
        item_id="k1",
        visibility=KnowledgeVisibility.of_department(MAINTENANCE),
        owner_id=COLLEAGUE,
        state=KnowledgeState.DRAFT,
    )
    published = an_item(item_id="k2", visibility=KnowledgeVisibility.of_department(MAINTENANCE))

    rows = coverage(
        [theirs, published], knowledge_reader(MAINTENANCE), areas=[MAINTENANCE], now=NOW
    )

    assert rows[0].items == 1


def test_an_unverified_item_is_unstated_rather_than_stale():
    """Deleting this reports a document nobody has ever checked as an old one, which sends
    somebody to re-verify a thing that was never verified. Never checked and checked long ago
    are different facts and the person deciding what to fix needs both."""
    never = an_item(item_id="k1", visibility=KnowledgeVisibility.of_department(MAINTENANCE))
    old = an_item(
        item_id="k2",
        visibility=KnowledgeVisibility.of_department(MAINTENANCE),
        verified_at=NOW - timedelta(days=30),
    )
    fresh = an_item(
        item_id="k3",
        visibility=KnowledgeVisibility.of_department(MAINTENANCE),
        verified_at=NOW - timedelta(minutes=1),
    )

    assert freshness_of(never, now=NOW) is Freshness.UNSTATED
    assert freshness_of(old, now=NOW) is Freshness.STALE
    assert freshness_of(fresh, now=NOW) is Freshness.LIVE

    rows = coverage(
        [never, old, fresh], knowledge_reader(MAINTENANCE), areas=[MAINTENANCE], now=NOW
    )
    assert rows[0].by_freshness == {
        Freshness.LIVE: 1,
        Freshness.AGEING: 0,
        Freshness.STALE: 1,
        Freshness.UNSTATED: 1,
    }


def test_every_freshness_band_is_a_key_even_at_zero():
    """Deleting this lets a caller write by_freshness.get(STALE, 0), which reads as though
    stale were optional. It is the band the screen exists for and it is missing on a good
    day, which is the day somebody writes the call."""
    rows = coverage([], knowledge_reader(MAINTENANCE), areas=[MAINTENANCE], now=NOW)

    assert set(rows[0].by_freshness) == set(COVERAGE_BANDS)
    assert set(COVERAGE_BANDS) == set(Freshness)


# ---------------------------------------------------------------- incidents (M27.2.7)
def test_an_incident_on_a_source_out_of_reach_is_absent_rather_than_redacted():
    """Deleting this shows a row for a source the reader cannot reach with the detail
    removed, and the row announces the source just as well as the detail would."""
    reachable = a_manifest(name="laravel")
    hidden = a_manifest(name="xero")

    found = incidents([(reachable, "degraded", NOW), (hidden, "down", NOW)], ["laravel"])

    assert [one.subject for one in found] == ["laravel"]
    assert "xero" not in repr(found)


def test_what_a_degradation_blocks_is_the_tools_its_own_manifest_declares():
    """Deleting this leaves the blocked list to be written by hand, which is a list that is
    right on the day it is written. A component carries no dependency edge, so the manifest
    is the only thing that actually knows what stops working."""
    manifest = a_manifest(name="laravel", tools=("laravel.read_client", "laravel.list_clients"))

    found = incidents([(manifest, "down", NOW)], ["laravel"])

    assert found[0].blocks == ("laravel.list_clients", "laravel.read_client")
    assert blocked_by(manifest, ["xero"]) == ()


def test_a_blocked_list_is_all_of_a_sources_tools_or_none_of_them():
    """Deleting this permits a per-tool filter, and a partial list is a per-tool disclosure of
    what exists on a source: the reader cannot tell a tool that is missing from one that was
    never there, and comparing two readers' screens recovers the difference."""
    manifest = a_manifest(
        name="laravel", tools=("laravel.read_one", "laravel.read_two", "laravel.read_three")
    )

    assert len(blocked_by(manifest, ["laravel"])) == 3
    assert blocked_by(manifest, []) == ()


# ------------------------------------------------------------ the stop button (M27.2.8)
def a_halt(scope: HaltScope, target: str = "") -> Halt:
    return Halt(
        scope=scope,
        target=target,
        declared_by="u_owner",
        at=NOW,
        reason="the source is returning other people's rows",
    )


def test_a_halt_on_everything_is_shown_to_a_reader_whose_scope_admits_no_target():
    """Deleting this leaves somebody reading a screen that says nothing is stopped while
    nothing runs, and sends them to raise an incident that already exists. A halt is neither
    denied nor absent: it says the system is paused, which discloses nothing about what this
    person could otherwise have read."""
    everything = stop_everything(declared_by="u_owner", at=NOW, reason="rolling back a release")
    state = HaltState(halts=(everything,))
    nobody = holding(HALT_ADMIN, scope=department_scope(FINANCE))

    assert len(stopped_for(state, nobody, NOW)) == 1


def test_a_halt_naming_a_department_out_of_reach_is_absent():
    """Deleting this lets one department admin read that another department has been stopped,
    and why, in a reason written by an administrator for an administrator that routinely names
    a customer or a defect."""
    theirs = a_halt(HaltScope.DEPARTMENT, FINANCE)
    state = HaltState(halts=(theirs,))
    reader = holding(
        HALT_ADMIN,
        scope=Scope(clauses=(Clause(field="target", op=Op.EQ, value=MAINTENANCE),)),
    )

    assert stopped_for(state, reader, NOW) == ()
    assert stopped_for(state, holding(HALT_ADMIN), NOW) == (theirs,)


def test_an_unreadable_halt_store_is_not_reported_as_nothing_being_stopped():
    """Deleting this makes the moment every request is being refused look identical to a
    quiet afternoon. Unknown means halted for admission, so a screen showing an empty list
    then contradicts every refusal being handed out."""
    unknown = HaltState.unknown()

    assert stopped_for(unknown, holding(HALT_ADMIN), NOW) == ()
    assert stop_is_unknown(unknown) is True
    assert stop_is_unknown(HaltState()) is False


def test_the_widest_halt_is_listed_first():
    """Deleting this leaves the order to insertion, so a reader reporting the first row
    reports whichever halt happened to be written first rather than the most general one,
    which is the one an administrator will recognise."""
    narrow = Halt(
        scope=HaltScope.CONNECTOR,
        target="laravel",
        declared_by="u_owner",
        at=NOW - timedelta(hours=2),
        reason="the source is returning other people's rows",
    )
    everything = stop_everything(declared_by="u_owner", at=NOW, reason="rolling back a release")

    found = stopped_for(HaltState(halts=(narrow, everything)), holding(HALT_ADMIN), NOW)

    assert [one.scope for one in found] == [HaltScope.EVERYTHING, HaltScope.CONNECTOR]


# ------------------------------------------------------- questions and gaps (M27.4.1)
def test_a_refusal_is_not_counted_as_a_gap():
    """Deleting this publishes refusals as holes in the knowledge base. Four of the five
    abstention reasons are facts about one person's reach, NOTHING_RETRIEVED deliberately
    covers the case where a record existed and was withheld, and counting them is both a
    wrong roadmap and a count of hidden things."""
    scope = SearchScope(covered=("laravel",))
    refused = nothing_retrieved(scope)

    assert gaps([refused]) == ()
    assert {AbstentionReason.NOTHING_CONNECTED} == GAP_REASONS
    assert AbstentionReason.NOTHING_RETRIEVED not in GAP_REASONS
    assert AbstentionReason.NOT_ENTITLED not in GAP_REASONS


def test_a_question_nothing_is_connected_to_is_counted_as_a_gap():
    """Deleting this leaves the gaps report empty for the one reason that is a fact about
    this company's setup, identical for everybody, and safe to say. The screen would then
    show nothing whatever was missing, which is a guard that refuses everything."""
    scope = SearchScope(covered=("laravel",))

    assert gaps([nothing_connected(scope), nothing_connected(scope)]) == (
        Gap(covered=("laravel",), occurrences=2),
    )


def test_a_gap_carries_the_scope_the_asker_was_shown_and_never_the_question():
    """Deleting this puts what people typed on a reporting screen. A transcript has its own
    grant, and the scope statement is the half the asker was already shown."""
    assert {one.name for one in fields(Gap)} == {"covered", "occurrences"}


def test_a_reader_without_the_questions_grant_sees_only_their_own():
    """Deleting this turns the questions screen into a list of what colleagues asked, which
    is the strongest form of the disclosure a count of it would only hint at."""
    mine = Turn(kind=TurnKind.QUESTION, at=NOW, principal_id=READER, text="where is the file")
    theirs = Turn(
        kind=TurnKind.QUESTION, at=NOW, principal_id=COLLEAGUE, text="what did we bill them"
    )

    assert visible_questions([mine, theirs], holding(), NOW) == (mine,)
    assert visible_questions([mine, theirs], holding(QUESTION_READ), NOW) == (mine, theirs)


def test_an_answer_is_not_a_question_on_the_questions_screen():
    """Deleting this puts answers on a screen registered for the existence plane. An answer
    is content, and the same grant would then reach two different planes."""
    asked = Turn(kind=TurnKind.QUESTION, at=NOW, principal_id=READER, text="where is the file")
    answered = Turn(kind=TurnKind.ANSWER, at=NOW, principal_id=READER, text="in the drive")

    assert visible_questions([asked, answered], holding(QUESTION_READ), NOW) == (asked,)


# ---------------------------------------------------------------- budgets (M27.4.3)
def test_the_ceiling_panel_carries_no_amount():
    """Deleting this lets the console add a figure back to a refusal that carries none by
    design. The sentence names the budget and who may raise it, and an amount beside it is
    somebody's spend on a screen the refusal was careful not to put it on."""
    effect = ceiling_effect(Allowance(row=a_budget_row(), spent_minor=99_000))

    assert {one.name for one in fields(effect)} == {"level", "ladder", "message", "raised_by"}
    assert "99" not in effect.message
    assert "100" not in effect.message


def test_the_ceiling_panel_says_what_happens_before_the_refusal():
    """Deleting this leaves the screen saying only that work stops, when in fact three
    degradations are tried first. An operator reading nothing about them changes a ceiling
    that was never the binding constraint."""
    effect = ceiling_effect(Allowance(row=a_budget_row(), spent_minor=0))

    same = Refusal(level=BudgetLevel.DEPARTMENT, period=BudgetPeriod.MONTH)
    assert effect.ladder == LADDER
    assert effect.message == same.message


def test_a_ceiling_on_a_subject_out_of_reach_is_absent():
    """Deleting this lets a reader count the rows and learn how many people or departments
    have budgets, which is a count of subjects they cannot see. A row stripped of its subject
    is still a row."""
    mine = a_budget_row(subject=MAINTENANCE)
    theirs = a_budget_row(subject=FINANCE)
    reader = holding(
        BUDGET_READ, scope=Scope(clauses=(Clause(field="subject", op=Op.EQ, value=MAINTENANCE),))
    )

    assert ceilings_in_reach([mine, theirs], reader, NOW) == (mine,)
    assert ceilings_in_reach([mine, theirs], holding(), NOW) == ()
    assert ceilings_in_reach([mine, theirs], holding(BUDGET_READ), NOW) == (mine, theirs)


# ------------------------------------------------------- quality and canaries (M27.4.4)
def a_finding(subject: str) -> CanaryFinding:
    return CanaryFinding(kind=Finding.LEAKED, asker="u_asker", question_id="q1", subject=subject)


def test_a_canary_finding_naming_a_field_out_of_reach_is_absent():
    """Deleting this turns the quality screen into a listing of the columns this system
    holds. The canaries module already refuses to carry the leaked value; the field name is
    the disclosure that is left, and it is the one a report is most likely to show."""
    reachable = a_finding("client.display_name")
    hidden = a_finding("client.contract_value")

    found = findings_in_reach([reachable, hidden], ["client.display_name"])

    assert found == (reachable,)
    assert "contract_value" not in repr(found)


def test_a_canary_finding_naming_a_field_in_reach_is_shown():
    """Deleting this leaves a filter satisfied by showing nothing, which is a quality screen
    that never reports a leak and passes every refusal test."""
    findings = [a_finding("client.display_name"), a_finding("client.status")]

    assert len(findings_in_reach(findings, ["client.display_name", "client.status"])) == 2


def test_a_subject_is_matched_whole_and_never_by_prefix():
    """Deleting this admits client.contract_value to somebody granted client.contract, and
    the failure looks like a helpful match rather than a leak."""
    assert findings_in_reach([a_finding("client.contract_value")], ["client.contract"]) == ()


# -------------------------------------------------------------- module properties
def test_nothing_in_this_module_intersects_two_entitlement_sets():
    """Deleting this lets a third implementation of the platform's central rule land on a
    console surface. The console's routes into it are `reads.audience` and
    `workspace_capabilities.run_reach`, and a copy here would be the one on a screen somebody
    trusts."""
    from pathlib import Path

    source = Path("src/brain/console/operate.py").read_text(encoding="utf-8")

    assert intersections_in(source) == ()


def test_the_model_matrix_names_both_halves_of_what_it_would_read():
    """Deleting this leaves the next person to look at the models screen concluding the
    machinery is absent and writing a third routing table. Both halves exist; what is missing
    is a renderer, and that is not this module's to write."""
    assert set(MATRIX_SURFACES) == {"brain.models.routing", "brain.models.health"}
    for module_path in MATRIX_SURFACES:
        __import__(module_path)


def test_the_usage_screen_says_why_it_cannot_show_tokens_by_department():
    """Deleting this leaves a column somebody assembles at read time from a second answer to
    which department a person is in. A figure that looks measured and is assembled is worse
    on a report than a column that is not there, and without this the reason is nowhere."""
    found = usage_gaps()

    assert found
    assert any("telemetry" in one and "department" in one for one in found)
