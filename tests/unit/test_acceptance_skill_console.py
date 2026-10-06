"""The install checks for the Skills screen's acts and the builder's second person: registered,
passing, and made to fail.

The pure half holds the checks to the leaves they prove, to `docs/wbs.json`, and to the rule that a
reason is a literal sentence short enough to be stored whole. The database half builds PostgreSQL to
head once and runs the checks as the worker would: each passes with no reason and every table holds
afterwards what it held before, the library's rows, the drafts and the published agent included.
Then each check is run against a product broken in the one place its sentence depends on, and fails
with its own sentence.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M27.11.8, M27.15.55, M27.15.56, M27.15.31
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

from brain.ops import acceptance_skill_console as skill_checks
from brain.ops.acceptance import FAILED, PASSED, REASON_CHARS, Check, check_modules, registered
from tests.unit.test_acceptance import at_head, checks_in
from tests.unit.test_acceptance_lifecycle import every_count

ROOT = Path(__file__).resolve().parents[2]

MODULE = "brain.ops.acceptance_skill_console"

LIBRARY = "a_skills_library_acts_are_rows_and_assignments_follow_them"
WIDENED = "a_widened_publish_waits_for_a_second_person_who_publishes_it"

#: Each check and the leaves it proves.
LEAVES = {
    LIBRARY: ("M27.11.8", "M27.15.55", "M27.15.56"),
    WIDENED: ("M27.15.31",),
}


def mine() -> tuple[Check, ...]:
    return registered((MODULE,))


def by_name(name: str) -> Check:
    [one] = [one for one in mine() if one.name == name]
    return one


# ------------------------------------------------------------------------ without a server
def test_the_skill_console_checks_are_registered_with_the_leaves_they_prove() -> None:
    """The module declares its checks, each with its leaves, and the suite finds it. Delete this
    and a check can fall out of the module or out of the suite with the Install page listing one
    fewer row, or close a leaf its routes do not exercise."""
    assert [(one.name, one.leaves) for one in mine()] == list(LEAVES.items())
    assert MODULE in check_modules()


def test_the_skill_console_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them, held here
    beside the module's other tests rather than in a list every package appends to (#287). Delete
    this and a check can drop out of the module with the page simply listing one fewer row."""
    assert checks_in(MODULE) == list(LEAVES)


def test_the_module_stands_after_the_skills_own_checks() -> None:
    """Held against the skills module's key, which is outside this one: these checks build on the
    library acts that module proves. Delete this and the module can be placed ahead of them."""
    from brain.ops import acceptance_checks_skills

    assert skill_checks.CHECK_ORDER > acceptance_checks_skills.CHECK_ORDER


def test_every_leaf_the_skill_console_checks_name_is_a_leaf_of_the_work_breakdown() -> None:
    """Held against `docs/wbs.json`, which is outside the module. WBS ids are positional, so an id
    that moved reads as a correct claim. Delete this and a result can be recorded against an id no
    task carries."""
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    for one in mine():
        assert set(one.leaves) <= leaves, one.name


def test_every_reason_the_skill_console_checks_give_is_a_literal_sentence_stored_whole() -> None:
    """`A_RESULT_NAMES_NO_DATA`: every reason is a string literal, never built from a value, and
    fits the column so the Install page shows the sentence the source wrote. Delete this and a
    reason can quote a row the check read, or be cut mid-word on the page."""
    tree = ast.parse(Path(skill_checks.__file__).read_text(encoding="utf-8"))
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
    assert len(said) > 15
    assert all(0 < len(one) <= REASON_CHARS for one in said)


# --------------------------------------------------------------------------- a real run
@pytest.fixture(scope="module")
def head() -> Iterator[str]:
    """One database at head for the file: every check rolls back, so the runs share it."""
    with at_head("brain_acceptance_skill_console") as url:
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


def _failed(url: str, name: str) -> str:
    [(outcome, reason)] = run_checks(url, (by_name(name),)).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_on_a_real_database_every_skill_console_check_passes_and_leaves_nothing_behind(
    head: str,
) -> None:
    """**The checks as the worker runs them, against PostgreSQL at head.** Each passes with no
    reason, and every table, the library's rows, the drafts, the published agent and the ledger
    among them, holds afterwards exactly what it held before. Delete this and a check that cannot
    pass on the real schema, or one that leaves an agent or a retired skill on a client's install,
    reaches the owner's server first."""
    before = every_count(head)
    outcomes = run_checks(head, mine())
    after = every_count(head)

    assert outcomes == dict.fromkeys(LEAVES, (PASSED, ""))
    assert after == before


# ------------------------------------------------------------------ each check can fail
@pytest.mark.needs_db
def test_a_retirement_naming_nobody_fails_the_library_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With retiring a version naming no agent still running it, the check says so. Delete this
    and M27.15.56 closes over a retirement that leaves its holders for nobody to find."""
    from brain import skill_routes

    real = skill_routes.RetirementView

    def naming_nobody(**fields: Any) -> Any:
        return real(**{**fields, "holding": ()})

    monkeypatch.setattr("brain.skill_routes.RetirementView", naming_nobody)
    assert _failed(head, LIBRARY) == "retiring a version did not name the agent still running it"


@pytest.mark.needs_db
def test_a_widened_publish_that_needs_nobody_fails_the_second_person_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no second person ever needed, the author's publish goes out on their word alone.
    Delete this and M27.15.31 closes over a builder whose one hazard ships unreviewed."""
    monkeypatch.setattr("brain.agent_builder_routes.second_people_needed", lambda widened: 0)
    assert _failed(head, WIDENED) == (
        "a publish reaching the price list did not wait for a second person"
    )
