"""The approved-actions acceptance check: registered, passing on a real schema, and able to fail.

The database half builds PostgreSQL to head and runs the check as the worker would: an installed
agent's four held actions, one approved, one pending, one rejected and one lapsed, and the worker's
run made twice. It passes, and every table it writes holds afterwards what it held before. Then it
is run against the runner broken where it proves, and each break fails it with its own sentence.

Task ids: M13.7.6
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from brain.ops import acceptance_approved_runs as module
from brain.ops.acceptance import FAILED, PASSED, Check, registered
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_sources import run_checks

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_approved_runs"
NAME = "an_approved_action_runs_once_and_no_other_does"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_check_is_registered_with_the_leaf_it_proves() -> None:
    """Delete this and the check can close a leaf it does not exercise, or name an id no task
    has."""
    assert {name: one.leaves for name, one in mine().items()} == {NAME: ("M13.7.6",)}
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for m in wbs["modules"] for one in m["leaf_ids"]}
    assert set(mine()[NAME].leaves) <= leaves


def test_the_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them. Delete this
    and a check can drop out of the module with the page simply listing one fewer row."""
    assert checks_in(MODULE) == [NAME]


@pytest.mark.needs_db
def test_on_a_real_database_an_approved_action_runs_once_and_nothing_is_left_behind() -> None:
    """**The check as the worker runs it, against PostgreSQL at head.** It passes, and every table
    holds afterwards what it held before. Delete this and the worker's run of approved actions can
    break on a real schema with nothing on the install saying so."""
    with at_head("brain_acceptance_approved_runs") as url:
        before = counts(url)
        outcome = run_checks(url, tuple(mine().values()))
        after = counts(url)
    assert outcome == {NAME: (PASSED, "")}
    assert after == before


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("door", module.THE_APPROVED_ACTION_DID_NOT_RUN),
        ("once", module.THE_APPROVED_ACTION_RAN_AGAIN),
        ("state", module.AN_UNAPPROVED_ACTION_RAN),
        ("standing", module.THE_AGENT_HAS_NO_STANDING),
    ],
)
def test_the_check_fails_where_the_run_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Four breaks: the worker asking the door for no tool, a resume that runs every time it is
    asked, a resume that runs whatever the approval's state and window, and a standing read that
    finds no agent. Each fails the check with its own sentence. Delete this and the check can
    pass with the property gone."""
    import brain.gate.leash as leash
    import brain.ops.approved_runs as approved_runs

    if broken == "door":

        async def nothing(session: Any, *, now: Any, tools: Any, limit: int = 50) -> list[Any]:
            del session, now, tools, limit
            return []

        monkeypatch.setattr(approved_runs, "approved_to_run", nothing)
    elif broken == "once":

        def always(action: Any, *, execute: Any, ledger: Any, intent: Any) -> Any:
            del ledger, intent
            return execute(action)

        monkeypatch.setattr(leash, "run_real", always)
    elif broken == "state":

        async def every_row(session: Any, *, now: Any, tools: Any, limit: int = 50) -> list[Any]:
            from sqlalchemy import text

            del now, limit
            rows = await session.execute(
                text(
                    "SELECT id, principal_id FROM gate.suspension WHERE "
                    "(action -> 'tool' ->> 'name') = ANY(:tools)"
                ),
                {"tools": list(tools)},
            )
            return [approved_runs.Listed(*one) for one in rows.all()]

        monkeypatch.setattr(approved_runs, "approved_to_run", every_row)
        monkeypatch.setattr(leash.SuspendedAction, "is_expired", lambda self, now: False)
        original = leash.resume

        def ignoring_state(suspension: Any, **kwargs: Any) -> Any:
            return original(
                suspension.model_copy(update={"state": leash.ApprovalState.APPROVED}), **kwargs
            )

        monkeypatch.setattr(leash, "resume", ignoring_state)
    else:

        async def none(self: Any, agent_id: str, now: Any) -> None:
            del self, agent_id, now

        monkeypatch.setattr(approved_runs.StoredStandings, "standing", none)
    with at_head(f"brain_acceptance_approved_runs_{broken}") as url:
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, reason)
