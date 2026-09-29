"""The tool acceptance checks: registered, passing on a real schema, and able to fail.

The pure half holds the checks to the suite and runs the sensitive-effect check, which reads no
table, against the install's own registry and against a registry broken two ways: one that no
longer asks a tool named for an effect to declare it, and one that lets a declared tool rise past a
person. The database half builds PostgreSQL to head and runs the three checks as the worker would:
they pass, and the catalogue, the switches and the ledger hold afterwards what they held before.
Then each database check is run against the install broken in the way its sentence rules out: a
start-up write that writes nothing, a catalogue table without its name constraint, a guard that no
longer asks the switch, a department administrator allowed the install's switch, and a stop that
ignores whose department a call is from. Each is a failed check with its own sentence.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M38.5.1
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, Check, reason_for, registered
from brain.ops.acceptance_run import Harness
from brain.ops.tool_store import stops_for_call
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, counts

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_tools"

CATALOGUE = "every_registered_tool_is_a_catalogue_row_under_the_name_grammar"
SENSITIVE = "a_tool_named_for_a_sensitive_effect_must_declare_it"
SWITCH = "a_switched_off_tool_is_refused_and_a_department_stops_its_own"

#: Each check and the leaves it proves, as the coordinator scoped them.
LEAVES = {
    CATALOGUE: ("M12.1.1", "M12.1.4"),
    SENSITIVE: ("M12.3.8",),
    SWITCH: ("M12.4.3",),
}

#: Every table the tool checks write to, which must hold afterwards what it held before.
WRITTEN_BY_TOOL_CHECKS = ("agent.tool_definition", "agent.tool_switch")

#: Pinned far from any wall clock, for CLAUDE.md's reason about fixtures with dates in them.
LONG_AGO = datetime(2019, 3, 6, 9, 0, tzinfo=UTC)


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def sensitive_outcome() -> tuple[str, str]:
    """The sensitive-effect check's outcome and reason, run with no database, as it needs none."""
    harness = Harness(run="0a1b2c3d", now=LONG_AGO, settings=settings_from({}), connection=None)  # type: ignore[arg-type]
    try:
        asyncio.run(mine()[SENSITIVE].run(harness))
    except Exception as exc:
        return reason_for(exc)
    return PASSED, ""


# ------------------------------------------------------------------------ without a server
def test_the_tool_checks_are_registered_with_the_leaves_they_prove() -> None:
    """Each check names the leaves it was scoped to, and each is a leaf of the work breakdown.
    Delete this and a check can close a leaf it does not exercise, or name an id no task has."""
    assert {name: one.leaves for name, one in mine().items()} == LEAVES
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    assert {leaf for one in LEAVES.values() for leaf in one} <= leaves


def test_the_sensitive_effect_check_passes_against_the_install_s_own_registry() -> None:
    """The positive run: seven effects refused undeclared and taken declared, reads taken. Delete
    this and the check can refuse the declared case too, which reads as registration broken."""
    assert sensitive_outcome() == (PASSED, "")


def test_the_sensitive_effect_check_fails_when_registration_stops_asking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M12.3.8 broken at the rule registration applies. Delete this and a check that passes with
    the rule gone stands between `drive.delete_file` and an Autonomous rung."""
    import brain.tools.registry as registry

    monkeypatch.setattr(
        registry, "assert_sensitive_effect_declared", lambda definition, named: None
    )
    assert sensitive_outcome() == (
        FAILED,
        "a tool named for a sensitive effect that declares none was registered",
    )


def test_the_sensitive_effect_check_fails_when_a_declared_tool_rises_past_a_person(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The declared half broken: the Tools screen's ceiling lets the tool run unapproved. Delete
    this and declaring an effect can mean nothing at the gate with the check green."""
    import brain.tools.registry as registry
    from brain.gate.injection import AutonomyTier

    monkeypatch.setattr(registry, "leash_ceiling", lambda definition: AutonomyTier.AUTONOMOUS)
    assert sensitive_outcome() == (
        FAILED,
        "a tool with a sensitive effect is allowed past a person",
    )


