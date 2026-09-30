"""The automation door's acceptance check: registered, passing on a real schema, and able to fail.

The check posts steps to the tool-call route mounted over its own transaction, so the database
half is the whole of it: PostgreSQL at head, run as the worker runs it, with the install's issuer
set as `tests/unit/test_acceptance.py` sets it. It passes and leaves every table it wrote as it
was. Then the product is broken where the check proves it, each the way it would break in
practice: the intersection replaced by the ceiling, an owner holding nothing read as unrestricted,
and the refusal for an undeclared tool made to differ from the one for a missing tool. Each is a
failed check with its own sentence.

Task ids: M32.6.2.2, M32.6.1.3
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from brain.ops import acceptance_checks_automation as automation
from brain.ops.acceptance import FAILED, PASSED, Check, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import INSTALL, at_head, checks_in, counts

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_automation"
NAME = "a_flow_step_gets_its_owner_s_rows_and_nothing_its_ceiling_adds"

#: The table an automation's registration is kept in, which `WRITTEN_BY_CHECKS` does not list.
WRITTEN_HERE = ("gate.automation_owner", "proj.record")


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_check_is_registered_with_the_leaves_it_proves() -> None:
    """One check naming the door's two leaves, each a leaf of the work breakdown. Delete this and
    the check can close a leaf it does not exercise, or name an id no task has."""
    assert {name: one.leaves for name, one in mine().items()} == {NAME: ("M32.6.2.2", "M32.6.1.3")}
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    assert {"M32.6.2.2", "M32.6.1.3"} <= leaves


def test_the_ceiling_declares_more_than_the_owners_hold() -> None:
    """`A_CEILING_IS_NEVER_A_GRANT`: the automation declares cost and margin and its owner holds
    neither, so a step answered with either is the flow reaching past its caller. Delete this and
    the two could be made equal, and the check would pass an intersection that is a union."""
    assert set(automation.OWNERS_HOLD) < set(automation.CEILING_DECLARES)
    assert {"read:price_list.cost", "read:price_list.margin"} <= set(automation.CEILING_DECLARES)
    assert {
        one.rsplit(".", 1)[1] for one in automation.OWNERS_HOLD if one.count(".") == 1
    } == automation.OWNERS_COLUMNS


def run_check(url: str, checks: Sequence[Check]) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url
    from brain.ops.acceptance_run import run_suite
    from brain.session import make_app_engine

    async def run() -> Any:
        engine = make_app_engine(normalise_database_url(url))
        try:
            return await run_suite(
                engine,
                checks,
                settings=settings_from({"BRAIN_DATABASE_URL": url, **INSTALL}),
                stream=sys.stderr,
            )
        finally:
            await engine.dispose()

    return {one.name: (one.outcome, one.reason) for one in asyncio.run(run())}


def written(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    return {
        one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0])  # noqa: S608
        for one in WRITTEN_HERE
    }


@pytest.fixture
def issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


@pytest.mark.needs_db
@pytest.mark.usefixtures("issuer")
def test_on_a_real_database_the_check_passes_and_leaves_nothing_behind() -> None:
    """**The check as the worker runs it, against PostgreSQL at head.** It passes, and every table
    it wrote to, the registrations and the records among them, holds what it held before. Delete
    this and a check that cannot pass on the real schema, or one that commits an automation to a
    client's install, reaches the owner's server first."""
    with at_head("brain_acceptance_automation") as url:
        before = (counts(url), written(url))
        outcomes = run_check(url, tuple(mine().values()))
        after = (counts(url), written(url))

    assert outcomes == {NAME: (PASSED, "")}
    assert after == before


@pytest.mark.needs_db
@pytest.mark.usefixtures("issuer")
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("ceiling", "a step was given a column only the automation's ceiling named"),
        ("empty", "an automation whose owner holds nothing was answered unlike a missing tool"),
        (
            "refusal",
            "an undeclared tool and a tool that does not exist were answered differently",
        ),
    ],
)
def test_the_check_fails_where_the_door_is_wrong(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Three breaks, each the way it happens: `flow_reach` answering with the automation's
    ceiling instead of the intersection; an owner holding nothing read as unrestricted, the empty
    set mistaken for no restriction; and a door that answers a tool it knows and the automation
    did not declare differently from one it does not know. Each fails with its own sentence.
    Delete this and the check is satisfied by a door that hands a flow whatever it declared."""
    from brain.core.entitlement import EntitlementSet
    from brain.ops import automation as flows
    from brain.ops import automation_piece

    real = flows.flow_reach
    if broken == "ceiling":

        def widened(caller: EntitlementSet, flow_ceiling: EntitlementSet) -> EntitlementSet:
            return flow_ceiling.model_copy(update={"principal_id": caller.principal_id})

        monkeypatch.setattr(automation_piece, "flow_reach", widened)
    elif broken == "empty":

        def unbounded(caller: EntitlementSet, flow_ceiling: EntitlementSet) -> EntitlementSet:
            if not caller.grants:
                return flow_ceiling.model_copy(update={"principal_id": caller.principal_id})
            return real(caller, flow_ceiling)

        monkeypatch.setattr(automation_piece, "flow_reach", unbounded)
    else:
        from brain import automation_routes

        # Read off the route's module, where the route looks it up; `getattr` because the name is
        # an import there rather than an export.
        real_call = getattr(automation_routes, "call_piece")  # noqa: B009

        async def told(step: Any, **kwargs: Any) -> Any:
            # A door that tells a flow author which names are tools it did not declare.
            if step.tool not in kwargs["declared_tools"] and kwargs["registry"].has(step.tool):
                raise PermissionError(step.tool)
            return await real_call(step, **kwargs)

        monkeypatch.setattr(automation_routes, "call_piece", told)
    check = mine()[NAME]
    with at_head("brain_acceptance_automation") as url:
        assert run_check(url, (check,)) == {NAME: (FAILED, reason)}


def test_the_automation_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them. Held here,
    beside the module's other tests, since 2026-09-30, so a package adding a check edits its own
    file and never a list every package appends to. Delete this and a check can drop out of the
    module with the page simply listing one fewer row."""
    assert checks_in("brain.ops.acceptance_checks_automation") == [
        "a_flow_step_gets_its_owner_s_rows_and_nothing_its_ceiling_adds",
    ]
