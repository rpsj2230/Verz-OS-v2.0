"""The memory, learning and evaluation roll-ups, run after the checks they read, on PostgreSQL.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M16.3.2, M16.7.3, M16.7.7, M16.7.8, M16.7.9, M16.7.11, M16.7.14, M28.5.1, M28.5.2
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator, Sequence

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, registered
from brain.ops.acceptance_roll_up import ROLL_UP_LEAVES, is_roll_up
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MEMORY = "brain.ops.acceptance_checks_memory_roll_up"
EVALUATION = "brain.ops.acceptance_checks_evaluation_roll_up"

TIER_ONE = "tier_one_is_one_persons_own_in_this_run"
OFFERED = "a_learned_rule_waits_for_approval_in_this_run"
PROMOTED = "a_promotion_and_a_gated_decision_record_who_agreed_in_this_run"
MEMORY_AND_CONTEXT = "memory_and_context_are_shown_clause_by_clause_in_this_run"
LEARNING = "the_learning_loop_is_shown_clause_by_clause_in_this_run"
EVERY_LEARNING = "every_learning_requirement_is_demonstrated_in_this_run"
EVERY_MEMORY = "every_memory_requirement_is_demonstrated_in_this_run"
REACH = "per_person_reach_is_shown_clause_by_clause_in_this_run"
GATE = "the_evaluation_gate_is_shown_clause_by_clause_in_this_run"

#: What the memory roll-ups read, in the order the suite runs them.
READ = (
    "brain.ops.acceptance_checks_memory",
    "brain.ops.acceptance_checks_signals",
    "brain.ops.acceptance_checks_signal_log",
    "brain.ops.acceptance_checks_learning",
    "brain.ops.acceptance_checks_promotion",
    "brain.ops.acceptance_checks_er_cascade",
    "brain.ops.acceptance_checks_context_signals",
)


def test_each_roll_up_names_the_leaf_it_rolls_up_and_none_is_evidence_for_another() -> None:
    """Nine roll-ups and one leaf each, and the six proof leaves are the ones no other check may
    count a roll-up as evidence for. Delete this and a roll-up can lose its leaf with the page
    showing the same row, or vouch for another."""
    assert [(one.name, one.leaves) for one in registered((MEMORY,))] == [
        (TIER_ONE, ("M16.3.2",)),
        (OFFERED, ("M16.7.3",)),
        (PROMOTED, ("M16.7.14",)),
        (MEMORY_AND_CONTEXT, ("M16.7.7",)),
        (LEARNING, ("M16.7.8",)),
        (EVERY_LEARNING, ("M16.7.9",)),
        (EVERY_MEMORY, ("M16.7.11",)),
    ]
    assert [(one.name, one.leaves) for one in registered((EVALUATION,))] == [
        (REACH, ("M28.5.1",)),
        (GATE, ("M28.5.2",)),
    ]
    assert checks_in(MEMORY) and checks_in(EVALUATION)
    from brain.ops import acceptance_checks_evaluation_roll_up as evaluation
    from brain.ops import acceptance_checks_memory_roll_up as memory

    assert 870 <= memory.CHECK_ORDER < evaluation.CHECK_ORDER <= 889
    proofs = [one for module in (MEMORY, EVALUATION) for one in registered((module,))]
    assert {one.name for one in proofs if is_roll_up(one)} == {
        MEMORY_AND_CONTEXT,
        LEARNING,
        EVERY_LEARNING,
        EVERY_MEMORY,
        REACH,
        GATE,
    }
    assert {"M16.7.7", "M16.7.8", "M16.7.9", "M16.7.11", "M28.5.1", "M28.5.2"} <= ROLL_UP_LEAVES


def test_every_clause_a_roll_up_names_is_a_leaf_of_the_breakdown() -> None:
    """A mistyped clause leaf would read as a clause no check names, and say so for ever. Delete
    this and a roll-up can stay not run on a typing mistake."""
    import json
    from pathlib import Path

    from brain.ops import acceptance_checks_evaluation_roll_up as evaluation
    from brain.ops import acceptance_checks_memory_roll_up as memory

    wbs = json.loads(
        (Path(__file__).resolve().parents[2] / "docs" / "wbs.json").read_text(encoding="utf-8")
    )
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    clauses = (
        *memory.TIER_ONE.values(),
        *memory.OFFERED.values(),
        *memory.PROMOTED.values(),
        *memory.MEMORY_AND_CONTEXT.values(),
        *memory.LEARNING_LOOP.values(),
        *evaluation.PER_PERSON_REACH.values(),
        *evaluation.THE_GATE.values(),
    )
    named = {leaf for clause in clauses for leaf in clause}
    assert named <= leaves


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_memory_roll_up") as url:
        yield url


def run_modules(url: str, modules: Sequence[str]) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url

    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings_from({"BRAIN_DATABASE_URL": url}),
            commit="abc1234",
            checks=list(registered(tuple(modules))),
            force=True,
        )
    )
    return {one.name: (one.outcome, one.reason) for one in results}


@pytest.mark.needs_db
def test_the_roll_ups_pass_where_every_clause_is_shown_and_say_what_is_missing_where_not(
    install: str,
) -> None:
    """**The roll-ups as the worker runs them**, after the checks they read. Tier one and the
    learned rule's approval are shown by checks that ran in the same run and pass; the promotion
    roll-up, memory and context, the learning loop and the two register roll-ups are not run, and
    each names what nothing proves yet; the evaluation roll-ups likewise. Nothing is left behind.
    Delete this and a roll-up passes on clauses that no check shows, or one that cannot see the
    run's earlier results reaches the owner's server."""
    before = counts(install)
    seen = run_modules(install, (*READ, MEMORY, EVALUATION))
    assert seen[TIER_ONE] == (PASSED, "")
    assert seen[OFFERED] == (PASSED, "")
    for name, missing in (
        (PROMOTED, "tier-three item"),
        (MEMORY_AND_CONTEXT, "M16.4.3"),
        (LEARNING, "M17.6.7"),
        (GATE, "M28.1.4"),
    ):
        outcome, reason = seen[name]
        assert outcome == NOT_RUN, name
        assert missing in reason, (name, reason)
    assert seen[EVERY_LEARNING][0] == NOT_RUN
    assert seen[EVERY_MEMORY][0] == NOT_RUN
    assert FAILED not in {outcome for outcome, _ in seen.values()}
    assert counts(install) == before


@pytest.mark.needs_db
def test_a_failed_clause_check_fails_the_tier_one_roll_up(install: str) -> None:
    """A mark that does change a later answer, so the check naming it fails and the roll-up that
    reads it fails with it. Delete this and tier one closes beside a mark that reorders answers."""
    import dataclasses

    from brain.db import normalise_database_url
    from brain.ops.acceptance import CheckFailedError

    async def failing(h: object) -> None:
        raise CheckFailedError("a mark changed what a later answer retrieved")

    checks = [
        dataclasses.replace(one, run=failing)
        if one.name == "a_mark_is_counted_and_changes_nothing"
        else one
        for one in registered((*READ, MEMORY))
    ]
    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(install),
            settings=settings_from({"BRAIN_DATABASE_URL": install}),
            commit="abc1234",
            checks=checks,
            force=True,
        )
    )
    seen = {one.name: one.outcome for one in results}
    assert seen["a_mark_is_counted_and_changes_nothing"] == FAILED
    assert seen[TIER_ONE] == FAILED