# --------------------------------------------------------------------------- a real run
def run_checks(url: str, checks: Sequence[Check]) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url
    from brain.ops.acceptance_run import run_suite
    from brain.session import make_app_engine

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

    return {one.name: (one.outcome, one.reason) for one in asyncio.run(run())}


def tool_counts(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    # The names are this module's constants, never input.
    return {
        one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0])  # noqa: S608
        for one in WRITTEN_BY_TOOL_CHECKS
    }


@pytest.mark.needs_db
def test_on_a_real_database_every_tool_check_passes_and_leaves_nothing_behind() -> None:
    """**The three checks as the worker runs them, against PostgreSQL at head.** Each passes with
    no reason, and the catalogue, the switches, the people, the grants and the ledger hold exactly
    what they held before. Delete this and a check that cannot pass on the real schema, or one
    that commits a stop on a client's tool, reaches the owner's server first."""
    with at_head("brain_acceptance_tools") as url:
        before = (counts(url), tool_counts(url))
        outcomes = run_checks(url, tuple(mine().values()))
        after = (counts(url), tool_counts(url))

    assert outcomes == dict.fromkeys(LEAVES, (PASSED, ""))
    assert after == before


async def _written_nowhere(sessions: Any, registry: Any) -> int:
    del sessions
    return len(registry)


def _unguarded(
    name: str, handler: Callable[..., object], source: Any, args: Any, kwargs: Any
) -> Any:
    del name, source

    async def run() -> object:
        answered = handler(*args, **kwargs)
        return await answered if asyncio.iscoroutine(answered) else answered

    return run()


def _every_department(tool: str, principal_id: str | None) -> Any:
    """Every stop on the tool, whoever calls: the statement as though nobody could be placed."""
    del principal_id
    return stops_for_call(tool, None)


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("check", "module", "attribute", "broken", "reason"),
    [
        (
            CATALOGUE,
            "brain.ops.tool_store",
            "record_catalogue",
            _written_nowhere,
            "a tool the install registers has no row in agent.tool_definition",
        ),
        (
            SWITCH,
            "brain.tools.registry",
            "_checked_call",
            _unguarded,
            "a call to a switched-off tool was not refused naming the switch",
        ),
        (
            SWITCH,
            "brain.tool_routes",
            "may_switch_install",
            lambda reach, now: True,
            "a department admin may switch a tool for the whole install",
        ),
        (
            SWITCH,
            "brain.ops.tool_store",
            "stops_for_call",
            _every_department,
            "a department's stop refused a call from another department",
        ),
    ],
)
def test_each_database_check_fails_when_the_install_breaks_what_it_says(
    monkeypatch: pytest.MonkeyPatch,
    check: str,
    module: str,
    attribute: str,
    broken: Any,
    reason: str,
) -> None:
    """A check shown able to fail, once per property it states: the start-up write missing, the
    guard not asking the switch, a department administrator holding the install's switch, and a
    department's stop reaching another department. Delete this and any of the four can go with
    the check still green."""
    import importlib

    monkeypatch.setattr(importlib.import_module(module), attribute, broken)
    with at_head(f"brain_acceptance_tools_{attribute}"[:40]) as url:
        outcome = run_checks(url, (mine()[check],))

    assert outcome[check] == (FAILED, reason)


@pytest.mark.needs_db
def test_the_catalogue_check_fails_when_the_table_no_longer_holds_the_grammar() -> None:
    """The database's own wall taken down: the name constraint dropped, and a name outside the
    grammar is a row. Delete this and the check can pass with the table taking any name, which
    is the second wall the leaf asks for."""
    from tests.fixtures.scratch_postgres import sql

    with at_head("brain_acceptance_tools_grammar") as url:
        [(constraint,)] = sql(
            url,
            "SELECT conname FROM pg_constraint WHERE conrelid = 'agent.tool_definition'::regclass"
            " AND conname LIKE '%%name_grammar%%'",
        )
        sql(url, f'ALTER TABLE agent.tool_definition DROP CONSTRAINT "{constraint}"')
        outcome = run_checks(url, (mine()[CATALOGUE],))

    assert outcome[CATALOGUE] == (
        FAILED,
        "agent.tool_definition took a name outside the tool grammar",
    )
