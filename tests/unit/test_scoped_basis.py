"""A grant scoped to a department is no grant at all for a basis, across every caller of one.

`brain.console.workspace.basis_of` is the one rule, and `basis_for`, `basis_over` and every
function built on them ask it. Measured on 2026-09-15 before it existed: each of the six
consumers below handed a maintenance-scoped reader exactly what an unrestricted reader got,
finance included, so a narrowed grant and no grant were told apart by a department's rows.

Every test uses three readers per screen who differ only in that screen's capability and the
scope it is held in, and every refused output is compared with the no-grant reader's as bytes.
`brain.console.operate.figure_basis`, the one caller that opts in, is tested beside its panels
in `test_operate.py`.

Task ids: M27.2.6, M27.3.14, M27.3.15, M33.1.1.3, M39.1.3.1, M39.2.2.4, M39.6.1.4
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from brain.console.agent_automations import Automation, AutomationRun, history, schedule_basis
from brain.console.agent_output import basis_over
from brain.console.agent_tabs import SkillInvocation, skill_usage, usage_basis
from brain.console.global_surfaces import company_consumption
from brain.console.govern import Placed
from brain.console.govern_estate import (
    LibraryItem,
    departments_represented,
    learning_review,
    spans_departments,
)
from brain.console.operate import queue_basis
from brain.console.reach_view import TierThreeRouting
from brain.console.reads import Plane, plane_capability
from brain.console.screens import screen
from brain.console.workspace import Basis, basis_for, basis_of, headline
from brain.core.department import DEPARTMENT_FIELD
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.lane import Lane
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Clause, Op, Scope
from brain.gate.context import TrafficClass
from brain.knowledge.visibility import KnowledgeVisibility
from brain.ops.jobs import JobState
from brain.ops.spend import Actual

#: A fixed moment. Nothing here compares it with the wall clock; it only places rows in a window.
NOW = datetime(2027, 5, 4, 10, 0, tzinfo=UTC)
SINCE = NOW - timedelta(days=30)

READER = "p_reader"
COLLEAGUE = "p_colleague"
MAINTENANCE = "maintenance"
FINANCE = "finance"
AGENT = "support_triage"


def readers(key: str, *also: str) -> dict[str, EntitlementSet]:
    """An unrestricted, a maintenance-scoped and a no-grant reader of one screen.

    All three hold every console plane unrestricted and whatever `also` names, so the screen's
    own capability and the scope it is held in are the only things that differ.
    """
    held = screen(key).read.requires
    common = [Grant(capability=plane_capability(plane), scope=Scope()) for plane in Plane]
    common += [Grant(capability=Capability(value=one), scope=Scope()) for one in also]

    def reader(*grants: Grant) -> EntitlementSet:
        return EntitlementSet(principal_id=READER, grants=(*grants, *common))

    return {
        "unrestricted": reader(Grant(capability=held, scope=Scope())),
        "department": reader(Grant(capability=held, scope=Scope.department(MAINTENANCE))),
        "no grant": reader(),
    }


#: Every function that turns a screen's grant into a basis, and the screen it asks. Held to
#: the source by `test_every_basis_in_the_source_is_a_measured_caller_and_one_opts_in`.
CALLERS: tuple[tuple[str, str, Callable[[EntitlementSet, datetime], Basis]], ...] = (
    ("schedule_basis", "queue", schedule_basis),
    ("queue_basis", "queue", queue_basis),
    ("usage_basis", "usage", usage_basis),
    ("spans_departments", "scopes", spans_departments),
    ("basis_for", "budget", basis_for),
)


@pytest.mark.parametrize(
    ("key", "decide"), [one[1:] for one in CALLERS], ids=[c[0] for c in CALLERS]
)
def test_a_department_scoped_grant_gets_the_basis_a_reader_holding_nothing_gets(
    key: str, decide: Callable[[EntitlementSet, datetime], Basis]
) -> None:
    """Deleting this lets a grant naming one department be counted at everybody's scale on a
    screen whose rows nothing narrows by that department, which on 2026-09-15 was every one of
    these. The unrestricted reader is asserted too, because a rule refusing every grant alike
    would satisfy the refusal and take every figure away from every administrator."""
    found = {who: decide(reader, NOW) for who, reader in readers(key).items()}

    assert found["unrestricted"] is Basis.EVERYONE
    assert found["department"] is Basis.OWN
    assert found["department"] is found["no grant"]


def _actual(principal_id: str, department: str, cost_minor: int) -> Actual:
    return Actual(
        principal_id=principal_id,
        principal_kind=PrincipalKind.HUMAN,
        traffic=TrafficClass.HUMAN_INTERACTIVE,
        department=department,
        agent_id=AGENT,
        model="m",
        lane=next(iter(Lane)),
        cost_minor=cost_minor,
        at=NOW - timedelta(days=1),
        trace_id="t-cost-1",
    )


#: The reader's own spend is in maintenance and a colleague's in finance, at different amounts,
#: so a figure that included the colleague's cannot equal one that did not.
ACTUALS = (_actual(READER, MAINTENANCE, 100), _actual(COLLEAGUE, FINANCE, 700))

AUTOMATION = Automation(
    automation_id="auto_1",
    agent_id=AGENT,
    name="I file the weekly timesheets",
    runs_as=Principal(
        id=READER, kind=PrincipalKind.HUMAN, employment=Employment.STAFF, display_name=READER
    ),
    task="file_timesheets",
    next_run_at=NOW + timedelta(days=1),
)

RUNS = tuple(
    AutomationRun(automation_id="auto_1", at=NOW, state=JobState.SUCCEEDED, principal_id=one)
    for one in (READER, COLLEAGUE)
)

CALLS = tuple(
    SkillInvocation(agent_id=AGENT, skill_name="hosting-expiry", principal_id=one, at=NOW)
    for one in (READER, COLLEAGUE)
)

ITEMS = tuple(
    Placed(
        record=LibraryItem(
            item_id=f"doc_{one}",
            visibility=KnowledgeVisibility.of_department(one, owner_id="u_author"),
        ),
        where={"department": one},
    )
    for one in (MAINTENANCE, FINANCE)
)

ROUTED = {
    AGENT: tuple(
        TierThreeRouting(memory_id=f"m_{one}", department=one, back_to="agent:x/learning")
        for one in (MAINTENANCE, FINANCE)
    )
}

#: Everything a basis decides, each consumer at the basis its own caller gives this reader.
CONSUMERS: tuple[tuple[str, str, Callable[[EntitlementSet], object]], ...] = (
    (
        "history",
        "queue",
        lambda r: history(AUTOMATION, RUNS, r, basis=schedule_basis(r, NOW), now=NOW),
    ),
    (
        "skill_usage",
        "usage",
        lambda r: skill_usage(
            AGENT,
            CALLS,
            attached=["hosting-expiry"],
            caller_id=READER,
            basis=usage_basis(r, NOW),
            since=SINCE,
            until=NOW,
        ),
    ),
    (
        "departments_represented",
        "scopes",
        lambda r: departments_represented(ITEMS, r, basis=spans_departments(r, NOW), now=NOW),
    ),
    (
        "learning_review",
        "scopes",
        lambda r: learning_review(
            basis=spans_departments(r, NOW),
            visible={AGENT},
            tier_one={},
            tier_two={},
            tier_three=ROUTED,
        ),
    ),
    (
        "headline",
        "budget",
        lambda r: headline(
            AGENT,
            caller_id=READER,
            basis=basis_for(r, NOW),
            actuals=ACTUALS,
            since=SINCE,
            until=NOW,
        ),
    ),
    (
        "company_consumption",
        "budget",
        lambda r: company_consumption(ACTUALS, r, since=SINCE, until=NOW, now=NOW),
    ),
)


@pytest.mark.parametrize(
    ("key", "consume"), [one[1:] for one in CONSUMERS], ids=[one[0] for one in CONSUMERS]
)
def test_what_a_department_scoped_reader_is_shown_is_byte_identical_to_what_nobody_is_shown(
    key: str, consume: Callable[[EntitlementSet], object]
) -> None:
    """Deleting this lets a basis be right while what it decides is not: a consumer that asked
    the grant itself, or one handed the wrong caller's basis, would hand a maintenance-scoped
    reader finance's spend or a colleague's runs again. Measured on 2026-09-15, all six did.

    The unrestricted reader's output must differ from the no-grant reader's, or the fixture
    carries nothing of anybody else's and the byte comparison would pass for any rule. The
    library readers also hold the Library screen's own grant, so the grouping has rows."""
    shown = {who: consume(reader) for who, reader in readers(key, "read:document").items()}

    assert repr(shown["department"]).encode() == repr(shown["no grant"]).encode()
    assert shown["department"] == shown["no grant"]
    assert shown["unrestricted"] != shown["no grant"]


