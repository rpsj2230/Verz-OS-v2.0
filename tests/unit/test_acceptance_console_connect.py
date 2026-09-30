"""The console-connect acceptance check: registered, passing on a real schema, and able to fail.

The database half builds PostgreSQL to head and runs the check as the worker would, then runs it
against the product broken where it proves: a source only the server could connect, a credential
shape the route no longer judges, an edit the store does not keep, and a disconnection that leaves
the source live. Each fails with its own sentence, and every table the check writes holds
afterwards what it held before.

Task ids: M11.7.7
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
MODULE = "brain.ops.acceptance_checks_console_connect"
NAME = "each_source_is_connected_edited_and_switched_off_in_the_console"

#: Every table the check writes to, which must hold afterwards what it held before.
WRITTEN = ("ops.connector_connection", "gate.role_grant")


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_console_connect_check_is_registered_with_the_leaf_it_proves() -> None:
    """Delete this and the check can close a leaf it does not exercise, or name an id no task
    has."""
    assert {name: one.leaves for name, one in mine().items()} == {NAME: ("M11.7.7",)}
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    assert set(mine()[NAME].leaves) <= leaves


def test_the_console_connect_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them. Held here
    since 2026-09-30, so a package adding a check edits its own file and never a list every
    package appends to. Delete this and a check can drop out of the module with the page simply
    listing one fewer row."""
    assert checks_in("brain.ops.acceptance_checks_console_connect") == [
        "each_source_is_connected_edited_and_switched_off_in_the_console",
    ]


def test_every_source_the_console_connects_has_an_edit_and_a_wrong_shape() -> None:
    """Held against the product's own list rather than the check's. Delete this and a source added
    to the console is walked by nothing, or a credential shape added has no refusal tried."""
    from brain.connectors.declaration import CredentialShape
    from brain.ops.acceptance_checks_console_connect import EDITS, WRONG_SHAPE
    from brain.ops.connectable import CONNECTABLE, DECLARED_FORMS

    assert set(CONNECTABLE) <= set(EDITS) <= set(DECLARED_FORMS)
    assert set(WRONG_SHAPE) == {one.value for one in CredentialShape}


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
def test_on_a_real_database_every_source_is_connected_edited_and_switched_off() -> None:
    """**The check as the worker runs it, against PostgreSQL at head.** It passes, and the
    connections, the grants and the ledger hold what they held before. Delete this and a source can
    fall back to being connected at the server with nothing on the owner's install saying so, or a
    check that commits a connection can reach his server."""
    with at_head("brain_acceptance_console_connect") as url:
        before = (counts(url), written(url))
        outcome = run_checks(url, tuple(mine().values()))
        after = (counts(url), written(url))
    assert outcome == {NAME: (PASSED, "")}
    assert after == before


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("server", "a source other than Lark's can only be connected at the server"),
        ("shape", "a credential in the wrong shape was not refused as the key"),
        ("edit", "an edited source was not live with the settings it was given"),
        ("off", "a source switched off was still live"),
        ("person", "a setting naming nobody here was not refused"),
    ],
)
def test_the_console_connect_check_fails_where_the_path_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Five breaks, one per property: Laravel sent back to the server, every credential passed
    whatever its shape, an edit the store drops, a disconnection that disconnects nothing, and a
    person setting nobody checks. Each fails the check with its own sentence. Delete this and the
    check can pass with the property gone."""
    import brain.ops.connectable as connectable
    import brain.ops.connector_admin as connector_admin
    import brain.ops.connector_store as connector_store
    from brain.connectors.declaration import CredentialShape

    if broken == "server":
        moved = dict(connectable.NOT_FROM_THE_CONSOLE)
        moved["laravel"] = connectable.NotConnectable(name="laravel", label="Laravel", why="x")
        monkeypatch.setattr(connectable, "NOT_FROM_THE_CONSOLE", moved)
    elif broken == "shape":

        def lenient(shape: Any, value: str) -> tuple[Any, ...]:
            del shape, value
            return ()

        monkeypatch.setattr(connector_admin, "credential_problems", lenient)
        assert CredentialShape.KEY_FILE.value == "key_file"
    elif broken == "edit":

        async def unchanged(self: Any, **kwargs: Any) -> Any:
            del self, kwargs
            return None

        monkeypatch.setattr(connector_store.StoredConnections, "reconnect", unchanged)
    elif broken == "off":

        async def nothing(self: Any, connector: str, **kwargs: Any) -> Any:
            del self, connector, kwargs
            return None

        monkeypatch.setattr(connector_store.StoredConnections, "disconnect", nothing)
    else:

        async def unchecked(kind: Any, settings: Any, *, is_live: Any) -> tuple[Any, ...]:
            del kind, settings, is_live
            return ()

        monkeypatch.setattr(connector_admin, "people_problems", unchecked)
    with at_head(f"brain_acceptance_console_connect_{broken}") as url:
        before = written(url)
        outcome = run_checks(url, (mine()[NAME],))
        after = written(url)
    assert outcome[NAME] == (FAILED, reason)
    assert after == before


@pytest.mark.needs_db
def test_a_source_the_install_connected_is_judged_and_never_touched() -> None:
    """`A_CONNECTED_SOURCE_IS_JUDGED_ONLY`. Delete this and the check could move the owner's own
    connection aside, or fail on an install whose Xero is connected."""
    from tests.fixtures.scratch_postgres import sql

    with at_head("brain_acceptance_console_connect_connected") as url:
        sql(
            url,
            "INSERT INTO ops.connector_connection (connector, settings, digest, connected_by)"
            " VALUES ('xero', '{}'::jsonb, %s, 'u_admin')",
            "0" * 64,
        )
        before = written(url)
        outcome = run_checks(url, (mine()[NAME],))
        after = written(url)
    assert outcome[NAME] == (PASSED, "")
    assert after == before
