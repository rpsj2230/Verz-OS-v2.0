"""The learning install acceptance checks: registered, passing on PostgreSQL, and able to fail.

The pure half holds the four checks to the leaves they prove and to the work breakdown. The
database half builds PostgreSQL to head once for the module and runs the checks as the worker would:
each passes, and every table they write to holds, row for row, what it held before. Then the
property each check proves is broken, one at a time, by replacing the product function the check
relies on where the product looks it up, and the check fails with its own sentence.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M16.3.5, M16.3.6, M16.4.2, M16.6.8, M27.7.21, M33.3.1.4
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Iterator, Sequence
from typing import Any

import pytest

from brain.ops.acceptance import CHECK_MODULES, FAILED, PASSED, Check, registered
from tests.unit.test_acceptance import ROOT, WRITTEN_BY_CHECKS, at_head

MODULE = "brain.ops.acceptance_checks_learning"

#: Each learning check and the leaves it proves.
LEAVES = {
    "a_person_edits_and_forgets_their_own_memory": ("M16.4.2", "M33.3.1.4"),
    "every_learned_change_is_held_at_the_tier_its_reach_needs": ("M16.3.5", "M16.3.6"),
    "a_conversation_learning_is_reviewed_and_undone": ("M27.7.21",),
    "learning_figures_are_set_in_bounds_and_move_no_tier": ("M16.6.8",),
}

#: Every table the learning checks write to, which must hold afterwards exactly what it held before.
WRITTEN_BY_LEARNING_CHECKS = (
    "gate.department",
    "gate.scope",
    "auth.principal",
    "gate.capability_grant",
    "gate.grants_version",
    "gate.policy_epoch",
    "obs.audit_entry",
    "ops.setting",
    "know.item",
    "know.chunk",
    "mem.persistent",
    "mem.adaptive",
    "mem.learning",
    "mem.correction",
)


def mine() -> tuple[Check, ...]:
    return registered((MODULE,))


def one(name: str) -> Check:
    [found] = [check for check in mine() if check.name == name]
    return found


# ------------------------------------------------------------------------ without a server
def test_the_learning_checks_prove_the_learning_leaves_and_nothing_else() -> None:
    """Each check names the leaves it was scoped to, and the module is in the suite. Delete this
    and a check can close a leaf it does not exercise, or fall out of the run."""
    assert {check.name: check.leaves for check in mine()} == LEAVES
    assert MODULE in CHECK_MODULES


def test_every_leaf_the_learning_checks_name_is_a_leaf_of_the_work_breakdown() -> None:
    """WBS ids are positional, so an id that moved reads as a correct claim. Delete this and a
    result can close the wrong leaf on the owner's tracker."""
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {leaf for module in wbs["modules"] for leaf in module["leaf_ids"]}
    assert {leaf for check in mine() for leaf in check.leaves} <= leaves


def test_every_table_the_learning_checks_write_is_one_the_suite_measures() -> None:
    """Delete this and a table these checks write can be left out of the suite's count, so a
    check that committed a correction to a client's install would pass the suite."""
    assert set(WRITTEN_BY_LEARNING_CHECKS) <= set(WRITTEN_BY_CHECKS)


# --------------------------------------------------------------------------- a real run
def run_checks(url: str, checks: Sequence[Check]) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url
    from brain.ops.acceptance_run import run_suite
    from brain.session import make_app_engine
    from brain.settings import settings_from

    async def run() -> Any:
        engine = make_app_engine(normalise_database_url(url))
        try:
            return await run_suite(
                engine,
                checks,
                settings=settings_from({"BRAIN_DATABASE_URL": url}),
                stream=sys.stderr,
            )
        finally:
            await engine.dispose()

    return {result.name: (result.outcome, result.reason) for result in asyncio.run(run())}


@pytest.fixture(scope="module")
def database() -> Iterator[str]:
    """One database at head for the module: every check rolls back, so they can share it."""
    with at_head("brain_acceptance_learning") as url:
        yield url


def contents(url: str) -> dict[str, tuple[int, str]]:
    """Every row of every table the checks write to, as a count and a digest of the rows."""
    from tests.fixtures.scratch_postgres import sql

    held: dict[str, tuple[int, str]] = {}
    for table in WRITTEN_BY_LEARNING_CHECKS:
        # The names are this module's constants, never input.
        [(count, digest)] = sql(
            url,
            f"SELECT count(*), coalesce(md5(string_agg(t::text, ',' ORDER BY t::text)), '')"  # noqa: S608
            f" FROM {table} t",
        )
        held[table] = (int(count), str(digest))
    return held


