"""The memory install acceptance checks: registered, passing on PostgreSQL, and able to fail.

The pure half holds the four checks to the leaves they prove and to the work breakdown, and the
tables they write to the suite's own list. The database half builds PostgreSQL to head once for the
module and runs the checks as the worker would: each passes, and every table they write to holds,
row for row, what it held before. Then the property each check proves is broken, one at a time, by
replacing the product function the check relies on where the product looks it up, and the check
fails with its own sentence. A check that cannot fail would pass on an install that does not do
what its leaf says.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M16.1.2, M16.1.3, M16.1.4, M16.1.5, M16.4.1, M16.4.4, M16.6.3, M16.7.10, M16.7.12
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Iterator, Sequence
from typing import Any

import pytest

from brain.ops import acceptance_checks_memory as memory
from brain.ops.acceptance import FAILED, PASSED, Check, check_modules, registered
from tests.unit.test_acceptance import ROOT, WRITTEN_BY_CHECKS, at_head

MODULE = "brain.ops.acceptance_checks_memory"

#: Each memory check and the leaves it proves.
LEAVES = {
    "a_stated_memory_forms_and_only_its_person_reads_it": ("M16.1.2", "M16.7.12"),
    "a_memory_is_not_recalled_once_its_grant_goes": ("M16.1.4", "M16.4.4"),
    "an_inference_decays_and_a_statement_does_not": ("M16.1.3", "M16.4.1", "M16.7.10"),
    "a_model_sees_the_askers_memory_as_a_hint_only": ("M16.6.3", "M16.1.5"),
}

#: Every table the memory checks write to, which must hold afterwards exactly what it held before.
WRITTEN_BY_MEMORY_CHECKS = (
    "gate.department",
    "gate.scope",
    "auth.principal",
    "gate.capability_grant",
    "gate.grants_version",
    "gate.policy_epoch",
    "obs.audit_entry",
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
def test_the_memory_checks_prove_the_memory_leaves_and_nothing_else() -> None:
    """Each check names the leaves it was scoped to, and the module is in the suite. Delete this
    and a check can close a leaf it does not exercise, or fall out of the run with the Install page
    listing four rows fewer."""
    assert {check.name: check.leaves for check in mine()} == LEAVES
    assert MODULE in check_modules()


def test_every_leaf_the_memory_checks_name_is_a_leaf_of_the_work_breakdown() -> None:
    """WBS ids are positional, so an id that moved reads as a correct claim. Held against
    `docs/wbs.json`, which is outside the registry. Delete this and a result can close the wrong
    leaf on the owner's tracker."""
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {leaf for module in wbs["modules"] for leaf in module["leaf_ids"]}
    assert {leaf for check in mine() for leaf in check.leaves} <= leaves


def test_every_table_the_memory_checks_write_is_one_the_suite_measures() -> None:
    """The suite's run test counts `WRITTEN_BY_CHECKS` before and after the whole run. Delete this
    and a memory table can be left out of that count, so a check that committed a memory to a
    client's install would pass the suite."""
    assert set(WRITTEN_BY_MEMORY_CHECKS) <= set(WRITTEN_BY_CHECKS)


def test_the_stand_in_reply_and_the_decay_horizons_are_what_the_checks_argue() -> None:
    """The reply is a word nothing else holds, so finding it in a memory is finding a memory formed
    from an answer; the decay horizon is past three half-lives, where an inference is below the
    floor, and the stated horizon is ten years. Delete this and a horizon can be shortened until the
    decay check passes on an install whose inferences never decay."""
    from brain.memory.formation import HALF_LIFE_DAYS, RECALL_FLOOR, confidence_now
    from brain.memory.turn import EXTRACTED_CONFIDENCE

    assert "QZREPLYSTANDIN" in memory.REPLY
    from datetime import UTC, datetime, timedelta

    formed = datetime(2999, 1, 1, tzinfo=UTC)
    later = formed + timedelta(days=memory.DECAYED_AFTER_DAYS)
    assert memory.DECAYED_AFTER_DAYS >= 3 * HALF_LIFE_DAYS
    assert confidence_now(EXTRACTED_CONFIDENCE, formed_at=formed, now=later) < RECALL_FLOOR
    assert memory.STATED_AFTER_DAYS >= 3650


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
    with at_head("brain_acceptance_memory") as url:
        yield url


