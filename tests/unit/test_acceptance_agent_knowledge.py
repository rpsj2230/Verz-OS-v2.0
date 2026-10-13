"""The agent Knowledge section's install checks: registered, passing, and made to fail.

The pure half holds the checks to the leaves they prove, to `docs/wbs.json`, to the rule that a
reason is a literal sentence short enough to be stored whole, and to the one hold the link's
stand-in page needs. The database half builds PostgreSQL to head once and runs the checks as the
worker
would: each passes with no reason and every table holds afterwards what it held before. Then each
is run against a product broken in the place its sentence depends on, and fails with its own
sentence.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M39.9.1.1, M39.9.1.2, M39.9.1.3, M39.9.1.4, M39.9.1.6, M39.9.1.8, M39.2.3.5
"""

from __future__ import annotations

import ast
import asyncio
import json
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest

from brain.ops import acceptance_checks_agent_knowledge as module
from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, REASON_CHARS, Check, check_modules, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_answers import vault_the_providers
from tests.unit.test_acceptance_models import Providers, laddered

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_agent_knowledge"
LISTS = "knowledge_lists_by_reach_and_adding_says_what_follows"
LINKS = "a_link_is_fetched_once_and_a_private_address_is_refused"
ANSWERS = "an_agent_answers_from_a_file_added_on_its_page_and_cites_it"
LEAVES = {
    LISTS: ("M39.9.1.1", "M39.9.1.2", "M39.9.1.4", "M39.9.1.6"),
    LINKS: ("M39.9.1.3",),
    ANSWERS: ("M39.9.1.8", "M39.2.3.5"),
}


def mine() -> tuple[Check, ...]:
    return registered((MODULE,))


# ------------------------------------------------------------------------ without a server
def test_the_knowledge_checks_are_registered_with_the_leaves_they_prove() -> None:
    """The module declares its checks with their leaves, in the range this work owns, and the suite
    runs them. Delete this and a check can fall out of the suite with the Install page simply
    listing one fewer row, or claim a leaf its flow does not exercise."""
    assert [(one.name, one.leaves) for one in mine()] == list(LEAVES.items())
    assert MODULE in check_modules()
    assert checks_in(MODULE) == list(LEAVES)
    assert 500 <= module.CHECK_ORDER <= 599


def test_every_leaf_the_knowledge_checks_name_is_a_leaf_of_the_work_breakdown() -> None:
    """Held against `docs/wbs.json`, outside the module, because WBS ids are positional. Delete this
    and a result can be recorded against an id no task carries."""
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module_ in wbs["modules"] for one in module_["leaf_ids"]}
    for one in mine():
        assert set(one.leaves) <= leaves, one.name


def test_every_reason_the_knowledge_checks_give_is_a_literal_sentence_stored_whole() -> None:
    """`A_RESULT_NAMES_NO_DATA`: every reason is a string literal that fits the column. Delete this
    and a reason can quote a row the check read, or be cut mid-word on the page."""
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
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
    assert len(said) >= 15
    assert all(0 < len(one) <= REASON_CHARS for one in said)


def test_the_link_check_is_held_because_its_page_is_a_stand_in() -> None:
    """The fetched page is one the check made, so its pass is not proof the install reaches a real
    site, and the sweep must not close the leaf on it alone. Delete this and M39.9.1.3 closes on a
    stand-in."""
    held = json.loads((ROOT / "docs" / "proof-sweep-holds.json").read_text(encoding="utf-8"))
    assert "M39.9.1.3" in held["held"]


# --------------------------------------------------------------------------- a real run
@pytest.fixture(scope="module")
def head() -> Iterator[str]:
    """One database at head for the file, with the ladder the wizard writes: every check rolls
    back, so the runs share it."""
    with at_head("brain_acceptance_agent_knowledge") as url:
        laddered(url)
        yield url


@pytest.fixture
def vaulted(monkeypatch: pytest.MonkeyPatch) -> Providers:
    """The hosted profile with every provider's key in a vault the test answers for, so the
    answering check plans its stand-in and no provider of the product is asked."""
    return vault_the_providers(monkeypatch)


def run_checks(url: str, checks: Sequence[Check]) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url

    settings = settings_from(
        {
            "BRAIN_DATABASE_URL": url,
            "BRAIN_VAULT_ADDRESS": "https://vault.acceptance.invalid",
            "BRAIN_VAULT_TOKEN": "test-token-not-a-token",
        }
    )
    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings,
            commit="abc1234",
            checks=list(checks),
            force=True,
        )
    )
    return {one.name: (one.outcome, one.reason) for one in results}


@pytest.mark.needs_db
def test_on_a_real_database_the_knowledge_checks_pass_and_leave_nothing_behind(
    head: str, vaulted: Providers
) -> None:
    """**The checks as the worker runs them, against PostgreSQL at head.** Each passes with no
    reason and every table holds afterwards exactly what it held before, which is the proof that
    the held door wrote nothing a rollback could not take back. Delete this and a check that cannot
    pass on the real schema, or one that commits a document to a client's install, reaches the
    owner's server first."""
    before = counts(head)
    outcomes = run_checks(head, mine())
    after = counts(head)

    assert outcomes == dict.fromkeys(LEAVES, (PASSED, "")), outcomes
    assert after == before


@pytest.mark.needs_db
def test_a_section_that_lists_what_the_rule_does_not_reach_fails_the_lists_check(
    head: str, vaulted: Providers, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the agent's rule treated as reaching everything, the file added in acceptance_b is
    listed beside the agent, and the check says so. Delete this and the check could pass over a list
    that shows every document the reader may open whatever the agent is for."""
    monkeypatch.setattr("brain.agent_knowledge_routes.matching", lambda scope, items: tuple(items))

    assert run_checks(head, mine())[LISTS] == (
        FAILED,
        "a reader of acceptance_a was not listed exactly the reached file",
    )


@pytest.mark.needs_db
def test_a_section_shown_to_a_reader_without_the_tab_fails_the_lists_check(
    head: str, vaulted: Providers, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the tab's read answered yes for everybody, a person without the Knowledge tab is shown
    the section and the check says so. Delete this and the check could pass over a section that is
    a way to list what an agent draws on for anybody who can open the agent."""
    monkeypatch.setattr("brain.agent_knowledge_routes.may_read_knowledge_at", lambda asked: True)

    assert run_checks(head, mine())[LISTS] == (
        FAILED,
        "a reader without the Knowledge tab was shown the section",
    )


@pytest.mark.needs_db
def test_an_add_that_skips_the_address_rule_fails_the_links_check(
    head: str, vaulted: Providers, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the rule that names an address as reachable only from inside the network turned into
    nothing, the private address is fetched and the check says so. Delete this and the check could
    pass over an agent page that is a second, unchecked way to make the server read its own
    network."""
    monkeypatch.setattr("brain.tools.fetch._is_reachable_only_from_inside", lambda address: False)

    assert run_checks(head, mine())[LINKS] == (
        FAILED,
        "a web page was not fetched exactly once, or a private address was fetched",
    )


@pytest.mark.needs_db
def test_an_answer_that_is_never_counted_fails_the_answers_check(
    head: str, vaulted: Providers, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the count after an answer turned into nothing, the section shows no figure for the file
    the answer cited and the check says so. Delete this and the check could pass over counting that
    is switched on and never writes."""

    async def nothing(*_: object, **__: object) -> None:
        return None

    monkeypatch.setattr("brain.api_routes.counted_citations", nothing)

    assert run_checks(head, mine())[ANSWERS] == (
        FAILED,
        "the file the answer cited was not counted once beside the agent",
    )
