"""The agent-run write acceptance check: registered, passing on a real schema, and able to fail.

The database half builds PostgreSQL to head and runs the check as the install would: an installed
agent's real run asks, through a scripted model, to reply to a ticket of a made-up helpdesk, and the
check reads what the run left. It passes, and every table it writes holds afterwards what it held
before. Then it is run against the product broken where it proves, and each break fails it with its
own sentence.

Task ids: M13.7.6
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from brain.ops import acceptance_runtime_side_effects as module
from brain.ops.acceptance import FAILED, PASSED, Check, registered
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_sources import run_checks

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_runtime_side_effects"
NAME = "an_agents_run_holds_the_reply_it_asks_for_and_sends_nothing"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_check_is_registered_with_the_leaf_it_proves() -> None:
    """Delete this and the check can close a leaf it does not exercise, or name an id no task
    has."""
    assert {name: one.leaves for name, one in mine().items()} == {NAME: ("M13.7.6",)}
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for m in wbs["modules"] for one in m["leaf_ids"]}
    assert set(mine()[NAME].leaves) <= leaves


def test_the_runtime_side_effects_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them. Delete this and
    a check can drop out of the module with the page simply listing one fewer row."""
    assert checks_in(MODULE) == [NAME]


@pytest.mark.needs_db
def test_on_a_real_database_a_run_holds_its_reply_and_nothing_is_left_behind() -> None:
    """**The check as the install runs it, against PostgreSQL at head.** It passes, and every table
    holds afterwards what it held before. Delete this and an agent's run can stop holding what it
    asks for on a real schema with nothing on the install saying so."""
    with at_head("brain_acceptance_runtime_effects") as url:
        before = counts(url)
        outcome = run_checks(url, tuple(mine().values()))
        after = counts(url)
    assert outcome == {NAME: (PASSED, "")}
    assert after == before


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("registry", module.THE_APPLICATION_REGISTERED_NO_REPLY),
        ("hold", module.A_RUN_HELD_NOTHING),
        ("twice", module.A_RUN_HELD_ONE_REPLY_MORE_THAN_ONCE),
        ("action", module.A_RUN_HELD_THE_WRONG_ACTION),
        ("told", module.A_MODEL_WAS_TOLD_WHO_DECIDES),
        ("state", module.A_RUN_SENT_BEFORE_A_PERSON_DECIDED),
        ("worker", module.THE_APPROVED_REPLY_WAS_NOT_SENT_ONCE),
        ("standing", module.THE_AGENT_HAS_NO_STANDING),
    ],
)
def test_the_check_fails_where_the_run_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Eight breaks: a registry with no reply tool, a run that holds nothing, one that holds the
    same reply again each time it is asked, a preparer that changes the words, a sentence to the
    model that names the department, a worker that sends what is still pending, a worker with no
    way to send, and a standing read that finds no agent. Each fails the check with its own
    sentence. Delete this and the check can pass with the property gone."""
    import brain.gate.leash as leash
    import brain.gate.runtime as runtime
    import brain.gate.runtime_effects as effects
    import brain.ops.approved_runs as approved_runs
    import brain.tools.startup as startup
    from brain.connectors import freshdesk

    if broken == "registry":
        monkeypatch.setattr(startup, "register_proposed_writes", lambda registry, declared: ())
    elif broken == "hold":

        async def nothing(self: Any, suspension: Any, reach: Any, now: Any) -> None:
            del self, suspension, reach, now

        monkeypatch.setattr(effects.ConnectorSideEffects, "hold", nothing)
    elif broken == "twice":
        original = runtime.AgentRuntime._proposed

        async def forgetting(self: Any, proposal: Any, definition: Any, **kwargs: Any) -> str:
            kwargs["run"].held.clear()
            return await original(self, proposal, definition, **kwargs)

        monkeypatch.setattr(runtime.AgentRuntime, "_proposed", forgetting)
    elif broken == "action":
        made = freshdesk.TicketReplyProposal.action_for

        def changed(self: Any, arguments: Any, **kwargs: Any) -> Any:
            action = made(self, arguments, **kwargs)
            return action.model_copy(update={"args": {freshdesk.REPLY_FIELD: "something else"}})

        monkeypatch.setattr(freshdesk.TicketReplyProposal, "action_for", changed)
    elif broken == "told":
        monkeypatch.setattr(runtime, "HELD_FOR_A_PERSON", "Held for the people of acceptance_a.")
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
        original_resume = leash.resume

        def ignoring_state(suspension: Any, **kwargs: Any) -> Any:
            return original_resume(
                suspension.model_copy(update={"state": leash.ApprovalState.APPROVED}), **kwargs
            )

        monkeypatch.setattr(leash, "resume", ignoring_state)
    elif broken == "worker":
        monkeypatch.setattr(approved_runs.ConnectorWrites, "tools", lambda self: frozenset())
    else:

        async def none(self: Any, agent_id: str, now: Any) -> None:
            del self, agent_id, now

        monkeypatch.setattr(approved_runs.StoredStandings, "standing", none)
    with at_head(f"brain_acceptance_runtime_effects_{broken}") as url:
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, reason)
