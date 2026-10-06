"""The install checks for the console pages around an agent: registered, passing, and made to fail.

The pure half holds the checks to the leaves they prove, to `docs/wbs.json`, and to the rule that a
reason is a literal sentence short enough to be stored whole. The database half builds PostgreSQL to
head once and runs the checks as the worker would: each passes with no reason and every table holds
afterwards what it held before, the connection the projections check makes for itself included.
Then each check is run against a product broken in the one place its sentence depends on, and fails
with its own sentence.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M27.11.11, M39.1.2.3, M39.2.1.1, M39.2.1.3, M39.2.1.5, M39.2.4.3, M27.11.16, M27.8.9
Task ids: M27.15.58, M27.15.9, M27.15.5
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

from brain.ops import acceptance_agent_console as console_checks
from brain.ops.acceptance import FAILED, PASSED, REASON_CHARS, Check, check_modules, registered
from tests.unit.test_acceptance import at_head, checks_in
from tests.unit.test_acceptance_lifecycle import every_count

ROOT = Path(__file__).resolve().parents[2]

MODULE = "brain.ops.acceptance_agent_console"

HEADER = "the_agent_page_header_and_its_views_come_in_one_answer"
STRIP = "an_agents_connector_strip_counts_only_what_its_reader_may_see"
FIELDS = "an_agents_connector_shows_its_run_fields_and_its_health"
LAYOUT = "each_channel_an_agent_is_offered_on_carries_its_own_layout"
ABOUT = "an_agents_about_flow_is_derived_from_its_setup"
PROMPTS = "an_agents_instructions_are_edited_and_given_back"
SOURCE = "a_source_page_lists_the_agents_and_skills_that_use_it"
RUNS = "a_skills_runs_are_counted_from_invocations_its_reader_may_see"
STEWARDS = "a_persons_overview_lists_the_agents_they_steward"

#: Each check and the leaves it proves.
LEAVES = {
    HEADER: ("M27.11.11", "M39.1.2.3"),
    STRIP: ("M39.2.1.1",),
    FIELDS: ("M39.2.1.3", "M39.2.1.5"),
    LAYOUT: ("M39.2.4.3",),
    ABOUT: ("M27.11.16",),
    PROMPTS: ("M27.8.9",),
    SOURCE: ("M27.15.58",),
    RUNS: ("M27.15.9",),
    STEWARDS: ("M27.15.5",),
}


def mine() -> tuple[Check, ...]:
    return registered((MODULE,))


def by_name(name: str) -> Check:
    [one] = [one for one in mine() if one.name == name]
    return one


# ------------------------------------------------------------------------ without a server
def test_the_agent_console_checks_are_registered_with_the_leaves_they_prove() -> None:
    """The module declares its checks, each with its leaves, and the suite finds it. Delete this
    and a check can fall out of the module or out of the suite with the Install page listing one
    fewer row, or close a leaf its route does not exercise."""
    assert [(one.name, one.leaves) for one in mine()] == list(LEAVES.items())
    assert MODULE in check_modules()


def test_the_agent_console_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them, held here
    beside the module's other tests rather than in a list every package appends to (#287). Delete
    this and a check can drop out of the module with the page simply listing one fewer row."""
    assert checks_in(MODULE) == list(LEAVES)


def test_the_module_stands_after_the_agent_page_s_own_checks() -> None:
    """Held against the workspace module's key, which is outside this one: these checks are about
    the pages around an agent and read after the agent page's own. Delete this and the module can
    be placed ahead of the checks whose agent it builds on, or tie with them unnoticed."""
    from brain.ops import acceptance_workspace

    assert console_checks.CHECK_ORDER > acceptance_workspace.CHECK_ORDER


def test_every_leaf_the_agent_console_checks_name_is_a_leaf_of_the_work_breakdown() -> None:
    """Held against `docs/wbs.json`, which is outside the module. WBS ids are positional, so an id
    that moved reads as a correct claim. Delete this and a result can be recorded against an id no
    task carries."""
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    for one in mine():
        assert set(one.leaves) <= leaves, one.name


def _reasons() -> list[str]:
    """Every reason the module raises a verdict with, read from its source."""
    tree = ast.parse(Path(console_checks.__file__).read_text(encoding="utf-8"))
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


def test_every_reason_the_agent_console_checks_give_is_a_literal_sentence_stored_whole() -> None:
    """`A_RESULT_NAMES_NO_DATA`: every reason is a string literal, never built from a value, and
    fits the column so the Install page shows the sentence the source wrote. Delete this and a
    reason can quote a row the check read, or be cut mid-word on the page."""
    said = _reasons()
    assert len(said) > 30
    assert all(0 < len(one) <= REASON_CHARS for one in said)


def test_the_sources_the_check_may_connect_are_sources_this_release_ships() -> None:
    """Held against the shipped declarations, which are outside the module: a name the release
    does not ship would make the projections check connect nothing and never run. Delete this and
    renaming a connector leaves M39.2.1.3 on a check that is not run on any install."""
    from brain.connectors.declaration import shipped

    assert set(console_checks.CONNECTABLE_HERE) <= set(shipped())


