"""The Laravel database's acceptance check: registered, passing on a real schema, and able to fail.

The database half builds PostgreSQL to head and runs the check as the worker would: a Laravel
connection made up for the run is connected, read through the executor over a recorded driver, and
asked about through the answer route's own functions, and every table the check writes holds
afterwards what it held before. Then it is run against the product broken where it proves: the
database contributing no question shapes, a live read that is never made, and a classification
that hands the contract value to a reader not granted it. Each fails with its own sentence.

Task ids: M11.6.1, M11.7.7, M11.1.4
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from brain.ops.acceptance import (
    FAILED,
    NOT_RUN,
    PASSED,
    REASON_CHARS,
    SENTENCE_CHARS,
    Check,
    registered,
)
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_laravel"
NAME = "a_laravel_database_answers_on_ask_from_its_views"

#: Every table the check writes to, which must hold afterwards what it held before.
WRITTEN = ("proj.record", "ops.connector_connection", "ops.connector_sync")


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_laravel_check_is_registered_with_the_leaves_it_proves() -> None:
    """Delete this and the check can close a leaf it does not exercise, or name an id no task
    has."""
    assert {name: one.leaves for name, one in mine().items()} == {
        NAME: ("M11.6.1", "M11.7.7", "M11.1.4")
    }
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    assert set(mine()[NAME].leaves) <= leaves


def test_the_laravel_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them, held in this
    module's own file so no package edits a list every package appends to. Delete this and a check
    can drop out of the module with the page simply listing one fewer row."""
    assert checks_in(MODULE) == [NAME]


def test_the_check_s_sentence_and_every_reason_it_can_give_fit_the_page() -> None:
    """The sentence fits the Install page's column and every reason is a literal that fits the
    result's, read from the module's parsed source so a reason assembled from a value is refused
    too. Delete this and a reason can carry a client's name or be cut off mid-word on the page."""
    import ast
    import inspect

    import brain.ops.acceptance_checks_laravel as module

    assert len(mine()[NAME].sentence) <= SENTENCE_CHARS
    reasons = []
    for node in ast.walk(ast.parse(inspect.getsource(module))):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") in {
            "CheckFailedError",
            "CheckNotRunError",
        }:
            [argument] = node.args
            if isinstance(argument, ast.Name):
                argument_value = getattr(module, argument.id)
            else:
                assert isinstance(argument, ast.Constant), ast.dump(argument)
                argument_value = argument.value
            reasons.append(argument_value)
    assert len(reasons) >= 10
    assert all(isinstance(one, str) and 0 < len(one) <= REASON_CHARS for one in reasons)


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
def test_on_a_real_database_the_laravel_database_answers_and_nothing_is_left_behind() -> None:
    """**The check as the worker runs it, against PostgreSQL at head.** It passes, and the
    projection, the connections, the attempts and the ledger hold what they held before. Delete
    this and the path from a company's own database to Ask can break with nothing on the owner's
    install saying so, or a check that commits a connection can reach his server."""
    with at_head("brain_acceptance_laravel") as url:
        before = (counts(url), written(url))
        outcome = run_checks(url, tuple(mine().values()))
        after = (counts(url), written(url))
    assert outcome == {NAME: (PASSED, "")}
    assert after == before


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("questions", "the connected database contributed no question shapes to Ask"),
        ("live", "a client's contract value was not read live for a reader granted it"),
        ("withheld", "a client's contract value was told to a reader not granted it"),
        ("allowlist", "a view off the connection's allowlist was planned for reading"),
    ],
)
def test_the_laravel_check_fails_where_the_path_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Four breaks, one per property: no question shapes for the connected database, a live
    reader that never reads, the contract value classified under the row's own capability, and a
    transport that plans a read of any view it is handed (M11.1.4). Each fails the check with its
    own sentence. Delete this and the check can pass with the
    property gone."""
    import brain.api_routes as api_routes
    import brain.ops.live_records as live_records
    import brain.tools.startup as startup

    if broken == "questions":

        async def none(state: Any) -> Any:
            del state
            return ()

        monkeypatch.setattr(api_routes, "connected_questions_of", none)
    elif broken == "live":

        async def never(self: Any, result: Any, **kwargs: Any) -> Any:
            del self, result, kwargs
            return None

        monkeypatch.setattr(live_records.SourceRecords, "refresh", never)
    elif broken == "allowlist":
        from brain.connectors.transports import DatabaseTransport, ViewRead

        def anything(self: Any, view: str, *, filters: Any = (), limit: int = 0) -> ViewRead:
            del self
            return ViewRead(view=view, filters=filters, limit=limit)

        monkeypatch.setattr(DatabaseTransport, "plan", anything)
    else:
        from dataclasses import replace

        from brain.core.entitlement import Capability

        opened = {
            source: tuple(
                replace(
                    one,
                    rules=tuple(
                        replace(rule, required_capability=Capability(value=f"read:{one.entity}"))
                        if rule.column == "contract_value"
                        else rule
                        for rule in one.rules
                    ),
                )
                for one in classifications
            )
            for source, classifications in startup.SOURCE_ROW_ENTITIES.items()
        }
        monkeypatch.setattr(startup, "SOURCE_ROW_ENTITIES", opened)
    with at_head(f"brain_acceptance_laravel_{broken}") as url:
        before = written(url)
        outcome = run_checks(url, (mine()[NAME],))
        after = written(url)
    assert outcome[NAME] == (FAILED, reason)
    assert after == before


@pytest.mark.needs_db
def test_the_laravel_check_steps_aside_where_the_install_has_the_database_connected() -> None:
    """`LARAVEL_IS_CONNECTED_HERE_ALREADY`. Delete this and the check could move the owner's real
    connection aside, or fail on an install whose Laravel database is connected."""
    from brain.ops.acceptance_checks_laravel import LARAVEL_IS_CONNECTED_HERE_ALREADY
    from tests.fixtures.scratch_postgres import sql

    with at_head("brain_acceptance_laravel_connected") as url:
        sql(
            url,
            "INSERT INTO ops.connector_connection (connector, settings, digest, connected_by)"
            " VALUES ('laravel', '{}'::jsonb, %s, 'u_admin')",
            "0" * 64,
        )
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (NOT_RUN, LARAVEL_IS_CONNECTED_HERE_ALREADY)
