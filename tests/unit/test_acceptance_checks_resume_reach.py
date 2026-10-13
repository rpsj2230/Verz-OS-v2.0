"""The resume point's install check: registered, passing on a real schema, and able to fail.

The database half holds an action for approval, revokes one approver's grant, has them press
approve and has a second approver approve it; it passes and leaves nothing. Then the product is
broken where the check proves it: an approval decided at a reach stored with the held action, and a
route that refuses every approver.

Task ids: M17.2.5
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, Check, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import INSTALL, at_head, checks_in, counts

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_resume_reach"
RESUME = "an_approval_is_decided_at_the_reach_held_when_it_is_pressed"
WRITTEN_HERE = ("gate.suspension",)


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_check_names_the_leaf_it_proves_and_it_is_a_leaf() -> None:
    """Delete this and the check can close a leaf it does not exercise, or name an id no task
    has."""
    assert {name: one.leaves for name, one in mine().items()} == {RESUME: ("M17.2.5",)}
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    assert "M17.2.5" in leaves


def test_the_resume_checks_are_listed_in_their_page_order() -> None:
    """Delete this and a check can drop out of the module with the page listing one fewer row."""
    assert checks_in(MODULE) == [RESUME]


def test_the_module_stands_inside_its_assigned_order_range() -> None:
    """Delete this and two modules can claim one place on the Install page."""
    from brain.ops import acceptance_checks_resume_reach as module

    assert 2000 <= module.CHECK_ORDER <= 2099


def run_checks(url: str, checks: Sequence[Check]) -> dict[str, tuple[str, str]]:
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
    """**The check as the worker runs it, against PostgreSQL at head.** It passes and every table
    it wrote holds what it held before. Delete this and a check that cannot pass on the real
    schema, or one that commits a held action to a client's install, reaches the owner's
    server."""
    with at_head("brain_acceptance_resume_reach") as url:
        before = (counts(url), written(url))
        outcomes = run_checks(url, tuple(mine().values()))
        after = (counts(url), written(url))

    assert outcomes == {RESUME: (PASSED, "")}
    assert after == before


@pytest.mark.needs_db
@pytest.mark.usefixtures("issuer")
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("stale_reach", "a person whose grant was revoked approved a held action"),
        ("refuses_all", None),
    ],
)
def test_the_check_fails_where_the_product_is_wrong(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str | None
) -> None:
    """Two breaks: a decision taken at the reach the approver held when the action was raised,
    which lets a person whose grant was taken away release it; and a route that answers every
    approver with the one refusal, which the second approver's approval exposes. Delete this and
    the check is satisfied by a route that never asks, or one that never allows."""
    from brain import approval_routes
    from brain.core.errors import Absent

    real = approval_routes.take_decision
    if broken == "stale_reach":

        async def stale(store: Any, sid: str, reach: Any, *args: Any, **kwargs: Any) -> Any:
            # The reach the person held before their grant was taken away, which is what a
            # decision taken at a reach stored beside the held action would read.
            from brain.core.entitlement import Capability, EntitlementSet, Grant
            from brain.core.scope import Scope
            from brain.ops.acceptance_checks_governance_2 import ACTION_CAPABILITY

            before = EntitlementSet(
                principal_id=reach.principal_id,
                grants=(
                    Grant(
                        capability=Capability(value=ACTION_CAPABILITY),
                        scope=Scope.department("acceptance_a"),
                    ),
                ),
            )
            return await real(store, sid, before, *args, **kwargs)

        monkeypatch.setattr(approval_routes, "take_decision", stale)
    else:

        async def never(*args: Any, **kwargs: Any) -> Any:
            raise Absent("no approval here", public_message="nothing here")

        monkeypatch.setattr(approval_routes, "take_decision", never)
    with at_head("brain_acceptance_resume_reach") as url:
        outcome = run_checks(url, tuple(mine().values()))[RESUME]

    assert outcome[0] == FAILED
    if reason is not None:
        assert outcome[1] == reason