# --------------------------------------------------------------------------- a real run
@pytest.fixture(scope="module")
def head() -> Iterator[str]:
    """One database at head for the file: every check rolls back, so the runs share it."""
    with at_head("brain_acceptance_agent_console") as url:
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
def test_on_a_real_database_every_agent_console_check_passes_and_leaves_nothing_behind(
    head: str,
) -> None:
    """**The checks as the worker runs them, against PostgreSQL at head.** Each passes with no
    reason, and every table, the agents, the skills, the connection and its attempt, the feature
    switch and the ledger among them, holds afterwards exactly what it held before. Delete this and
    a check that cannot pass on the real schema, or one that leaves a connection or an edited
    instruction on a client's install, reaches the owner's server first."""
    before = every_count(head)
    outcomes = run_checks(head, mine())
    after = every_count(head)

    assert outcomes == dict.fromkeys(LEAVES, (PASSED, ""))
    assert after == before


# ------------------------------------------------------------------ each check can fail
@pytest.mark.needs_db
def test_a_workspace_answer_without_the_profile_fails_the_header_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the Profile left out of the workspace answer, moving to the Profile would ask again.
    Delete this and M39.1.2.3 closes on a check that never looked for the Profile."""
    monkeypatch.setattr("brain.agent_routes.profile_view", lambda *args: None)
    assert _failed(head, HEADER) == (
        "the workspace answer left out the Profile a settings reader opens"
    )


@pytest.mark.needs_db
def test_a_strip_naming_every_source_fails_the_strip_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With every registered source told to every reader, the narrower reader is shown the source
    they may not read. Delete this and the overflow count can include what a reader may not see."""

    def everything(registry: Any, asked: Any) -> tuple[str, ...]:
        return tuple(sorted({one.source for one in registry.definitions() if one.source}))

    monkeypatch.setattr("brain.agent_routes.reachable_sources", everything)
    assert _failed(head, STRIP) == "the strip's rows were not the sources its reader may be told of"


@pytest.mark.needs_db
def test_fields_projected_at_the_readers_reach_alone_fail_the_fields_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the projection computed at the reader's reach and not the run's, a field the agent's
    ceiling withholds is shown. Delete this and M39.2.1.3 closes over the caller's reach alone."""
    monkeypatch.setattr("brain.agent_capability_routes.run_reach", lambda reach, record: reach)
    assert _failed(head, FIELDS) == "a field the agent's ceiling withholds was shown as projected"


@pytest.mark.needs_db
def test_one_layout_for_every_surface_fails_the_layout_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With every surface laid out as plain text, Lark's cards are never chosen. Delete this and
    M39.2.4.3 closes over a profile that is the same everywhere."""
    from brain.console.agent_tabs import RenderProfile

    monkeypatch.setattr("brain.agent_routes.rendering_profile", lambda one: RenderProfile.PLAIN)
    assert _failed(head, LAYOUT) == "a surface's layout was not the one its adapter can carry"


@pytest.mark.needs_db
def test_an_about_flow_handed_the_setup_for_everybody_fails_the_about_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the setup handed to the flow for every reader, a member who may read no settings is
    told the agent's tools. Delete this and the About tab can describe a ceiling to anybody."""
    monkeypatch.setattr("brain.agent_about_routes.may_read_settings", lambda asked: True)
    assert _failed(head, ABOUT) == "a reader of no settings was told the agent's tools or its rows"


@pytest.mark.needs_db
def test_instructions_anybody_may_edit_fail_the_prompts_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the authority asked of nobody, a reader without it replaces an agent's instructions.
    Delete this and the Prompts screen can be a way round the instructions authority."""
    monkeypatch.setattr("brain.prompt_routes._asked_to_edit", lambda asked: None)
    monkeypatch.setattr("brain.prompt_routes.may_edit", lambda *args: True)
    assert _failed(head, PROMPTS) == (
        "a reader without the authority edited an agent's instructions"
    )


@pytest.mark.needs_db
def test_a_source_page_listing_every_agent_fails_the_source_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With every agent visible to every reader, a source's page names an agent to a reader in
    another department. Delete this and M27.15.58's narrowing is never looked at."""
    monkeypatch.setattr(
        "brain.connector_routes.visible_agent_ids",
        lambda records, viewer: frozenset(one.agent_id for one in records),
    )
    assert _failed(head, SOURCE) == (
        "an agent its reader may not see was listed on a source's page"
    )


@pytest.mark.needs_db
def test_runs_counted_at_nobody_s_basis_fail_the_runs_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With every invocation read and counted whoever reads, the member is shown the
    administrator's run. Both halves are broken, the statement's narrowing and the count's, because
    the route applies the basis twice and either alone still holds. Delete this and a skill's
    figure can be somebody else's afternoon."""
    from brain import console_stats_routes
    from brain.console.workspace import Basis

    statement = console_stats_routes.skill_invocations

    def every_row(*args: Any, **kwargs: Any) -> Any:
        return statement(*args, **{**kwargs, "basis": Basis.EVERYONE})

    def every_run(runs: Any, **kwargs: Any) -> tuple[Any, ...]:
        return tuple(runs)

    monkeypatch.setattr("brain.console_stats_routes.skill_invocations", every_row)
    monkeypatch.setattr("brain.console_stats_routes.skill_runs", every_run)
    assert _failed(head, RUNS) == "a skill's runs were not the invocations its reader may count"


@pytest.mark.needs_db
def test_a_roster_listing_every_agent_fails_the_steward_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the audience covering everybody, a reader in another department is shown the steward's
    agent on their Overview. Delete this and M27.15.5 closes over a list nobody narrowed."""
    monkeypatch.setattr(
        "brain.agent_routes.visible_agent_ids",
        lambda records, viewer: frozenset(one.agent_id for one in records),
    )
    assert _failed(head, STEWARDS) == (
        "an agent was listed to a reader its audience does not cover"
    )
