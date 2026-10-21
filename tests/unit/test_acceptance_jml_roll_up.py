"""The joiner, mover and leaver roll-ups: every clause names a leaf of the breakdown, a clause no
check names leaves the roll-up not run, and one that failed fails it.

Task ids: M26.2.7, M26.4.1
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from brain.ops import acceptance_roll_up
from brain.ops.acceptance import (
    FAILED,
    NOT_RUN,
    PASSED,
    CheckFailedError,
    CheckNotRunError,
    registered,
)
from brain.ops.acceptance_checks_jml_roll_up import (
    CLAUSES,
    MOVER_CLAUSES,
)
from brain.ops.acceptance_checks_jml_roll_up import (
    every_mover_leaf_is_shown_clause_by_clause_in_this_run as mover_roll_up,
)
from brain.ops.acceptance_checks_jml_roll_up import (
    joiner_mover_leaver_is_shown_clause_by_clause_in_this_run as jml_roll_up,
)
from brain.ops.acceptance_roll_up import checks_naming, is_roll_up

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_jml_roll_up"
MOVER = "every_mover_leaf_is_shown_clause_by_clause_in_this_run"
JML = "joiner_mover_leaver_is_shown_clause_by_clause_in_this_run"


def _leaves() -> set[str]:
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    return {leaf for m in wbs["modules"] for leaf in m["leaf_ids"]}


def test_each_roll_up_proves_the_leaf_it_names_and_is_never_evidence_itself() -> None:
    """Delete this and a roll-up can close a leaf it does not name, or be counted as the evidence
    for a requirement it only reads."""
    found = {one.name: one for one in registered((MODULE,))}
    assert {name: one.leaves for name, one in found.items()} == {
        MOVER: ("M26.2.7",),
        JML: ("M26.4.1",),
    }
    assert all(is_roll_up(one) for one in found.values())
    assert {leaf for one in found.values() for leaf in one.leaves} <= _leaves()


def test_every_clause_names_leaves_of_the_breakdown() -> None:
    """A clause naming a leaf outside the breakdown is one nothing can prove, and a mistyped id
    would read as a clause with no check. Delete this and either is found only by the install
    never closing the task. The one clause with no leaf is the one no leaf in the breakdown names,
    and is the only one allowed to be empty."""
    leaves = _leaves()
    for clauses in (MOVER_CLAUSES, CLAUSES):
        for clause, named in clauses.items():
            assert set(named) <= leaves, clause
    assert [clause for clause, named in CLAUSES.items() if not named] == [
        "an item a person can no longer reach leaves their workspace"
    ]
    assert all(MOVER_CLAUSES.values())


def test_the_mover_clauses_are_exactly_the_leaves_of_the_mover_group_above_the_test() -> None:
    """M26.2.7 covers every one of M26.2.1 to M26.2.6. Delete this and a leaf of the group can be
    left out of the roll-up, which then closes the test leaf on less than it says."""
    assert sorted(leaf for named in MOVER_CLAUSES.values() for leaf in named) == [
        f"M26.2.{n}" for n in range(1, 7)
    ]


def _run(roll_up: Any, earlier: dict[str, tuple[str, str]]) -> None:
    harness: Any = SimpleNamespace(earlier=earlier)
    asyncio.run(roll_up(harness))


@pytest.fixture
def every_clause_has_a_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """A world in which each leaf has one check named for it, so the roll-up's own decision is
    asked apart from which checks this branch happens to have."""

    def named(leaf: str, *, excluding: str) -> tuple[Any, ...]:
        return (SimpleNamespace(name=f"check_for_{leaf}"),)

    monkeypatch.setattr(acceptance_roll_up, "checks_naming", named)


def _all(outcome: str, clauses: Mapping[str, Sequence[str]]) -> dict[str, tuple[str, str]]:
    return {f"check_for_{leaf}": (outcome, "") for named in clauses.values() for leaf in named}


@pytest.mark.usefixtures("every_clause_has_a_check")
def test_a_run_in_which_every_clause_check_passed_passes_the_mover_roll_up() -> None:
    """The positive half. Delete this and a roll-up that refuses everything is satisfied by the
    tests below."""
    _run(mover_roll_up, _all(PASSED, MOVER_CLAUSES))


@pytest.mark.usefixtures("every_clause_has_a_check")
def test_a_clause_check_that_failed_fails_the_roll_up() -> None:
    """Delete this and the composite closes beside a red clause."""
    earlier = _all(PASSED, MOVER_CLAUSES)
    earlier["check_for_M26.2.3"] = (FAILED, "")
    with pytest.raises(CheckFailedError):
        _run(mover_roll_up, earlier)


@pytest.mark.usefixtures("every_clause_has_a_check")
def test_a_clause_check_that_was_not_run_leaves_the_roll_up_not_run() -> None:
    """Delete this and a roll-up passes in a run that never asked a question it reports."""
    with pytest.raises(CheckNotRunError):
        _run(mover_roll_up, _all(NOT_RUN, MOVER_CLAUSES))
    with pytest.raises(CheckNotRunError):
        _run(mover_roll_up, {})


@pytest.mark.usefixtures("every_clause_has_a_check")
def test_the_leaf_with_a_clause_no_leaf_names_is_never_passed() -> None:
    """With a check for every leaf that exists and all of them passing, M26.4.1 is still not run,
    and the sentence names the clause no leaf covers. Delete this and the roll-up closes the leaf
    on nine clauses of ten, which is the one failure a roll-up exists to prevent."""
    with pytest.raises(CheckNotRunError, match="no check names a clause of this leaf"):
        _run(jml_roll_up, _all(PASSED, CLAUSES))


def test_a_clause_check_that_failed_fails_the_joiner_mover_and_leaver_roll_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The failure outranks the missing clause: a red check is the product's fault and is said
    first. Delete this and a failing delegation check is hidden behind a clause nobody has built."""

    def named(leaf: str, *, excluding: str) -> tuple[Any, ...]:
        return (SimpleNamespace(name=f"check_for_{leaf}"),)

    monkeypatch.setattr(acceptance_roll_up, "checks_naming", named)
    earlier = _all(PASSED, CLAUSES)
    earlier["check_for_M26.2.3"] = (FAILED, "")
    with pytest.raises(CheckFailedError):
        _run(jml_roll_up, earlier)


def test_the_real_registry_leaves_a_clause_with_no_check_not_run_and_names_it() -> None:
    """Against the checks this tree registers, with every one of them passing, the roll-up either
    passes because each clause has a check or says which clause has none. Delete this and the
    roll-up can pass on the checks that exist while a clause has none."""
    own = JML
    uncovered = [
        clause
        for clause, named in CLAUSES.items()
        if not any(checks_naming(leaf, excluding=own) for leaf in named)
    ]
    earlier = {
        one.name: (PASSED, "")
        for named in CLAUSES.values()
        for leaf in named
        for one in checks_naming(leaf, excluding=own)
    }
    if uncovered:
        with pytest.raises(CheckNotRunError, match="no check names a clause of this leaf"):
            _run(jml_roll_up, earlier)
    else:  # pragma: no cover - every clause has a check once the missing ones are built
        _run(jml_roll_up, earlier)