@pytest.mark.needs_db
def test_on_a_real_database_every_learning_check_passes_and_leaves_nothing_behind(
    database: str,
) -> None:
    """**The four checks as the worker runs them, against PostgreSQL at head.** Each passes with
    no reason, and every table any of them wrote to holds row for row what it held before. Delete
    this and a check that cannot pass on the real schema, or one that commits a correction to a
    client's install, reaches the owner's server first."""
    before = contents(database)
    outcomes = run_checks(database, mine())
    after = contents(database)

    assert outcomes == dict.fromkeys(LEAVES, (PASSED, ""))
    assert after == before


# ------------------------------------------------------------- each check can fail
def refused(database: str, name: str) -> tuple[str, str]:
    return run_checks(database, (one(name),))[name]


@pytest.mark.needs_db
def test_the_edit_check_fails_when_an_edit_can_be_made_to_somebody_elses_memory(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ownership is the whole of a personal control. Delete this and the check can pass on an
    install where anybody edits a memory by its id."""
    from brain import mine_routes
    from brain.console import own_things

    for module in (mine_routes, own_things):
        monkeypatch.setattr(module, "is_own", lambda principal_id, owner_id: True)

    assert refused(database, "a_person_edits_and_forgets_their_own_memory") == (
        FAILED,
        "a colleague could edit or forget somebody else's memory",
    )


@pytest.mark.needs_db
def test_the_edit_check_fails_when_an_edit_leaves_the_old_words_in_use(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An edit that writes the replacement and no mark leaves two memories recalled, the old words
    beside the new. Delete this and the check can pass on an install that forgets to mark."""
    from sqlalchemy import select

    from brain.ops import memory_store

    monkeypatch.setattr(memory_store, "correction_row", lambda correction, actor: select(1))

    assert refused(database, "a_person_edits_and_forgets_their_own_memory") == (
        FAILED,
        "an edited memory was not what the person was shown afterwards",
    )


@pytest.mark.needs_db
def test_the_tier_check_fails_when_a_gated_change_is_proposed_below_its_tier(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A capability addition proposed at tier one would apply by itself. Delete this and the check
    can pass on an install whose proposals ignore the blast radius."""
    from brain.memory import tiers

    monkeypatch.setattr(
        tiers,
        "BLAST_RADIUS",
        {**tiers.BLAST_RADIUS, tiers.Change.CAPABILITY_ADDITION: tiers.Tier.AUTOMATIC},
    )

    assert refused(database, "every_learned_change_is_held_at_the_tier_its_reach_needs") == (
        FAILED,
        "a change that widens who sees what is not gated for a person",
    )


@pytest.mark.needs_db
def test_the_review_check_fails_when_a_conversations_learning_is_left_off_the_screen(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Learning screen was empty on every install where people asked Ask directly. Delete
    this and the check can pass on an install where it still is."""
    from brain.console import govern_estate

    monkeypatch.setattr(govern_estate, "conversation_learnings", lambda learnings, **kw: ())

    assert refused(database, "a_conversation_learning_is_reviewed_and_undone") == (
        FAILED,
        "a learning a person's conversation formed was not on their department's Learning "
        "screen, in effect and undoable",
    )


@pytest.mark.needs_db
def test_the_figures_check_fails_when_recall_ignores_the_saved_half_life(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Recall decaying at the product's figure whatever was saved is the defect this leaf exists to
    prevent. Delete this and the check can pass on an install where the Learning screen's figure
    reaches the table and nothing that reads memories."""
    from brain.memory import formation

    monkeypatch.setattr(formation, "in_force_half_life_days", lambda: formation.HALF_LIFE_DAYS)

    assert refused(database, "learning_figures_are_set_in_bounds_and_move_no_tier") == (
        FAILED,
        "an inference was still recalled past the saved lifetime",
    )


@pytest.mark.needs_db
def test_the_figures_check_fails_when_agreement_can_promote_a_gated_change(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A promotion that counts agreement for any tier lets a saved figure of two open a scope
    widening. Delete this and the check can pass on an install where it does."""
    from brain.memory import tiers

    def any_tier(proposal: Any, occurrences: Any, *, now: Any, agreement: int, **kw: Any) -> bool:
        return tiers.independent(occurrences, now=now) >= agreement

    monkeypatch.setattr(tiers, "may_promote", any_tier)

    assert refused(database, "learning_figures_are_set_in_bounds_and_move_no_tier") == (
        FAILED,
        "a saved figure let a change be promoted its tier does not allow",
    )
