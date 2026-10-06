"""The agent page's header and strip install check: registered, passing, and made to fail.

The pure half holds the check to the leaves it proves, to `docs/wbs.json`, to the rule that a
reason is a literal sentence short enough to be stored whole, and its written-out strips to the
tabs this install populates. The database half builds PostgreSQL to head once and runs the check
as the worker would: it passes with no reason and every table holds afterwards what it held
before. Then it is run against a product broken in each place its sentence depends on, and fails
with its own sentence.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M39.1.2.1, M39.1.2.2
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

from brain.ops import acceptance_checks_agent_page as page_checks
from brain.ops.acceptance import FAILED, PASSED, REASON_CHARS, Check, check_modules, registered
from tests.unit.test_acceptance import at_head, checks_in
from tests.unit.test_acceptance_lifecycle import every_count

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_agent_page"
NAME = "an_agents_header_names_its_lineage_and_its_strip_follows_grants"
LEAVES = {NAME: ("M39.1.2.1", "M39.1.2.2")}


def mine() -> tuple[Check, ...]:
    return registered((MODULE,))


# ------------------------------------------------------------------------ without a server
def test_the_agent_page_check_is_registered_with_the_leaves_it_proves() -> None:
    """The module declares its one check with its leaves, and the suite runs it. Delete this and
    the check can fall out of the suite with the Install page simply listing one fewer row, or
    claim a leaf its flow does not exercise."""
    assert [(one.name, one.leaves) for one in mine()] == list(LEAVES.items())
    assert MODULE in check_modules()
    assert checks_in(MODULE) == list(LEAVES)


def test_every_leaf_the_agent_page_check_names_is_a_leaf_of_the_work_breakdown() -> None:
    """Held against `docs/wbs.json`, outside the module, because WBS ids are positional. Delete
    this and a result can be recorded against an id no task carries."""
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    for one in mine():
        assert set(one.leaves) <= leaves, one.name


def test_every_reason_the_agent_page_check_gives_is_a_literal_sentence_stored_whole() -> None:
    """`A_RESULT_NAMES_NO_DATA`: every reason is a string literal that fits the column. Delete this
    and a reason can quote a row the check read, or be cut mid-word on the page."""
    tree = ast.parse(Path(page_checks.__file__).read_text(encoding="utf-8"))
    said: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in ("CheckFailedError", "CheckNotRunError")
        ):
            [argument] = node.args
            assert isinstance(argument, ast.Constant), ast.unparse(node)
            said.append(str(argument.value))
    assert len(said) >= 8
    assert all(0 < len(one) <= REASON_CHARS for one in said)


def test_the_written_out_strips_are_the_tabs_this_install_populates_in_the_strips_order() -> None:
    """The check states the steward's strip in its own words rather than calling `tab_strip`, so it
    is held here to what that strip can be: the populated tabs, in the order the tab enum lists
    them. Delete this and a tab the install starts populating fails the check on the owner's server
    rather than here, where the constant can be moved with it."""
    from brain.agent_routes import POPULATED_HERE
    from brain.console.workspace import Tab

    expected = tuple(one.value for one in Tab if one in POPULATED_HERE)
    assert expected == page_checks.STEWARDS_STRIP
    assert set(page_checks.MEMORY_READERS_STRIP) <= set(expected)


# --------------------------------------------------------------------------- a real run
@pytest.fixture(scope="module")
def head() -> Iterator[str]:
    """One database at head for the file: every check rolls back, so the runs share it."""
    with at_head("brain_acceptance_agent_page") as url:
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
def test_on_a_real_database_the_agent_page_check_passes_and_leaves_nothing_behind(
    head: str,
) -> None:
    """**The check as the worker runs it, against PostgreSQL at head.** It passes with no reason,
    and every table holds afterwards exactly what it held before. Delete this and a check that
    cannot pass on the real schema, or one that commits an agent to a client's install, reaches the
    owner's server first."""
    before = every_count(head)
    outcomes = run_checks(head, mine())
    after = every_count(head)

    assert outcomes == dict.fromkeys(LEAVES, (PASSED, ""))
    assert after == before


@pytest.mark.needs_db
def test_a_header_that_drops_the_lineage_fails_the_agent_page_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the install read as missing, the header carries no template lineage, and the check
    says so. Delete this and the check could pass over a header that never says what the agent was
    installed from."""
    monkeypatch.setattr("brain.agent_routes.install_of", lambda *_: None)

    assert run_checks(head, mine())[NAME] == (
        FAILED,
        "the header did not carry the template lineage and version",
    )


@pytest.mark.needs_db
def test_a_header_that_tells_everybody_who_built_it_fails_the_agent_page_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With every reader treated as holding the Settings tab, a colleague is told who built the
    agent, and the check says so. Delete this and the check could pass over a route that sends the
    builder and the agent's state to everybody the audience covers."""
    monkeypatch.setattr("brain.agent_routes.holds_settings", lambda strip: True)

    assert run_checks(head, mine())[NAME] == (
        FAILED,
        "a reader without the Settings tab was told who built it",
    )


@pytest.mark.needs_db
def test_a_strip_that_ignores_the_readers_grants_fails_the_agent_page_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the tab read answered yes for everybody, the colleague holding one tab is offered all
    three, and the check says so. Delete this and the check could pass over a strip that shows
    every reader every populated tab."""
    monkeypatch.setattr("brain.console.workspace.permitted", lambda read, reach, now=None: True)

    assert run_checks(head, mine())[NAME] == (
        FAILED,
        "a reader holding one tab was not offered that tab alone",
    )
