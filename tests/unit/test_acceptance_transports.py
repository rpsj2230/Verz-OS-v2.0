"""The MCP and custom-code transport checks: registered, passing on a real schema, able to fail.

The database half builds PostgreSQL to head and runs both checks as the worker would, then runs
each against the product broken where it proves. For MCP: a session that never checks a tool
against its pin, so a redefined tool is called; and a live read that ignores the declared
one-record tool. For custom code: a connectable list that offers a custom-code source with no
runner, and a host that hands the key to the code. Each fails with its own sentence, and every
table the checks write holds afterwards what it held before.

Task ids: M11.1.2, M11.1.5
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, Check, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_transports"
MCP = "an_mcp_server_is_read_into_the_index_and_one_record_live"
CODE = "a_custom_code_source_is_read_only_through_a_sandbox_runner"

#: Every table the checks write to, which must hold afterwards what it held before.
WRITTEN = ("proj.record", "ops.connector_connection", "ops.connector_sync")


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_transport_checks_are_registered_with_the_leaves_they_prove() -> None:
    """Delete this and a check can close a leaf it does not exercise, or name an id no task
    has."""
    assert {name: one.leaves for name, one in mine().items()} == {
        MCP: ("M11.1.2",),
        CODE: ("M11.1.5",),
    }
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    assert {leaf for one in mine().values() for leaf in one.leaves} <= leaves


def test_the_transport_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them. Delete this
    and a check can drop out of the module with the page simply listing one fewer row."""
    assert checks_in(MODULE) == [MCP, CODE]


def test_the_custom_code_check_says_the_sandbox_is_not_what_it_proves() -> None:
    """The check runs a stand-in runner, so its sentence must say the sandbox itself is not
    proved by it. Delete this and the Install page can read as a proof of isolation that no
    process on the install has given."""
    sentence = mine()[CODE].sentence
    assert "sandbox itself is the deploy work's optional service" in sentence
    assert "not proved here" in sentence


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


def written(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    # The names are this module's constants, never input.
    return {one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0]) for one in WRITTEN}  # noqa: S608


@pytest.mark.needs_db
def test_on_a_real_database_both_transports_are_read_and_nothing_is_left() -> None:
    """**Both checks as the worker runs them, against PostgreSQL at head.** They pass, and the
    index, the connections, the attempts and the ledger hold what they held before. Delete this
    and either transport can stop reading a source, or start keeping what it read live, with
    nothing on the owner's install saying so."""
    with at_head("brain_acceptance_transports") as url:
        before = (counts(url), written(url))
        outcome = run_checks(url, tuple(mine().values()))
        after = (counts(url), written(url))
    assert outcome == {MCP: (PASSED, ""), CODE: (PASSED, "")}
    assert after == before


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("name", "broken", "reason"),
    [
        (MCP, "pin", "a server that redefined a declared tool was still called"),
        (MCP, "one_tool", "a live read did not call the declared one-record tool for the id"),
        (CODE, "offered", "a custom-code source was offered on an install with no runner"),
        (CODE, "key", "the key was in something the custom code was handed"),
    ],
)
def test_each_transport_check_fails_where_its_path_is_broken(
    monkeypatch: pytest.MonkeyPatch, name: str, broken: str, reason: str
) -> None:
    """Four breaks, two per check. The session no longer checks a tool against its pin; a live
    read calls the list tool rather than the declared one-record tool; the console's reading
    test no longer asks for a runner; and the host's check that the key is in no spec is gone
    while the key rides in the environment it builds. Each fails its check with its own
    sentence. Delete this and either check can pass with its half of the transport gone."""
    import brain.connectors.mcp as mcp
    import brain.ops.connectable as connectable
    import brain.ops.custom_code_run as custom_code_run
    import brain.ops.mcp_session as mcp_session
    from brain.ops import acceptance_checks_transports as transports

    if broken == "pin":
        monkeypatch.setattr(mcp_session, "assert_as_reviewed", lambda pinned, listed: None)
    elif broken == "one_tool":
        listing = transports.MCP_READING.reads[0]

        def the_list_tool(self: Any, entity: str, source_id: str | None) -> Any:
            del self, entity
            narrowed = {} if source_id is None else {listing.id_argument: source_id}
            return listing.tool, {**listing.arguments, **narrowed}

        monkeypatch.setattr(mcp.McpReading, "tool_call", the_list_tool)
    elif broken == "offered":
        original = connectable.reads

        def careless(declaration: Any, *, runner: Any = None) -> bool:
            del runner
            return original(declaration, runner=object())  # type: ignore[arg-type]

        monkeypatch.setattr(connectable, "reads", careless)
    else:
        original_run = custom_code_run.run_code

        def leaky(runner: Any, spec: Any, *, secret: str) -> str:
            from dataclasses import replace

            return original_run(runner, replace(spec, environment={"TZ": secret}), secret="")

        monkeypatch.setattr(custom_code_run, "run_code", leaky)
    with at_head(f"brain_acceptance_transports_{broken}") as url:
        before = written(url)
        outcome = run_checks(url, (mine()[name],))
        after = written(url)
    assert outcome[name] == (FAILED, reason)
    assert after == before
