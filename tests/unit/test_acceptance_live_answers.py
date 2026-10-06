"""The install check that a live connector answer cites what it read and when (M11.8.8).

Over `brain.ops.acceptance_checks_live_answers`, against PostgreSQL at head where the suite has
one. The live half of the leaf is the owner's recorded check, which
`tests/unit/test_requirement_check_routes.py` holds the Connectors area to naming.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from brain.ops import acceptance_checks_live_answers as module
from brain.ops.acceptance import FAILED, PASSED, Check, registered
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_hubspot import run_checks

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_live_answers"
NAME = "a_live_connector_answer_cites_what_it_read_and_when"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_check_is_registered_with_the_leaf_it_proves() -> None:
    """Delete this and the check can close a leaf it does not exercise, or name an id no task
    has."""
    assert {name: one.leaves for name, one in mine().items()} == {NAME: ("M11.8.8",)}
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    assert {"M11.8.8"} <= {one for m in wbs["modules"] for one in m["leaf_ids"]}


def test_the_check_is_listed_in_its_page_order() -> None:
    """Delete this and the check can drop out of the module with the page listing one fewer
    row."""
    assert checks_in(MODULE) == [NAME]


def test_the_check_says_its_live_half_is_the_owner_s_recorded_check() -> None:
    """A check over a made-up helpdesk is not the live proof the leaf asks for, and its sentence
    has to say where that proof is, or the Install page reads a regression as the whole leaf.
    Delete this and the sentence can drop the clause."""
    assert "owner's recorded check" in mine()[NAME].sentence


@pytest.mark.needs_db
def test_on_a_real_database_a_live_answer_cites_what_it_read_and_nothing_is_left() -> None:
    """**The check as the worker runs it, against PostgreSQL at head.** It passes, and every table
    holds afterwards what it held before. Delete this and the path from a key kept by the console
    to a cited live answer can break on a real schema with nothing on the install saying so."""
    with at_head("brain_acceptance_live_answers") as url:
        before = counts(url)
        outcome = run_checks(url, tuple(mine().values()))
        after = counts(url)
    assert outcome == {NAME: (PASSED, "")}
    assert after == before


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("uncited", module.THE_ANSWER_DID_NOT_CITE_WHAT_WAS_READ),
        ("undated", module.THE_ANSWER_DID_NOT_CITE_WHAT_WAS_READ),
        ("unbound", module.AN_UNBOUND_AGENT_WAS_ANSWERED),
    ],
)
def test_the_check_fails_where_the_live_answer_path_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Three breaks in the product: an answer composed with no citations, one whose citations
    carry no read time, and a run computed at the caller's reach whatever the agent. Each fails
    the check with its own sentence. Delete this and the check can pass with the citation, its
    time or the agent's binding gone."""
    import dataclasses

    import brain.gate.compose as compose
    from brain.core.entitlement import EntitlementSet

    if broken == "uncited":
        monkeypatch.setattr(compose, "_citations_from", lambda payload: ())
    elif broken == "undated":
        cited = compose._citations_from

        def undated(payload: Any) -> Any:
            return tuple(dataclasses.replace(one, fetched_at="") for one in cited(payload))

        monkeypatch.setattr(compose, "_citations_from", undated)
    else:

        def caller_only(self: EntitlementSet, ceiling: EntitlementSet, now: Any = None) -> Any:
            del ceiling, now
            return self

        monkeypatch.setattr(EntitlementSet, "intersect", caller_only)
    with at_head(f"brain_acceptance_live_answers_{broken}") as url:
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, reason)
