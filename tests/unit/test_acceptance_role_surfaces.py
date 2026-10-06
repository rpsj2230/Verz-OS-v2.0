"""The role surfaces' install acceptance checks: registered, passing on a real schema, able to fail.

The pure half holds the checks to the leaves they prove, to `docs/wbs.json`, and to the rule that a
reason is a literal sentence short enough to be stored whole. The database half builds PostgreSQL
to head once and runs both checks as the worker would: each passes with no reason, and every table
holds afterwards what it held before. Then each check is run against a product broken in one place
its sentence depends on, and fails with its own sentence.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M38.5.1
"""

from __future__ import annotations

import ast
import json
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from brain.ops import acceptance_checks_role_surfaces as role_checks
from brain.ops.acceptance import FAILED, PASSED, REASON_CHARS, Check, check_modules, registered
from tests.unit.test_acceptance import at_head, checks_in
from tests.unit.test_acceptance_lifecycle import every_count
from tests.unit.test_acceptance_workspace import run_checks

ROOT = Path(__file__).resolve().parents[2]

#: The module under test, by the name `check_modules` finds it under.
MODULE = "brain.ops.acceptance_checks_role_surfaces"

ALLOWANCE = "a_person_sees_their_own_spend_against_their_own_allowance"
HISTORY = "an_auditor_reads_a_grants_and_an_agents_leash_history"

#: Each check and the leaves it proves.
LEAVES = {ALLOWANCE: ("M33.3.1.5",), HISTORY: ("M33.4.1.2",)}


def mine() -> tuple[Check, ...]:
    return registered((MODULE,))


def by_name(name: str) -> Check:
    [one] = [one for one in mine() if one.name == name]
    return one


# ------------------------------------------------------------------------ without a server
def test_the_role_surface_checks_are_registered_with_the_leaves_they_prove() -> None:
    """The module declares its checks in the order the page lists them, each with its leaf, and
    the suite runs it. Delete this and a check can fall out of the module or out of the suite with
    the Install page simply listing one fewer row, or close a leaf its flow does not exercise."""
    assert [(one.name, one.leaves) for one in mine()] == list(LEAVES.items())
    assert checks_in(MODULE) == list(LEAVES)
    assert MODULE in check_modules()


def test_every_leaf_the_role_surface_checks_name_is_a_leaf_of_the_work_breakdown() -> None:
    """Held against `docs/wbs.json`, which is outside the module. WBS ids are positional, so an id
    that moved reads as a correct claim. Delete this and a result can be recorded against an id no
    task carries."""
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    for one in mine():
        assert set(one.leaves) <= leaves, one.name


def _reasons() -> list[str]:
    """Every reason the module raises a verdict with: the literal or the constant it names."""
    tree = ast.parse(Path(role_checks.__file__).read_text(encoding="utf-8"))
    said: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id not in ("CheckFailedError", "CheckNotRunError"):
            continue
        [argument] = node.args
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
            said.append(argument.value)
        elif isinstance(argument, ast.Name) and isinstance(
            getattr(role_checks, argument.id, None), str
        ):
            said.append(getattr(role_checks, argument.id))
        else:
            pytest.fail(ast.unparse(node))
    return said


def test_every_reason_the_role_surface_checks_give_is_a_literal_sentence_stored_whole() -> None:
    """`A_RESULT_NAMES_NO_DATA`: every reason is a string literal or a module constant holding one,
    never built from a value, and fits the column so the Install page shows the sentence the source
    wrote. Delete this and a reason can quote a row the check read, or be cut mid-word."""
    said = _reasons()
    assert len(set(said)) >= 11
    assert all(0 < len(one) <= REASON_CHARS for one in said)


def test_the_two_people_s_figures_cannot_be_mistaken_for_each_other() -> None:
    """The check tells a colleague's allowance and spend from the member's only because every
    figure differs, and the member's spend crosses each alert it sets. Delete this and a constant
    edited to equal its neighbour turns a mix-up into a pass."""
    from brain.ops.acceptance_checks_role_surfaces import (
        COLLEAGUE_DAY,
        COLLEAGUE_MONTH,
        COLLEAGUE_SPENT,
        MEMBER_DAY,
        MEMBER_MONTH,
        MEMBER_SPENT,
    )

    ceilings = {MEMBER_DAY[0], MEMBER_MONTH[0], COLLEAGUE_DAY, COLLEAGUE_MONTH}
    assert len(ceilings) == 4
    assert len({MEMBER_SPENT, COLLEAGUE_SPENT}) == 2
    for ceiling, fraction in (MEMBER_DAY, MEMBER_MONTH):
        assert ceiling * fraction <= MEMBER_SPENT < ceiling
    assert min(COLLEAGUE_DAY, COLLEAGUE_MONTH) > COLLEAGUE_SPENT


