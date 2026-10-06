"""The audience, manifest and trace graph install checks: registered, passing, and made to fail.

The pure half holds the checks to the leaves they prove, to `docs/wbs.json`, to literal reasons
short enough to be stored whole, and the trace check's vocabulary of endings to the two it restates:
the console's `RUN_ENDINGS` and the telemetry's `RequestStatus`. The database half builds
PostgreSQL to head once and runs the checks as the worker would: each passes with no reason and
every table holds afterwards what it held before. Then each check is run against a product broken
in the one place its sentence depends on, and fails with its own sentence.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M13.1.2, M13.2.2, M20.2.1
"""

from __future__ import annotations

import ast
import asyncio
import json
import re
import sys
from collections.abc import Iterator, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from brain.ops import acceptance_checks_agents as agent_checks
from brain.ops.acceptance import FAILED, PASSED, REASON_CHARS, Check, check_modules, registered
from tests.unit.test_acceptance import at_head, checks_in
from tests.unit.test_acceptance_lifecycle import every_count

ROOT = Path(__file__).resolve().parents[2]

#: The module under test, by the name `check_modules` finds it under.
MODULE = "brain.ops.acceptance_checks_agents"

#: Each check and the leaves it proves.
LEAVES = {
    "an_agent_is_seen_by_exactly_the_audience_its_level_names": ("M13.1.2",),
    "a_template_version_holds_every_section_and_nothing_else": ("M13.2.2",),
    "a_completed_runs_graph_is_read_for_the_trace_page": ("M20.2.1",),
}

AUDIENCE = "an_agent_is_seen_by_exactly_the_audience_its_level_names"
SCHEMA = "a_template_version_holds_every_section_and_nothing_else"
GRAPH = "a_completed_runs_graph_is_read_for_the_trace_page"


def mine() -> tuple[Check, ...]:
    return registered((MODULE,))


def by_name(name: str) -> Check:
    [one] = [one for one in mine() if one.name == name]
    return one


# ------------------------------------------------------------------------ without a server
def test_the_agent_checks_are_registered_with_the_leaves_they_prove() -> None:
    """The module declares its checks in the order the page lists them, each with its leaves, and
    the suite runs it. Delete this and a check can fall out of the module or out of the suite with
    the Install page simply listing one fewer row, or close a leaf its flow does not exercise."""
    assert [(one.name, one.leaves) for one in mine()] == list(LEAVES.items())
    assert MODULE in check_modules()
    assert checks_in(MODULE) == list(LEAVES)


def test_every_leaf_the_agent_checks_name_is_a_leaf_of_the_work_breakdown() -> None:
    """Held against `docs/wbs.json`, which is outside the module. WBS ids are positional, so an id
    that moved reads as a correct claim. Delete this and a result can be recorded against an id no
    task carries."""
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    for one in mine():
        assert set(one.leaves) <= leaves, one.name


