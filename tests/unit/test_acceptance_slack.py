"""The Slack acceptance check: registered, passing on a real schema, and able to fail.

The database half builds PostgreSQL to head and runs the check as the worker would, then runs it
against the product broken where it proves: membership no longer asked of Slack, so every
channel is read for every member; an asker matched to a Slack account they do not have; and a
member's address kept in the index. Each fails with its own sentence, and every table the check
writes holds afterwards what it held before.

Task ids: M11.7.5
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, Check, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_slack"
NAME = "a_slack_message_is_read_only_for_a_member_of_its_channel"

#: Every table the check writes to, which must hold afterwards what it held before.
WRITTEN = (
    "proj.record",
    "ops.connector_connection",
    "ops.connector_sync",
    "auth.principal_identity",
)


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_slack_check_is_registered_with_the_leaf_it_proves() -> None:
    """Delete this and the check can close a leaf it does not exercise, or name an id no task
    has."""
    assert {name: one.leaves for name, one in mine().items()} == {NAME: ("M11.7.5",)}
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    assert set(mine()[NAME].leaves) <= leaves


def test_the_slack_messages_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them. Held here
    since 2026-09-30, so a package adding a check edits its own file and never a list every
    package appends to. Delete this and a check can drop out of the module with the page simply
    listing one fewer row."""
    assert checks_in("brain.ops.acceptance_checks_slack") == [
        "a_slack_message_is_read_only_for_a_member_of_its_channel",
    ]


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
def test_on_a_real_database_a_slack_message_is_read_for_its_members_and_nothing_is_left() -> None:
    """**The check as the worker runs it, against PostgreSQL at head.** It passes, and the index,
    the connections, the attempts, the bindings and the ledger hold what they held before. Delete
    this and a private channel could be read for a person not in it with nothing on the owner's
    install saying so, or a check that commits a connection can reach his server."""
    with at_head("brain_acceptance_slack") as url:
        before = (counts(url), written(url))
        outcome = run_checks(url, tuple(mine().values()))
        after = (counts(url), written(url))
    assert outcome == {NAME: (PASSED, "")}
    assert after == before


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("membership", "a private channel's message was read for somebody not in it"),
        (
            "account",
            "Slack was read for a person with no account in it, no grant or another department",
        ),
        ("address", "a Slack member's address was kept in a table"),
    ],
)
def test_the_slack_check_fails_where_the_path_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Three breaks, one per property: membership no longer asked of Slack, so a member is read
    every channel the index lists; an asker whose address Slack does not know matched to a member
    the index holds; and a member's address kept in the index beside its digest, as a label. Each
    fails the check with its own sentence. Delete this and the check can pass with the property
    gone."""
    import brain.connectors.slack_messages as slack
    import brain.ops.slack_messages_live as slack_live

    if broken == "membership":

        class _Everything(frozenset[str]):
            def __contains__(self, item: object) -> bool:
                return True

        monkeypatch.setattr(
            slack_live.SlackPassages, "_membership", lambda self, *args: _Everything()
        )
    elif broken == "account":
        own = slack_live.asker_digests

        async def any_member(sessions: Any, principal_id: str) -> tuple[str, ...]:
            # Their own address where Slack knows it; where it does not, whoever the index holds.
            mine = await own(sessions, principal_id)
            indexed = await slack_live.indexed(sessions, slack.MEMBER)
            everyone = tuple(str(fields.get("identity_hash")) for _, fields in indexed)
            return mine if set(mine) & set(everyone) else everyone

        monkeypatch.setattr(slack_live, "asker_digests", any_member)
    else:
        projected = slack.SlackReading.projected

        def keeping_the_address(self: Any, entity: str, row: Any, *, seen_at: Any) -> Any:
            kept = projected(self, entity, row, seen_at=seen_at)
            if kept is None or entity != slack.MEMBER:
                return kept
            return replace(kept, source_id=str(row.get("email")))

        monkeypatch.setattr(slack.SlackReading, "projected", keeping_the_address)
    with at_head(f"brain_acceptance_slack_{broken}") as url:
        before = written(url)
        outcome = run_checks(url, (mine()[NAME],))
        after = written(url)
    assert outcome[NAME] == (FAILED, reason)
    assert after == before


@pytest.mark.needs_db
def test_the_slack_check_steps_aside_where_the_install_has_slack_connected() -> None:
    """`SLACK_IS_CONNECTED_HERE_ALREADY`. Delete this and the check could move the owner's own
    connection aside, or fail on an install whose Slack is connected."""
    from brain.ops.acceptance_checks_slack import SLACK_IS_CONNECTED_HERE_ALREADY
    from tests.fixtures.scratch_postgres import sql

    with at_head("brain_acceptance_slack_connected") as url:
        sql(
            url,
            "INSERT INTO ops.connector_connection (connector, settings, digest, connected_by)"
            " VALUES ('slack_messages', '{}'::jsonb, %s, 'u_admin')",
            "0" * 64,
        )
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (NOT_RUN, SLACK_IS_CONNECTED_HERE_ALREADY)