def test_a_caller_whose_rows_arrive_narrowed_to_the_department_still_counts_that_grant() -> None:
    """The positive sibling. Deleting it lets the rule be satisfied by refusing every scoped
    grant, which would take the usage and coverage figures off the landing screen from every
    department admin while every refusal above stays green. Asked through both entry points,
    because `basis_over` has to pass the caller's word on and not drop it."""
    usage = screen("usage").read
    three = readers("usage")

    assert basis_of(usage, three["department"], NOW, narrowed_to_department=True) is Basis.EVERYONE
    assert (
        basis_over("usage", three["department"], NOW, narrowed_to_department=True) is Basis.EVERYONE
    )
    assert basis_of(usage, three["no grant"], NOW, narrowed_to_department=True) is Basis.OWN
    assert basis_of(usage, three["department"], NOW) is Basis.OWN


def test_rows_narrowed_to_a_department_admit_a_department_clause_and_nothing_else() -> None:
    """Deleting this lets a caller's word that its rows are narrowed to a department admit a
    grant scoped to something else, a model or a department and a model, over rows that were
    narrowed by department and by nothing more. And it lets the scope stand in for the screen:
    an unrestricted capability with no console plane cannot open the screen at all."""
    usage = screen("usage").read
    planes = tuple(Grant(capability=plane_capability(plane), scope=Scope()) for plane in Plane)
    by_model = Clause(field="model", op=Op.EQ, value="m")
    by_place = Clause(field=DEPARTMENT_FIELD, op=Op.EQ, value=MAINTENANCE)

    for clauses in ((by_model,), (by_place, by_model)):
        scoped = Grant(capability=usage.requires, scope=Scope(clauses=clauses))
        reader = EntitlementSet(principal_id=READER, grants=(scoped, *planes))
        assert basis_of(usage, reader, NOW, narrowed_to_department=True) is Basis.OWN

    bare = EntitlementSet(
        principal_id=READER, grants=(Grant(capability=usage.requires, scope=Scope()),)
    )
    assert basis_of(usage, bare, NOW, narrowed_to_department=True) is Basis.OWN


def test_every_basis_in_the_source_is_a_measured_caller_and_one_opts_in() -> None:
    """Deleting this lets a new screen ask for a basis without being measured here, and lets a
    caller pass `narrowed_to_department` over rows nobody showed are narrowed, which is the
    false figure declared correct. Read from the source, as
    `tests/invariants/test_single_implementation.py` reads intersections, because a list of
    callers kept by hand is a list of the ones somebody remembered."""
    found: set[tuple[str, str, bool]] = set()
    for path in sorted(Path("src/brain").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for function in ast.walk(tree):
            if not isinstance(function, ast.FunctionDef):
                continue
            for call in ast.walk(function):
                if (
                    isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Name)
                    and call.func.id in {"basis_of", "basis_over"}
                ):
                    opts = any(one.arg == "narrowed_to_department" for one in call.keywords)
                    found.add((path.stem, function.name, opts))

    measured = {(module_of(decide), name, False) for name, _, decide in CALLERS}
    assert found == measured | {
        ("operate", "figure_basis", True),
        ("agent_output", "basis_over", True),
    }


def module_of(function: Callable[..., object]) -> str:
    return function.__module__.rpartition(".")[2]