def test_every_reason_the_agent_checks_give_is_a_sentence_stored_whole() -> None:
    """`A_RESULT_NAMES_NO_DATA`: every reason is a literal or a module constant holding one, never
    built from a value, and fits the column so the Install page shows the sentence the source
    wrote. Delete this and a reason can quote a row the check read, or be cut mid-word."""
    source = Path(agent_checks.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    said: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id != "CheckFailedError":
            continue
        [argument] = node.args
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
            said.append(argument.value)
        elif isinstance(argument, ast.Name):
            value = getattr(agent_checks, argument.id)
            assert isinstance(value, str), argument.id
            said.append(value)
        else:
            pytest.fail(ast.unparse(node))
    assert len(said) >= 15
    assert all(0 < len(one) <= REASON_CHARS for one in said)


def test_the_endings_the_trace_check_wants_are_the_consoles_and_the_telemetrys() -> None:
    """The check restates the endings the Trace page will draw a run for, and they are held here
    to the TypeScript array and to `RequestStatus`, both outside the module. Delete this and the
    check can accept an ending the page refuses to draw, so a run the page shows as unreadable is
    reported proved on the install."""
    from brain.ops.telemetry import RequestStatus

    graph = (ROOT / "console" / "src" / "components" / "graph.ts").read_text(encoding="utf-8")
    block = re.search(r"export const RUN_ENDINGS: readonly string\[\] = \[(.*?)\];", graph, re.S)
    assert block is not None
    console = set(re.findall(r'"([a-z_]+)"', block.group(1)))
    assert console == set(agent_checks.RUN_ENDINGS)
    assert {one.value for one in RequestStatus} == set(agent_checks.RUN_ENDINGS)


# --------------------------------------------------------------------------- a real run
@pytest.fixture(scope="module")
def head() -> Iterator[str]:
    """One database at head for the file: every check rolls back, so the runs share it."""
    with at_head("brain_acceptance_agents") as url:
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
def test_on_a_real_database_every_agent_check_passes_and_leaves_nothing_behind(
    head: str,
) -> None:
    """**The checks as the worker runs them, against PostgreSQL at head.** Each passes with no
    reason, and every table in the database, the agents, their templates, the stored trace and its
    read among them, holds afterwards exactly what it held before. Delete this and a check that
    cannot pass on the real schema, or one that commits an agent or a trace to a client's install,
    reaches the owner's server first."""
    before = every_count(head)
    outcomes = run_checks(head, mine())
    after = every_count(head)

    assert outcomes == dict.fromkeys(LEAVES, (PASSED, ""))
    assert after == before


# ------------------------------------------------------- M13.1.2, the audience made to fail
@pytest.mark.needs_db
def test_an_audience_that_admits_everybody_fails_the_audience_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With every agent visible to every reader, the personal agent is listed to a colleague, and
    the check says so. Delete this and the check could pass over an install whose Agents page
    lists one person's agent to the whole company."""
    monkeypatch.setattr(
        "brain.agent_routes.visible_agent_ids",
        lambda records, viewer: frozenset(one.agent_id for one in records),
    )

    assert run_checks(head, (by_name(AUDIENCE),))[AUDIENCE] == (
        FAILED,
        agent_checks.LISTED_OUTSIDE_ITS_AUDIENCE,
    )


@pytest.mark.needs_db
def test_an_audience_that_admits_nobody_fails_the_audience_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sibling: with no agent visible to anybody, the steward is not shown their own agents,
    and the check says so. Delete this and a route refusing every reader would satisfy a check
    written only about the readers it must refuse."""
    monkeypatch.setattr("brain.agent_routes.visible_agent_ids", lambda records, viewer: frozenset())

    assert run_checks(head, (by_name(AUDIENCE),))[AUDIENCE] == (
        FAILED,
        agent_checks.NOT_LISTED_TO_ITS_AUDIENCE,
    )


@pytest.mark.needs_db
def test_a_page_that_names_why_it_refused_fails_the_audience_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the workspace refusing a hidden agent in other words than a missing one, the check says
    the two were told apart. Delete this and the agent page could tell somebody outside an agent's
    audience that it exists, with its listing still correct."""
    import brain.agent_routes as routes
    from brain.core.errors import Absent

    original = routes._visible_record

    async def telling(session: Any, agent_id: str, asked: Any) -> Any:
        row = (await session.execute(routes.one_agent(agent_id))).scalar_one_or_none()
        try:
            return await original(session, agent_id, asked)
        except Absent:
            if row is not None:
                raise Absent("that agent is not yours to see") from None
            raise

    monkeypatch.setattr(routes, "_visible_record", telling)

    assert run_checks(head, (by_name(AUDIENCE),))[AUDIENCE] == (
        FAILED,
        agent_checks.HIDDEN_AGENT_TOLD_APART,
    )


# --------------------------------------------------------- M13.2.2, the schema made to fail
@pytest.mark.needs_db
def test_a_reader_that_drops_the_placeholders_fails_the_schema_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the gallery's reader losing a version's placeholders, the page still shows every
    section it has a place for, and the read-back says the version is not what was signed. Delete
    this and the two sections the page cannot show could be lost on the install unseen."""
    import brain.agent_routes as routes

    original = routes.manifest_of

    def dropping(document: Any) -> Any:
        return original(document).model_copy(update={"placeholders": ()})

    monkeypatch.setattr(routes, "manifest_of", dropping)

    assert run_checks(head, (by_name(SCHEMA),))[SCHEMA] == (FAILED, agent_checks.NOT_READ_BACK)


@pytest.mark.needs_db
def test_a_page_that_miscounts_the_golden_set_fails_the_schema_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the template page counting no golden questions, the check says the page did not show
    the version as written. Delete this and the page could drop a section the version declares."""
    import brain.agent_routes as routes

    original = routes.template_detail

    def miscounting(template_id: str, published: Any) -> Any:
        found = original(template_id, published)
        return None if found is None else found.model_copy(update={"golden_cases": 0})

    monkeypatch.setattr(routes, "template_detail", miscounting)

    assert run_checks(head, (by_name(SCHEMA),))[SCHEMA] == (
        FAILED,
        agent_checks.PAGE_NOT_AS_WRITTEN,
    )


@pytest.mark.needs_db
def test_an_install_without_the_schemas_closing_constraint_fails_the_schema_check(
    head: str,
) -> None:
    """With the database's refusal of a path outside the schema dropped, a version naming an
    audience is kept, and the check says so; the constraint is put back as it was. Delete this and
    the install could keep a template that publishes an agent into a company it has never seen."""
    from tests.fixtures.scratch_postgres import sql

    [(name, definition)] = sql(
        head,
        "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint"
        " WHERE conrelid = 'agent.template_version'::regclass"
        " AND conname LIKE '%document_holds_no_other_path'",
    )
    # The name and definition are the catalogue's own, read back above, never input.
    sql(head, f'ALTER TABLE agent.template_version DROP CONSTRAINT "{name}"')
    try:
        outcome = run_checks(head, (by_name(SCHEMA),))[SCHEMA]
    finally:
        sql(head, f'ALTER TABLE agent.template_version ADD CONSTRAINT "{name}" {definition}')

    assert outcome == (FAILED, agent_checks.OTHER_PATH_KEPT)


# ------------------------------------------------------- M20.2.1, the trace made to fail
@pytest.mark.needs_db
def test_a_route_reading_a_role_off_every_sign_in_fails_the_trace_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the payload role read off every sign-in, a person without it is shown the run, and
    the check says so. Delete this and the Trace page could draw any run for anybody signed in."""
    from brain.ops.tracing import PAYLOAD_ROLE

    monkeypatch.setattr(
        "brain.trace_routes.payload_roles_of", lambda claims: frozenset({PAYLOAD_ROLE})
    )

    assert run_checks(head, (by_name(GRAPH),))[GRAPH] == (
        FAILED,
        agent_checks.READ_WITHOUT_THE_ROLE,
    )


@pytest.mark.needs_db
def test_a_trace_whose_steps_hang_from_nothing_fails_the_trace_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With every step read back as a root, the run is no longer one graph hanging from its
    request, and the check says so. Delete this and the route could answer a heap of steps the
    page draws as unconnected boxes."""
    from brain.ops.trace_store import StoredTraces

    original = StoredTraces.read

    async def loose(self: StoredTraces, **asked: Any) -> Any:
        return tuple(replace(one, parent=None) for one in await original(self, **asked))

    monkeypatch.setattr(StoredTraces, "read", loose)

    assert run_checks(head, (by_name(GRAPH),))[GRAPH] == (FAILED, agent_checks.NOT_ONE_GRAPH)


@pytest.mark.needs_db
def test_a_trace_that_names_no_ending_fails_the_trace_check(
    head: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the request step recorded as still going, the run has no ending the page will draw,
    and the check says so. Delete this and the check could pass a trace the page refuses as
    unfinished."""
    from types import SimpleNamespace

    monkeypatch.setattr(
        "brain.ops.trace_store.status_of_finished",
        lambda request: SimpleNamespace(value="in_flight"),
    )

    assert run_checks(head, (by_name(GRAPH),))[GRAPH] == (FAILED, agent_checks.NO_ENDING)
