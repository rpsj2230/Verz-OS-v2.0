"""Search Console's acceptance check: registered, placed, passing on a real schema, able to fail.

The database half builds PostgreSQL to head and runs the check as the worker would: a Search
Console site made up for the run is connected, its name read by the worker from the account's site
list with a token its key file bought, and asked about on Ask and through its figure tool, and every
table the check writes holds afterwards what it held before. Then it is run against the product
broken where it proves: a token exchange that names a person, a figure that is never read live, the
site told to a reader without it, the account's site list kept whole rather than the connected site
alone, and the figure tool's range dropped. Each fails with its own sentence.

Task ids: M11.7.2
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from brain.core.scope import Scope
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, Check, registered
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_sources import run_checks, written

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_search_console"
NAME = "a_search_console_site_answers_its_figures_live_and_keeps_none"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_search_console_check_is_registered_with_the_leaf_it_proves() -> None:
    """Delete this and the check can close a leaf it does not exercise, or name an id no task
    has."""
    assert {name: one.leaves for name, one in mine().items()} == {NAME: ("M11.7.2",)}
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    assert set(mine()[NAME].leaves) <= leaves


def test_the_search_console_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them: one check,
    a Search Console site connected, indexed and asked live, placed after Google Analytics'. Held
    here, beside the module's other tests, so a package adding a check edits its own file and never
    a list every package appends to. Delete this and a check can drop out of the module with the
    page simply listing one fewer row, or Search Console's can be listed before Analytics'."""
    from brain.ops import acceptance
    from brain.ops.acceptance_checks_google import CHECK_ORDER as ANALYTICS
    from brain.ops.acceptance_checks_search_console import CHECK_ORDER

    assert checks_in(MODULE) == [NAME]
    assert CHECK_ORDER > ANALYTICS
    modules = acceptance.check_modules()
    assert modules.index(MODULE) > modules.index("brain.ops.acceptance_checks_google")


@pytest.mark.needs_db
def test_on_a_real_database_a_site_answers_its_figures_live_and_nothing_is_left_behind() -> None:
    """**The check as the worker runs it, against PostgreSQL at head.** It passes, and the
    projection, the connections, the attempts and the ledger hold what they held before. Delete
    this and the path from a connected site to its clicks on Ask and through the figure tool can
    break with nothing on the owner's install saying so, or a check that commits a connection can
    reach his server."""
    with at_head("brain_acceptance_search_console") as url:
        before = (counts(url), written(url))
        outcome = run_checks(url, tuple(mine().values()))
        after = (counts(url), written(url))
    assert outcome == {NAME: (PASSED, "")}
    assert after == before


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("subject", "the worker's read was not one token for the account and no call"),
        ("live", "a connected site's clicks were not told to a reader granted them"),
        ("reach", "a site's figure was told to a reader not granted it"),
        ("every_site", "the worker did not keep the connected site alone from its list"),
        ("range", "the site's figure tool did not ask for the range it was given"),
    ],
)
def test_the_search_console_check_fails_where_the_path_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Five breaks, one per property: the account made to act as a person, a live reader that never
    reads, the site's department rule moved to the other department, the site list kept whole
    rather than the connected site alone, and the figure tool's range dropped. Each fails the check
    with its own sentence; the kept figure is the Analytics check's break, over the same search.
    Delete this and the check can pass with the property gone."""
    import brain.connectors.google_service_account as google_service_account
    import brain.connectors.search_console as search_console
    import brain.ops.live_records as live_records

    if broken == "subject":
        signed = google_service_account.signed_assertion

        def as_a_person(**kwargs: Any) -> str:
            return signed(**{**kwargs, "subject": "someone@example.com"})

        monkeypatch.setattr("brain.connectors.google_token.signed_assertion", as_a_person)
    elif broken == "live":

        async def never(self: Any, result: Any, **kwargs: Any) -> Any:
            del self, result, kwargs
            return None

        monkeypatch.setattr(live_records.SourceRecords, "refresh", never)
    elif broken == "reach":
        monkeypatch.setattr(
            search_console.SearchConsoleConnection,
            "visibility",
            lambda self: Scope.department("acceptance_b"),
        )
    elif broken == "range":
        # The tool's range dropped on the way, and the last 28 days asked for instead.
        from brain.connectors.date_range import RangeRequest, window_of

        monkeypatch.setattr(
            RangeRequest, "window", lambda self, *, today: window_of("last 28 days", today=today)
        )
    else:
        # Every site on the account's list kept, the connected one and any other.
        def every_site(operation: Any, body: Any, *, fetched_at: str) -> Any:
            return operation.records(body, fetched_at=fetched_at)

        monkeypatch.setattr(search_console, "connected_rows", every_site)
    with at_head(f"brain_acceptance_search_{broken}") as url:
        before = written(url)
        outcome = run_checks(url, (mine()[NAME],))
        after = written(url)
    assert outcome[NAME] == (FAILED, reason)
    assert after == before


@pytest.mark.needs_db
def test_the_search_console_check_steps_aside_where_the_install_has_the_site_connected() -> None:
    """`A_CONNECTED_SOURCE_IS_NOT_CONNECTED_AGAIN`. Delete this and the check could move the
    owner's real connection aside, or fail on an install whose Search Console is connected."""
    from brain.ops.acceptance_checks_search_console import SEARCH_CONSOLE_IS_CONNECTED_HERE_ALREADY
    from tests.fixtures.scratch_postgres import sql

    with at_head("brain_acceptance_search_connected") as url:
        sql(
            url,
            "INSERT INTO ops.connector_connection (connector, settings, digest, connected_by)"
            " VALUES ('search_console', '{}'::jsonb, %s, 'u_admin')",
            "0" * 64,
        )
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (NOT_RUN, SEARCH_CONSOLE_IS_CONNECTED_HERE_ALREADY)