def test_the_member_grant_the_check_holds_is_the_one_a_sign_in_binding_writes() -> None:
    """The check's member holds `MEMBER_SURFACE` over their own things, and that is the row
    `member_grant` inserts. Delete this and the binding's grant can change while the check goes on
    proving the page for a reader nobody on an install is."""
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.sql import ClauseElement

    from brain.console.own_things import own_scope
    from brain.identity.sign_in_binding import MEMBER_SURFACE, member_grant

    compiled: ClauseElement = member_grant(uuid.uuid4(), "acceptance.x.a.member", granted_by="x")
    # `postgresql.dialect()` is untyped and mypy runs strict; making one performs no I/O.
    dialect = postgresql.dialect()  # type: ignore[no-untyped-call]
    params = compiled.compile(dialect=dialect).params
    assert params["capability"] == MEMBER_SURFACE.value
    assert params["scope"] == own_scope("acceptance.x.a.member").model_dump(mode="json")


# --------------------------------------------------------------------------- a real run
@pytest.fixture(scope="module")
def head() -> Iterator[str]:
    """One database at head for the file: every check rolls back, so the runs share it."""
    with at_head("brain_acceptance_role_surfaces") as url:
        yield url


@pytest.mark.needs_db
def test_on_a_real_database_both_role_surface_checks_pass_and_leave_nothing_behind(
    head: str,
) -> None:
    """**The checks as the worker runs them, against PostgreSQL at head.** Each passes with no
    reason, and every table, the spend, the budget versions, the grants, the agent and the ledger
    among them, holds afterwards exactly what it held before. Delete this and a check that cannot
    pass on the real schema, or one that commits an allowance or a grant to a client's install,
    reaches the owner's server first."""
    before = every_count(head)
    outcomes = run_checks(head, mine())
    after = every_count(head)

    assert outcomes == dict.fromkeys(LEAVES, (PASSED, ""))
    assert after == before


def _fails(head: str, name: str) -> tuple[str, str]:
    return run_checks(head, (by_name(name),))[name]