def contents(url: str) -> dict[str, tuple[int, str]]:
    """Every row of every table the checks write to, as a count and a digest of the rows."""
    from tests.fixtures.scratch_postgres import sql

    held: dict[str, tuple[int, str]] = {}
    for table in WRITTEN_BY_MEMORY_CHECKS:
        # The names are this module's constants, never input.
        [(count, digest)] = sql(
            url,
            f"SELECT count(*), coalesce(md5(string_agg(t::text, ',' ORDER BY t::text)), '')"  # noqa: S608
            f" FROM {table} t",
        )
        held[table] = (int(count), str(digest))
    return held


@pytest.mark.needs_db
def test_on_a_real_database_every_memory_check_passes_and_leaves_nothing_behind(
    database: str,
) -> None:
    """**The four checks as the worker runs them, against PostgreSQL at head.** Each passes with no
    reason, and every table any of them wrote to, the memory tables and the ledger among them,
    holds row for row what it held before. Delete this and a check that cannot pass on the real
    schema, or one that commits a reserved person's memory to a client's install, reaches the
    owner's server first."""
    before = contents(database)
    outcomes = run_checks(database, mine())
    after = contents(database)

    assert outcomes == dict.fromkeys(LEAVES, (PASSED, ""))
    assert after == before


# ------------------------------------------------------------- each check can fail
def refused(database: str, name: str) -> tuple[str, str]:
    return run_checks(database, (one(name),))[name]


@pytest.mark.needs_db
def test_the_formation_check_fails_when_the_answer_route_forms_nothing(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The defect the owner's install had until 2026-09-29: nothing called formation. Delete this
    and the check can pass on an install whose Ask remembers nothing."""
    from brain import api_routes

    async def nothing(state: object, turn: object) -> None:
        del state, turn

    monkeypatch.setattr(api_routes, "formed_after", nothing)

    assert refused(database, "a_stated_memory_forms_and_only_its_person_reads_it") == (
        FAILED,
        "saying remember that on Ask did not keep a stated memory",
    )


@pytest.mark.needs_db
def test_the_formation_check_fails_when_a_memory_names_no_department(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A memory naming its person alone is the M16.7.12 defect: nobody without a company-wide grant
    reads it on a screen. Delete this and the check can pass on an install where they do not."""
    from brain.memory import turn
    from brain.memory.formation import clause_place

    def person_only(principal_id: str, department: str | None = None) -> object:
        del department
        return clause_place(principal_id=principal_id)

    monkeypatch.setattr(turn, "own_scope", person_only)

    assert refused(database, "a_stated_memory_forms_and_only_its_person_reads_it") == (
        FAILED,
        "a stated memory was not kept in its person's own place",
    )


@pytest.mark.needs_db
def test_the_grant_check_fails_when_a_memory_records_less_than_its_person_held(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A memory tagged with less than its person held is recalled by readers who reach less than
    it was formed from. Delete this and the check can pass on an install that tags nothing."""
    from brain.core.entitlement import Capability
    from brain.memory import turn

    def one_tag(reach: object, now: object) -> tuple[Capability, ...]:
        del reach, now
        return (Capability(value="read:knowledge"),)

    monkeypatch.setattr(turn, "requirement_of", one_tag)

    assert refused(database, "a_memory_is_not_recalled_once_its_grant_goes") == (
        FAILED,
        "a memory did not record the capabilities its person held",
    )


@pytest.mark.needs_db
def test_the_decay_check_fails_when_an_inference_never_decays(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An inference kept at its formed confidence for ever is a one-off remark treated as a rule.
    Delete this and the check can pass on an install whose inferences never fade."""
    from brain.memory import formation

    monkeypatch.setattr(formation, "DECAYS_WITH_TIME", dict.fromkeys(formation.MemoryKind, False))

    assert refused(database, "an_inference_decays_and_a_statement_does_not") == (
        FAILED,
        "an inference was still recalled after three half-lives",
    )


@pytest.mark.needs_db
def test_the_hint_check_fails_when_the_answer_route_recalls_nothing_for_the_model(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and the check can pass on an install whose models are never told anything a
    person asked to be remembered."""
    from brain import api_routes

    def unhinted(state: object, lane: object, **kw: object) -> object:
        del state, kw
        return lane

    monkeypatch.setattr(api_routes, "with_hints", unhinted)

    assert refused(database, "a_model_sees_the_askers_memory_as_a_hint_only") == (
        FAILED,
        "a model was not shown the asker's memory as a hint",
    )
