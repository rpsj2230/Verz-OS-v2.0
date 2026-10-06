"""The stop button's acceptance check: registered, passing on a real schema, and able to fail.

The database half builds PostgreSQL to head and runs the check as the worker would: a department
stopped by its own administrator and nothing wider, its member refused without the reason, a
resume that needs words, a stop on everything turning a question away, and an unreadable store
refusing. It passes, and every table holds afterwards what it held before, `ops.halt` and the
ledger included, so the check stops nobody on the install. Then it is run against the product
broken where it proves.

Task ids: M27.15.10, M27.15.15, M27.15.16, M27.15.2, M13.7.3
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, Check, registered
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_sources import run_checks

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_halt"
NAME = "a_stop_reaches_only_what_its_holder_may_stop"
LEAVES = ("M27.15.2", "M27.15.10", "M27.15.15", "M27.15.16", "M13.7.3")


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_check_is_registered_with_the_leaves_it_proves() -> None:
    """Delete this and the check can close a leaf it does not exercise, or name an id no task
    has."""
    assert {name: one.leaves for name, one in mine().items()} == {NAME: LEAVES}
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for m in wbs["modules"] for one in m["leaf_ids"]}
    assert set(LEAVES) <= leaves


def test_the_checks_are_listed_in_their_page_order() -> None:
    """Delete this and a check can drop out of the module with the page listing one fewer row."""
    assert checks_in(MODULE) == [NAME]


@pytest.mark.needs_db
def test_on_a_real_database_a_stop_reaches_only_what_it_may_and_leaves_nothing() -> None:
    """**The check as the worker runs it, against PostgreSQL at head.** It passes, and every table
    holds afterwards what it held before, the halts and the ledger included. Delete this and the
    stop button can break on a real schema with nothing on the install saying so, or the check
    can leave a department stopped on the owner's server."""
    from tests.fixtures.scratch_postgres import sql

    def halts(url: str) -> tuple[int, int]:
        (stops,) = sql(url, "SELECT count(*) FROM ops.halt")
        (entries,) = sql(url, "SELECT count(*) FROM obs.audit_entry WHERE action = 'halt'")
        return int(stops[0]), int(entries[0])

    with at_head("brain_acceptance_halt") as url:
        before = counts(url), halts(url)
        outcome = run_checks(url, tuple(mine().values()))
        after = counts(url), halts(url)
    assert outcome == {NAME: (PASSED, "")}
    assert after == before


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("anyone_stops", "a department administrator stopped beyond their department"),
        ("nothing_refused", "a department stop did not stop exactly that department"),
        ("resume_without_words", "a resume with no reason lifted a stop"),
        ("answers_anyway", "a question was answered while everything was stopped"),
        ("agent_not_asked", "an agent stop did not stop exactly that agent's work"),
    ],
)
def test_the_check_fails_where_the_stop_button_is_broken(
    broken: str, reason: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each property the check claims, broken in the product, fails it with its own reason. Delete
    this and the check can pass with the property gone."""
    import brain.api_routes as api_routes
    import brain.halt_routes as halt_routes
    import brain.ops.halt_store as halt_store

    if broken == "anyone_stops":

        def anybody(*args: Any, **kwargs: Any) -> bool:
            del args, kwargs
            return True

        monkeypatch.setattr(halt_routes, "may_act", anybody)
        monkeypatch.setattr(halt_store, "may_act", anybody)
    elif broken == "nothing_refused":
        monkeypatch.setattr(halt_store, "refusal_in", lambda state, work: "")
    elif broken == "resume_without_words":
        real = halt_store.resume

        async def wordless(*args: Any, reason: str, **kwargs: Any) -> Any:
            return await real(*args, reason=reason or "lifted with nothing written", **kwargs)

        monkeypatch.setattr(halt_routes, "resume", wordless)
    elif broken == "agent_not_asked":
        from brain.ops.halt import ENFORCED_AXES, HaltScope

        monkeypatch.setattr(halt_store, "ENFORCED_AXES", ENFORCED_AXES - {HaltScope.AGENT})
    else:
        monkeypatch.setattr(api_routes, "refusal_in", lambda state, work: "")
    with at_head(f"brain_acceptance_halt_{broken}") as url:
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, reason)
