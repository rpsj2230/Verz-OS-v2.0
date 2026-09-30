"""An agent page's install acceptance checks: registered, passing, and made to fail.

The pure half holds the checks to the leaves they prove, to `docs/wbs.json`, and to the rule that a
reason is a literal sentence short enough to be stored whole. The database half builds PostgreSQL to
head once and runs the checks as the worker would: each passes with no reason and every table in the
database holds afterwards what it held before. Then each check is run against a product broken in
the one place its sentence depends on, and fails with its own sentence.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M39.1.1.2, M39.1.1.4, M39.1.1.5, M39.1.3.1, M39.1.3.2, M39.1.3.3, M39.1.3.4
"""

from __future__ import annotations

import ast
import asyncio
import json
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest

from brain.ops import acceptance_workspace as workspace_checks
from brain.ops.acceptance import FAILED, PASSED, REASON_CHARS, Check, check_modules, registered
from tests.unit.test_acceptance import at_head, checks_in
from tests.unit.test_acceptance_lifecycle import every_count

ROOT = Path(__file__).resolve().parents[2]

#: The module under test, by the name `check_modules` finds it under.
MODULE = "brain.ops.acceptance_workspace"

#: Each check and the leaves it proves.
LEAVES = {
    "an_agent_pins_its_parts_and_its_diff_shows_local_changes": (
        "M39.1.1.2",
        "M39.1.1.4",
        "M39.1.1.5",
    ),
    "an_agents_figures_follow_the_period_and_project_to_its_budget": (
        "M39.1.3.1",
        "M39.1.3.2",
        "M39.1.3.3",
        "M39.1.3.4",
    ),
}


def mine() -> tuple[Check, ...]:
    return registered((MODULE,))


def by_name(name: str) -> Check:
    [one] = [one for one in mine() if one.name == name]
    return one


# ------------------------------------------------------------------------ without a server
def test_the_workspace_checks_are_registered_with_the_leaves_they_prove() -> None:
    """The module declares its checks in the order the page lists them, each with its leaves, and
    the suite runs it. Delete this and a check can fall out of the module or out of the suite with
    the Install page simply listing one fewer row, or close a leaf its flow does not exercise."""
    assert [(one.name, one.leaves) for one in mine()] == list(LEAVES.items())
    assert MODULE in check_modules()


def test_the_workspace_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them, held here
    beside the module's other tests rather than in a list every package appends to (#287). Delete
    this and a check can drop out of the module with the page simply listing one fewer row."""
    assert checks_in(MODULE) == list(LEAVES)


def test_every_leaf_the_workspace_checks_name_is_a_leaf_of_the_work_breakdown() -> None:
    """Held against `docs/wbs.json`, which is outside the module. WBS ids are positional, so an id
    that moved reads as a correct claim. Delete this and a result can be recorded against an id no
    task carries."""
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    for one in mine():
        assert set(one.leaves) <= leaves, one.name


def _reasons() -> list[str]:
    """Every reason the module raises a verdict with, read from its source."""
    tree = ast.parse(Path(workspace_checks.__file__).read_text(encoding="utf-8"))
    said: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id not in ("CheckFailedError", "CheckNotRunError"):
            continue
        [argument] = node.args
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
            said.append(argument.value)
        else:
            pytest.fail(ast.unparse(node))
    return said


def test_every_reason_the_workspace_checks_give_is_a_literal_sentence_stored_whole() -> None:
    """`A_RESULT_NAMES_NO_DATA`: every reason is a string literal, never built from a value, and
    fits the column so the Install page shows the sentence the source wrote. Delete this and a
    reason can quote a row the check read, or be cut mid-word on the page."""
    said = _reasons()
    assert len(said) > 15
    assert all(0 < len(one) <= REASON_CHARS for one in said)


def test_the_budget_authority_the_route_asks_for_is_the_one_a_budget_warning_reaches() -> None:
    """The route restates `brain.ops.budget_stop.BUDGET_AUTHORITY` rather than importing the
    stop's machinery. Delete this and the two drift, so an agent's budget is set by somebody the
    budget's own warning never reaches."""
    from brain.agent_workspace_routes import BUDGET_AUTHORITY
    from brain.ops.budget_stop import BUDGET_AUTHORITY as WARNED

    assert BUDGET_AUTHORITY == WARNED


# --------------------------------------------------------------------------- a real run
@pytest.fixture(scope="module")
def head() -> Iterator[str]:
    """One database at head for the file: every check rolls back, so the runs share it."""
    with at_head("brain_acceptance_workspace") as url:
        yield url


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

    return {one.name: (one.outcome, one.reason) for one in asyncio.run(run())}


@pytest.mark.needs_db
def test_on_a_real_database_every_workspace_check_passes_and_leaves_nothing_behind(
    head: str,
) -> None:
    """**The checks as the worker runs them, against PostgreSQL at head.** Each passes with no
    reason, and every table in the database, the agent's rows, its requests, its costs, its budget
    versions and the ledger among them, holds afterwards exactly what it held before. Delete this
    and a check that cannot pass on the real schema, or one that commits an agent or a budget to a
    client's install, reaches the owner's server first."""
    before = every_count(head)
    outcomes = run_checks(head, mine())
    after = every_count(head)

    assert outcomes == dict.fromkeys(LEAVES, (PASSED, ""))
    assert after == before


# ------------------------------------------------------------------ each check can fail
@pytest.mark.needs_db
def test_an_install_that_forgets_what_was_changed_here_fails_the_composition_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the divergence read returning nothing, the persona changed on the install is not
    flagged, and the check says so. Delete this and the check could pass over an install whose
    local edits nobody is told about."""
    monkeypatch.setattr("brain.agent_routes.divergent_parts", lambda instance: frozenset())
    name = "an_agent_pins_its_parts_and_its_diff_shows_local_changes"

    assert run_checks(head, (by_name(name),))[name] == (
        FAILED,
        "the divergence flag did not name exactly the changed persona",
    )


@pytest.mark.needs_db
def test_an_automation_counted_as_a_message_fails_the_figures_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With every traffic class read as a person's, the automation's run is counted as a message,
    and the check says so. Delete this and the message figure could be the run figure renamed."""
    monkeypatch.setattr(
        "brain.console_stats_routes.PERSON_TRAFFIC",
        frozenset({"human_interactive", "human_async", "automation", "system"}),
    )
    name = "an_agents_figures_follow_the_period_and_project_to_its_budget"

    assert run_checks(head, (by_name(name),))[name] == (
        FAILED,
        "an automation's run was counted as a message, or a period missed one",
    )


@pytest.mark.needs_db
def test_a_budget_anybody_may_set_fails_the_figures_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the budget authority asked of nobody, a member may set the agent's budget, and the
    check says so. Delete this and the check could pass over an install where anybody who can open
    an agent can raise what it may spend."""
    monkeypatch.setattr("brain.agent_workspace_routes.within_reach", lambda *args: True)
    name = "an_agents_figures_follow_the_period_and_project_to_its_budget"

    assert run_checks(head, (by_name(name),))[name] == (
        FAILED,
        "the budget authority did not decide who may set an agent's budget",
    )