# --------------------------------------------------------- the allowance check can fail
def _budget_withheld(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("brain.mine_routes.MAX_OWN_RUNS", 0)


def _somebody_elses_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    """The ceiling read by level and period alone: the largest anybody holds is everybody's."""
    from sqlalchemy import select

    from brain.ops.budget_store import row_from
    from brain.tables.budget import BudgetVersionRow

    async def any_ceiling(session: Any, key: Any, at: Any) -> Any:
        level, _subject, period = key
        found = await session.execute(
            select(BudgetVersionRow)
            .where(BudgetVersionRow.level == level.value, BudgetVersionRow.period == period.value)
            .order_by(BudgetVersionRow.ceiling_minor.desc())
            .limit(1)
        )
        row = found.scalar_one_or_none()
        return None if row is None else row_from(row)

    monkeypatch.setattr("brain.mine_routes.in_force", any_ceiling)


def _spend_uncounted(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain.member_activity import personal_budget as kept

    def nothing_spent(rows: Any, actuals: Any, **kwargs: Any) -> Any:
        return kept(rows, (), **kwargs)

    monkeypatch.setattr("brain.mine_routes.personal_budget", nothing_spent)


def _everybody_counted(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both narrowings dropped: the load reads everybody's runs and the join counts them all."""
    from sqlalchemy import select

    from brain.tables.spend import SpendActualRow

    def everybodys_runs(principal_id: str, since: Any, limit: int) -> Any:
        return (
            select(SpendActualRow)
            .where(SpendActualRow.at >= since)
            .order_by(SpendActualRow.at.desc())
            .limit(limit)
        )

    def all_of_it(actuals: Any, dimension: Any) -> Any:
        return _Everyone(actuals)

    monkeypatch.setattr("brain.mine_routes.runs_by", everybodys_runs)
    monkeypatch.setattr("brain.console.own_things.spend_by", all_of_it)


class _Everyone(dict[str, int]):
    """A spend breakdown answering every person with everybody's total."""

    def __init__(self, actuals: Any) -> None:
        super().__init__()
        self.total: int = sum(one.cost_minor for one in actuals)

    def get(self, key: str, default: Any = None) -> int:
        return self.total


def _anybody_opens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("brain.mine_routes.permitted", lambda *args, **kwargs: True)


ALLOWANCE_BREAKS: dict[str, tuple[Callable[[pytest.MonkeyPatch], None], str]] = {
    "budget_withheld": (_budget_withheld, "NOT_SHOWN"),
    "somebody_elses_ceiling": (_somebody_elses_ceiling, "NOT_THEIR_ALLOWANCE"),
    "spend_uncounted": (_spend_uncounted, "NOT_COUNTED"),
    "everybody_counted": (_everybody_counted, "COUNTED_SOMEBODY_ELSES"),
    "anybody_opens": (_anybody_opens, "SHOWN_WITHOUT_THE_MEMBER_GRANT"),
}


@pytest.mark.needs_db
@pytest.mark.parametrize("broken", sorted(ALLOWANCE_BREAKS))
def test_the_allowance_check_fails_where_the_workspace_is_broken(
    head: str, monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    """One break per property, each failing the check with its own sentence: the budget card
    withheld, a colleague's ceiling read as the person's, the person's spend not counted,
    everybody's spend counted against them (both narrowings dropped, since either alone still
    holds), and the page opened without the member grant. Delete this and the check can pass with
    any of those properties gone from My workspace."""
    setup, reason = ALLOWANCE_BREAKS[broken]
    setup(monkeypatch)
    assert _fails(head, ALLOWANCE) == (FAILED, getattr(role_checks, reason))


@pytest.mark.needs_db
def test_a_single_dropped_narrowing_still_passes_the_allowance_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**The allowed case beside the breaks.** With the load reading everybody's runs but the join
    still narrowing to the person, the page is right and the check passes. Delete this and the
    `everybody_counted` break above can be read as one narrowing doing all the work, when the
    workspace keeps the person's figure in two places."""
    from sqlalchemy import select

    from brain.tables.spend import SpendActualRow

    def everybodys_runs(principal_id: str, since: Any, limit: int) -> Any:
        return select(SpendActualRow).where(SpendActualRow.at >= since).limit(limit)

    monkeypatch.setattr("brain.mine_routes.runs_by", everybodys_runs)
    assert _fails(head, ALLOWANCE) == (PASSED, "")


# ----------------------------------------------------------- the history check can fail
def _history_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("brain.audit_routes.permission_history", lambda *args, **kwargs: ())


def _without(action: str) -> Callable[[pytest.MonkeyPatch], None]:
    def setup(monkeypatch: pytest.MonkeyPatch) -> None:
        from brain.console.auditor import PERMISSION_ACTIONS

        fewer = frozenset(one for one in PERMISSION_ACTIONS if one.value != action)
        monkeypatch.setattr("brain.audit_routes.PERMISSION_ACTIONS", fewer)
        monkeypatch.setattr("brain.console.auditor.PERMISSION_ACTIONS", fewer)

    return setup


def _reach_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("brain.audit.view.AuditView._may_see", lambda self, entry: True)


def _anybody_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("brain.audit_routes.permitted", lambda *args, **kwargs: True)


HISTORY_BREAKS: dict[str, tuple[Callable[[pytest.MonkeyPatch], None], str]] = {
    "history_empty": (_history_empty, "GRANT_HISTORY_INCOMPLETE"),
    "revocation_left_out": (_without("revoke"), "GRANT_HISTORY_INCOMPLETE"),
    "leash_left_out": (_without("leash_change"), "LEASH_HISTORY_INCOMPLETE"),
    "reach_ignored": (_reach_ignored, "SHOWN_PAST_REACH"),
    "anybody_reads": (_anybody_reads, "SHOWN_WITHOUT_THE_SCREEN"),
}


@pytest.mark.needs_db
@pytest.mark.parametrize("broken", sorted(HISTORY_BREAKS))
def test_the_history_check_fails_where_the_activity_history_is_broken(
    head: str, monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    """One break per property, each failing the check with its own sentence: no history at all, a
    removal left out of a grant's history, a leash move left out of an agent's, a reader shown
    entries past their audit reach, and the history served without the Activity screen. Delete
    this and the check can pass with any of those properties gone from the auditor's history."""
    setup, reason = HISTORY_BREAKS[broken]
    setup(monkeypatch)
    assert _fails(head, HISTORY) == (FAILED, getattr(role_checks, reason))
