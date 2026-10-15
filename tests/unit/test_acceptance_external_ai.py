"""The outside AI service acceptance check: registered, passing on a real schema, and able to fail.

The database half builds PostgreSQL to head and runs the check as the worker would: a stand-in
service declared as a screen would declare it, the switch pressed both ways through the Features
route, three agents and two members, and a direct call. It passes, and every table it writes holds
afterwards what it held before. Then it is run against the product broken where it proves.

Task ids: M12.3.7
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from brain.core.entitlement import EntitlementSet
from brain.core.envelope import TypedResult
from brain.ops.acceptance import FAILED, PASSED, Check, registered
from brain.tools.external_ai import OutsideAiResult, ServiceAsked
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_sources import run_checks

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_external_ai"
NAME = "an_outside_service_is_offered_only_to_agents_that_name_it"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_check_is_registered_with_the_leaf_it_proves() -> None:
    """Delete this and the check can close a leaf it does not exercise, or name an id no task
    has."""
    assert {name: one.leaves for name, one in mine().items()} == {NAME: ("M12.3.7",)}
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for m in wbs["modules"] for one in m["leaf_ids"]}
    assert set(mine()[NAME].leaves) <= leaves


def test_the_checks_are_listed_in_their_page_order() -> None:
    """Delete this and a check can drop out of the module with the page listing one fewer row."""
    assert checks_in(MODULE) == [NAME]


@pytest.mark.needs_db
def test_on_a_real_database_a_declared_service_is_registered_and_offered_to_nobody_unnamed() -> (
    None
):
    """**The check as the worker runs it, against PostgreSQL at head.** It passes, and every table
    holds afterwards what it held before, the declaration row, the switch row and the agents
    included. Delete this and registering a service can break on a real schema with nothing on the
    install saying so, or a check can leave a declared service or a switched feature behind on the
    owner's server."""
    from tests.fixtures.scratch_postgres import sql

    def kept(url: str) -> dict[str, int]:
        # The names are this module's constants, never input.
        return {
            one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0])  # noqa: S608
            for one in ("ops.setting", "agent.agent")
        }

    with at_head("brain_acceptance_external_ai") as url:
        before = counts(url), kept(url)
        outcome = run_checks(url, tuple(mine().values()))
        after = counts(url), kept(url)
    assert outcome == {NAME: (PASSED, "")}
    assert after == before


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        (
            "the_switch_is_ignored",
            "a service was registered while outside services were switched off",
        ),
        (
            "a_service_counts_as_a_read",
            "a registered service did not count as sending something out",
        ),
        (
            "the_ceiling_is_ignored",
            "a service was offered through an agent whose ceiling does not name it",
        ),
        ("a_service_is_called", "a registered service was called instead of refused"),
    ],
)
def test_the_check_fails_where_registering_a_service_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Four breaks: the switch not being asked, a service counted as a read, the agent's ceiling
    not consulted by the catalogue, and a handler that answers a call. Each fails the check with
    its own sentence. Delete this and the check can pass with the property gone."""
    import brain.gate.catalogue as catalogue
    import brain.ops.external_ai_store as store
    import brain.tools.external_ai as external

    if broken == "the_switch_is_ignored":

        async def always(sessions: Any) -> bool:
            del sessions
            return True

        monkeypatch.setattr(store, "services_are_on", always)
    elif broken == "a_service_counts_as_a_read":
        from brain.core.envelope import SideEffect

        monkeypatch.setattr(external, "SERVICE_SIDE_EFFECT", SideEffect.NONE)
    elif broken == "the_ceiling_is_ignored":
        monkeypatch.setattr(catalogue, "within_ceiling", lambda tool, ceiling: True)
    else:

        async def answers(
            request: ServiceAsked, *, entitlement: EntitlementSet, now: datetime | None = None
        ) -> TypedResult[OutsideAiResult]:
            del request, entitlement, now
            return TypedResult[OutsideAiResult](records=(), source="stand-in")

        monkeypatch.setattr(external, "never_called_directly", answers)
    with at_head(f"brain_acceptance_external_ai_{broken}") as url:
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, reason)
