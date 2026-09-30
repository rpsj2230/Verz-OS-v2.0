"""The HubSpot acceptance check: registered, passing on a real schema, and able to fail.

The database half builds PostgreSQL to head and runs the check as the worker would, then runs it
against the product broken where it proves: HubSpot's records classified for nothing, so no
question reaches them, and the live lookup naming no one-record read, so a deal's amount is never
read. Each fails with its own sentence, and every table the check writes holds afterwards what it
held before.

Task ids: M11.9.2, M11.6.5
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, Check, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_hubspot"
NAME = "a_hubspot_deal_is_answered_on_ask_and_its_amount_read_live"

#: Every table the check writes to, which must hold afterwards what it held before.
WRITTEN = ("proj.record", "ops.connector_connection", "ops.connector_sync")


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_hubspot_check_is_registered_with_the_leaves_it_proves() -> None:
    """Delete this and the check can close a leaf it does not exercise, or name an id no task
    has."""
    assert {name: one.leaves for name, one in mine().items()} == {NAME: ("M11.9.2", "M11.6.5")}
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    assert set(mine()[NAME].leaves) <= leaves


def test_the_hubspot_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them. Delete this
    and a check can drop out of the module with the page simply listing one fewer row."""
    assert checks_in(MODULE) == [NAME]


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
def test_on_a_real_database_a_hubspot_deal_is_answered_and_nothing_is_left() -> None:
    """**The check as the worker runs it, against PostgreSQL at head.** It passes, and the index,
    the connections, the attempts and the ledger hold what they held before. Delete this and
    HubSpot can be offered, read and never answer a question with nothing on the owner's install
    saying so."""
    with at_head("brain_acceptance_hubspot") as url:
        before = (counts(url), written(url))
        outcome = run_checks(url, tuple(mine().values()))
        after = (counts(url), written(url))
    assert outcome == {NAME: (PASSED, "")}
    assert after == before


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("classified", "a connected HubSpot account contributed no question shape to Ask"),
        ("live", "a connected HubSpot company was not answered on Ask by its name"),
    ],
)
def test_the_hubspot_check_fails_where_the_path_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Two breaks, one per half: HubSpot's records classified for nothing, which is where HubSpot
    stood before 2026-09-30, and the live lookup naming no one-record read, so no value is read
    from HubSpot and the first question, a company's stage, is not answered. Each fails the check with its own sentence. Delete this and
    the check can pass with either half gone."""
    import brain.connectors.hubspot as hubspot
    import brain.knowledge.connector_rows as connector_rows

    if broken == "classified":
        kept = {k: v for k, v in connector_rows.CONNECTOR_ROW_ENTITIES.items() if k != "hubspot"}
        monkeypatch.setattr(connector_rows, "CONNECTOR_ROW_ENTITIES", kept)
    else:
        monkeypatch.setattr(hubspot.HubSpotLiveLookup, "operation", lambda self, *a, **k: None)
    with at_head(f"brain_acceptance_hubspot_{broken}") as url:
        before = written(url)
        outcome = run_checks(url, (mine()[NAME],))
        after = written(url)
    assert outcome[NAME] == (FAILED, reason)
    assert after == before


@pytest.mark.needs_db
def test_the_hubspot_check_steps_aside_where_the_install_has_hubspot_connected() -> None:
    """`HUBSPOT_IS_CONNECTED_HERE_ALREADY`. Delete this and the check could move the owner's own
    connection aside, or fail on an install whose HubSpot is connected."""
    from brain.ops.acceptance_checks_hubspot import HUBSPOT_IS_CONNECTED_HERE_ALREADY
    from tests.fixtures.scratch_postgres import sql

    with at_head("brain_acceptance_hubspot_connected") as url:
        sql(
            url,
            "INSERT INTO ops.connector_connection (connector, settings, digest, connected_by)"
            " VALUES ('hubspot', '{}'::jsonb, %s, 'u_admin')",
            "0" * 64,
        )
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (NOT_RUN, HUBSPOT_IS_CONNECTED_HERE_ALREADY)
