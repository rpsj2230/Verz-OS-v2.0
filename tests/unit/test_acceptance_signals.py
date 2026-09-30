"""The mark and pause install acceptance checks: registered, passing on PostgreSQL, able to fail.

The pure half holds the checks to their leaves and to the work breakdown. The database half builds
PostgreSQL to head once for the module and runs them as the worker would: each passes, and every
table they write to holds, row for row, what it held before. Then the property each check proves
is broken, one at a time, and the check fails with its own sentence.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M16.7.4, M16.7.13, M16.7.5
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Iterator, Sequence
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, Check, check_modules, registered
from tests.unit.test_acceptance import ROOT, WRITTEN_BY_CHECKS, at_head, checks_in

MODULE = "brain.ops.acceptance_checks_signals"

#: Each check and the leaves it proves.
LEAVES = {
    "a_mark_is_counted_and_changes_nothing": ("M16.7.4",),
    "pausing_an_agent_stops_what_its_runs_teach": ("M16.7.13", "M16.7.5"),
}

#: Every table the checks write to, which must hold afterwards exactly what it held before.
WRITTEN_BY_SIGNAL_CHECKS = (
    "gate.department",
    "gate.scope",
    "auth.principal",
    "gate.capability_grant",
    "gate.grants_version",
    "gate.policy_epoch",
    "obs.audit_entry",
    "know.item",
    "know.chunk",
    "know.classified_table",
    "know.classified_row",
    "agent.agent",
    "agent.template_instance",
    "agent.template_version",
    "obs.request_telemetry",
    "mem.persistent",
    "mem.adaptive",
    "mem.learning",
    "mem.mark",
    "agent.learning_pause",
)


def mine() -> tuple[Check, ...]:
    return registered((MODULE,))


def one(name: str) -> Check:
    [found] = [check for check in mine() if check.name == name]
    return found


# ------------------------------------------------------------------------ without a server
def test_the_signal_checks_prove_their_leaves_and_nothing_else() -> None:
    """Delete this and a check can close a leaf it does not exercise, or fall out of the run."""
    assert {check.name: check.leaves for check in mine()} == LEAVES
    assert MODULE in check_modules()


def test_every_leaf_the_signal_checks_name_is_a_leaf_of_the_work_breakdown() -> None:
    """WBS ids are positional. Delete this and a result can close the wrong leaf."""
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {leaf for module in wbs["modules"] for leaf in module["leaf_ids"]}
    assert {leaf for check in mine() for leaf in check.leaves} <= leaves


def test_every_table_the_signal_checks_write_is_one_the_suite_measures() -> None:
    """Delete this and a table the checks write can be left out of the suite's count, so a
    check that committed a mark or a pause to a client's install would pass the suite."""
    assert set(WRITTEN_BY_SIGNAL_CHECKS) <= set(WRITTEN_BY_CHECKS)


def test_the_signals_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them, held here
    beside the module's other tests so a package adding a check edits its own file and never a
    list every package appends to. Delete this and a check can drop out of the module with the
    page simply listing one fewer row."""
    assert checks_in(MODULE) == [
        "a_mark_is_counted_and_changes_nothing",
        "pausing_an_agent_stops_what_its_runs_teach",
    ]


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
    with at_head("brain_acceptance_signals") as url:
        yield url


def contents(url: str) -> dict[str, tuple[int, str]]:
    """Every row of every table the checks write to, as a count and a digest of the rows."""
    from tests.fixtures.scratch_postgres import sql

    held: dict[str, tuple[int, str]] = {}
    for table in WRITTEN_BY_SIGNAL_CHECKS:
        # The names are this module's constants, never input.
        [(count, digest)] = sql(
            url,
            f"SELECT count(*), coalesce(md5(string_agg(t::text, ',' ORDER BY t::text)), '')"  # noqa: S608
            f" FROM {table} t",
        )
        held[table] = (int(count), str(digest))
    return held


@pytest.mark.needs_db
def test_on_a_real_database_every_signal_check_passes_and_leaves_nothing_behind(
    database: str,
) -> None:
    """**The two checks as the worker runs them, against PostgreSQL at head.** Each passes with no
    reason, and every table either wrote to holds row for row what it held before. Delete this and
    a check that cannot pass on the real schema, or one that commits a mark or a pause to a
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
def test_the_mark_check_fails_when_anybody_may_mark_any_answer(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and the check can pass on an install where a colleague counts against
    somebody else's answer."""
    from brain.ops import learning_signal_store

    def anybodys(trace_id: str, principal_id: str, since: Any) -> Any:
        from sqlalchemy import func, select

        from brain.tables.telemetry import RequestTelemetryRow

        del principal_id
        return (
            select(func.count())
            .select_from(RequestTelemetryRow)
            .where(
                RequestTelemetryRow.trace_id == trace_id, RequestTelemetryRow.received_at >= since
            )
        )

    monkeypatch.setattr(learning_signal_store, "answer_given_to", anybodys)

    assert refused(database, "a_mark_is_counted_and_changes_nothing") == (
        FAILED,
        "a colleague could mark an answer somebody else was given",
    )


@pytest.mark.needs_db
def test_the_pause_check_fails_when_formation_ignores_a_pause(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and the check can pass on an install whose switch writes a row nothing reads."""
    from brain.ops import memory_store

    async def never(session: Any, agent_ids: Any) -> frozenset[str]:
        del session, agent_ids
        return frozenset()

    monkeypatch.setattr(memory_store, "paused_in", never)

    assert refused(database, "pausing_an_agent_stops_what_its_runs_teach") == (
        FAILED,
        "an agent whose learning is paused still formed a memory",
    )


@pytest.mark.needs_db
def test_the_pause_check_fails_when_a_memory_keeps_what_the_answer_said(
    database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A formation that kept the answer's words beside the person's is the M16.7.5 failure. Delete
    this and the check can pass on an install that remembers the values it reads."""
    import re

    from brain import api_routes
    from brain.memory.turn import turn_of as kept

    def with_the_answer(**kw: Any) -> Any:
        text = kw["outcome"].text
        if not text:
            return kept(**kw)
        heard = " ".join(re.findall(r"QZ[0-9A-F]+", text))
        return kept(**{**kw, "said": f"Remember that I heard {heard}. {kw['said']}"})

    monkeypatch.setattr(api_routes, "turn_of", with_the_answer)

    assert refused(database, "pausing_an_agent_stops_what_its_runs_teach") == (
        FAILED,
        "a value read from a source was kept in a memory or a rule",
    )
