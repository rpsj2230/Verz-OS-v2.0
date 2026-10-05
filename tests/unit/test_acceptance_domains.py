"""The domains acceptance check: registered, passing on a real schema, and able to fail.

The database half builds PostgreSQL to head and runs the check as the worker would, then runs it
against the product broken where it proves: a registry asked for a domain nobody listed, a domain
whose registry publishes no RDAP answered as an outage, and a live read that no longer asks the
site. Each fails with its own sentence, and every table the check writes holds afterwards what it
held before.

Task ids: M11.7.4
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
MODULE = "brain.ops.acceptance_checks_domains"
NAME = "a_domain_s_expiry_comes_from_its_registry_and_no_other_is_asked"

#: Every table the check writes to, which must hold afterwards what it held before.
WRITTEN = ("proj.record", "ops.connector_connection", "ops.connector_sync")


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_domains_check_is_registered_with_the_leaf_it_proves() -> None:
    """Delete this and the check can close a leaf it does not exercise, or name an id no task
    has."""
    assert {name: one.leaves for name, one in mine().items()} == {NAME: ("M11.7.4",)}
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    assert set(mine()[NAME].leaves) <= leaves


def test_the_domains_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them. Held here
    since 2026-09-30, so a package adding a check edits its own file and never a list every
    package appends to. Delete this and a check can drop out of the module with the page simply
    listing one fewer row."""
    assert checks_in("brain.ops.acceptance_checks_domains") == [
        "a_domain_s_expiry_comes_from_its_registry_and_no_other_is_asked",
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
def test_on_a_real_database_a_domain_is_answered_from_its_registry_and_nothing_is_left() -> None:
    """**The check as the worker runs it, against PostgreSQL at head.** It passes, and the index,
    the connections, the attempts and the ledger hold what they held before. Delete this and an
    expiry question can fall back to whatever the index last held with nothing on the owner's
    install saying so, or a check that commits a connection can reach his server."""
    with at_head("brain_acceptance_domains") as url:
        before = (counts(url), written(url))
        outcome = run_checks(url, tuple(mine().values()))
        after = (counts(url), written(url))
    assert outcome == {NAME: (PASSED, "")}
    assert after == before


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("unlisted", "a domain nobody listed was looked up"),
        ("unpublished", "a domain no registry publishes was not said to be unpublished"),
        ("site", "a listed domain's site was not asked whether it answers"),
    ],
)
def test_the_domains_check_fails_where_the_path_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Three breaks, one per property: the listed-only guard gone, so an unlisted domain is looked
    up and answered; a registry that publishes no RDAP answered with no record, as an outage is;
    and the live read's site check taken away. Each fails the check with its own sentence. Delete
    this and the check can pass with the property gone."""
    import brain.connectors.domains as domains

    if broken == "unlisted":
        monkeypatch.setattr(domains.DomainsConnection, "listed", lambda self, domain: True)
    elif broken == "unpublished":
        monkeypatch.setattr(
            domains.DomainsReading, "unpublished", lambda self, *args, **kwargs: None
        )
    else:
        monkeypatch.setattr(domains.DomainsLiveLookup, "facts", lambda self, *args, **kwargs: {})
    with at_head(f"brain_acceptance_domains_{broken}") as url:
        before = written(url)
        outcome = run_checks(url, (mine()[NAME],))
        after = written(url)
    assert outcome[NAME] == (FAILED, reason)
    assert after == before


@pytest.mark.needs_db
def test_the_domains_check_steps_aside_where_the_install_has_its_domains_connected() -> None:
    """`DOMAINS_ARE_CONNECTED_HERE_ALREADY`. Delete this and the check could move the owner's
    own connection aside, or fail on an install whose domains are connected."""
    from brain.ops.acceptance_checks_domains import DOMAINS_ARE_CONNECTED_HERE_ALREADY
    from tests.fixtures.scratch_postgres import sql

    with at_head("brain_acceptance_domains_connected") as url:
        sql(
            url,
            "INSERT INTO ops.connector_connection (connector, settings, digest, connected_by)"
            " VALUES ('domains', '{}'::jsonb, %s, 'u_admin')",
            "0" * 64,
        )
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (NOT_RUN, DOMAINS_ARE_CONNECTED_HERE_ALREADY)
