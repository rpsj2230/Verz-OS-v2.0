"""The modularity roll-up: every clause names checks that exist, and the roll-up reads them.

Task ids: M29.3.1
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from brain.ops.acceptance import (
    FAILED,
    NOT_RUN,
    PASSED,
    CheckFailedError,
    CheckNotRunError,
    registered,
)
from brain.ops.acceptance_checks_modularity_roll_up import (
    CLAUSES,
)
from brain.ops.acceptance_checks_modularity_roll_up import (
    modularity_is_shown_clause_by_clause_in_this_run as roll_up,
)
from brain.ops.acceptance_roll_up import checks_naming, is_roll_up

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_modularity_roll_up"
OWN = "modularity_is_shown_clause_by_clause_in_this_run"


def test_the_roll_up_proves_the_leaf_it_names_and_is_never_evidence_itself() -> None:
    """Delete this and the roll-up can close a leaf it does not name, or be counted as the evidence
    for a requirement it only reads."""
    [one] = registered((MODULE,))
    assert (one.name, one.leaves) == (OWN, ("M29.3.1",))
    assert is_roll_up(one)
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    assert set(one.leaves) <= {leaf for m in wbs["modules"] for leaf in m["leaf_ids"]}


def test_every_clause_names_a_leaf_a_check_proves() -> None:
    """**A clause with no check is a clause the roll-up can never show**, so the leaf could never
    close, and one naming a leaf outside the breakdown is one nothing can prove. Delete this and
    either is found by the owner's install not closing the task."""
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {leaf for m in wbs["modules"] for leaf in m["leaf_ids"]}
    assert len(CLAUSES) == 4
    for clause, named in CLAUSES.items():
        assert set(named) <= leaves, clause
        assert checks_naming(named[0], excluding=OWN), clause


def test_the_leaf_is_held_until_the_owner_answers_the_question_about_its_fourth_clause() -> None:
    """Delete this and a pass over three real clauses and one nearest clause closes the leaf before
    the owner has said whether the nearest clause is enough."""
    held = json.loads((ROOT / "docs" / "proof-sweep-holds.json").read_text(encoding="utf-8"))
    assert "needs-rupash 227" in held["held"]["M29.3.1"]


def _run(earlier: dict[str, tuple[str, str]]) -> None:
    harness: Any = SimpleNamespace(earlier=earlier)
    asyncio.run(roll_up(harness))


def _everything(outcome: str = PASSED) -> dict[str, tuple[str, str]]:
    return {
        one.name: (outcome, "")
        for leaves in CLAUSES.values()
        for leaf in leaves
        for one in checks_naming(leaf, excluding=OWN)
    }


def test_a_run_in_which_every_clause_check_passed_passes_the_roll_up() -> None:
    """The positive half. Delete this and a roll-up that refuses everything is satisfied by the
    tests below."""
    _run(_everything())


def test_a_clause_check_that_failed_fails_the_roll_up() -> None:
    """Delete this and the composite closes M29.3.1 beside a red clause."""
    earlier = _everything()
    name = checks_naming("M27.15.43", excluding=OWN)[0].name
    earlier[name] = (FAILED, "")
    with pytest.raises(CheckFailedError):
        _run(earlier)


def test_a_clause_check_that_was_not_run_leaves_the_roll_up_not_run() -> None:
    """Delete this and a roll-up passes in a run that never asked a question it reports."""
    earlier = _everything(NOT_RUN)
    with pytest.raises(CheckNotRunError):
        _run(earlier)
    with pytest.raises(CheckNotRunError):
        _run({})
