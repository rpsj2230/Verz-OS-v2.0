"""The answer cache's install acceptance check: registered, passing on PostgreSQL, able to fail.

The pure half holds the check to its leaf and to the work breakdown. The database half builds
PostgreSQL to head once for the module and runs the check as the worker would. No cache runs here,
so the check is run once with the process given no cache's address, where it says it was not run,
and then with an in-memory store standing where the install's cache stands, where it passes and
every table it writes to holds, row for row, what it held before. Then the property it proves is
broken, one part at a time, and it fails with its own sentence.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M6.5.2
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Iterator, Sequence
from typing import Any

import pytest

from brain.gate.cache_key import CachedAnswer
from brain.ops import acceptance_checks_cache as cache
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, Check, check_modules, registered
from tests.unit.test_acceptance import ROOT, WRITTEN_BY_CHECKS, at_head, checks_in

MODULE = "brain.ops.acceptance_checks_cache"
NAME = "a_cached_answer_reaches_only_the_reach_it_was_computed_for"

#: Every table the cache check writes to, which must hold afterwards exactly what it held before.
WRITTEN_BY_CACHE_CHECKS = (
    "gate.department",
    "gate.scope",
    "auth.principal",
    "gate.capability_grant",
    "gate.grants_version",
    "gate.policy_epoch",
    "obs.audit_entry",
    "know.classified_table",
    "know.classified_row",
    "gate.fast_path_rule",
    "obs.request_telemetry",
)


class Held:
    """An answer store in memory, standing where the install's cache stands."""

    def __init__(self) -> None:
        self.held: dict[str, CachedAnswer] = {}

    def get(self, key: str) -> CachedAnswer | None:
        return self.held.get(key)

    def set(self, key: str, value: CachedAnswer, ttl_seconds: int) -> None:
        del ttl_seconds
        self.held[key] = value


def mine() -> tuple[Check, ...]:
    return registered((MODULE,))


# ------------------------------------------------------------------------ without a server
def test_the_cache_check_proves_its_leaf_and_nothing_else() -> None:
    """Delete this and the check can close a leaf it does not exercise, or fall out of the run."""
    assert {check.name: check.leaves for check in mine()} == {NAME: ("M6.5.2",)}
    assert MODULE in check_modules()


def test_the_cache_checks_leaf_is_a_leaf_of_the_work_breakdown() -> None:
    """WBS ids are positional. Delete this and a result can close the wrong leaf."""
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {leaf for module in wbs["modules"] for leaf in module["leaf_ids"]}
    assert {leaf for check in mine() for leaf in check.leaves} <= leaves


def test_every_table_the_cache_check_writes_is_one_the_suite_measures() -> None:
    """Delete this and a table the check writes can be left out of the suite's count."""
    assert set(WRITTEN_BY_CACHE_CHECKS) <= set(WRITTEN_BY_CHECKS)


def test_the_store_the_check_uses_keeps_every_key_it_writes_so_each_is_removed() -> None:
    """Delete this and a key the check stored in the install's cache could be left there."""
    from datetime import UTC, datetime

    kept = cache.KeptKeys(Held())
    answer = CachedAnswer(
        key="k1", payload="p", stored_at=datetime(2999, 1, 1, tzinfo=UTC), source_epochs={}
    )
    kept.set("k1", answer, 60)
    kept.set("k2", answer, 60)
    assert kept.keys == ["k1", "k2"]
    assert kept.get("k1") == answer and kept.get("missing") is None


def test_the_cache_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them, held here
    beside the module's other tests so a package adding a check edits its own file and never a
    list every package appends to. Delete this and a check can drop out of the module with the
    page simply listing one fewer row."""
    assert checks_in(MODULE) == [
        "a_cached_answer_reaches_only_the_reach_it_was_computed_for",
    ]


# --------------------------------------------------------------------------- a real run
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

    return {result.name: (result.outcome, result.reason) for result in asyncio.run(run())}


@pytest.fixture(scope="module")
def database() -> Iterator[str]:
    """One database at head for the module: every check rolls back, so they can share it."""
    with at_head("brain_acceptance_cache") as url:
        yield url


def contents(url: str) -> dict[str, tuple[int, str]]:
    """Every row of every table the checks write to, as a count and a digest of the rows."""
    from tests.fixtures.scratch_postgres import sql

    held: dict[str, tuple[int, str]] = {}
    for table in WRITTEN_BY_CACHE_CHECKS:
        # The names are this module's constants, never input.
        [(count, digest)] = sql(
            url,
            f"SELECT count(*), coalesce(md5(string_agg(t::text, ',' ORDER BY t::text)), '')"  # noqa: S608
            f" FROM {table} t",
        )
        held[table] = (int(count), str(digest))
    return held


@pytest.fixture
def held(monkeypatch: pytest.MonkeyPatch) -> Held:
    """The in-memory store, handed to the check where the install's cache would be."""
    store = Held()
    monkeypatch.setattr(cache, "answer_store_for", lambda h: cache.KeptKeys(store))
    return store


@pytest.mark.needs_db
def test_with_no_cache_address_the_check_says_it_was_not_run(database: str) -> None:
    """Delete this and a worker given no cache address records a failure the install did not
    cause, or a pass it did not earn."""
    outcome, reason = run_checks(database, mine())[NAME]
    assert outcome == NOT_RUN
    assert reason.startswith("the worker running this check was not given the cache address")


@pytest.mark.needs_db
def test_on_a_real_database_the_cache_check_passes_and_leaves_nothing_behind(
    database: str, held: Held
) -> None:
    """**The check as the worker runs it, against PostgreSQL at head, with a store where the
    cache stands.** It passes, it stored answers, and every table it wrote to holds row for row what
    it held before. Delete this and a check that cannot pass on the real schema reaches the
    owner's server first."""
    before = contents(database)
    outcomes = run_checks(database, mine())
    after = contents(database)

    assert outcomes == {NAME: (PASSED, "")}
    assert held.held
    assert after == before


@pytest.mark.needs_db
def test_the_check_fails_when_the_cache_key_forgets_the_askers_reach(
    database: str, held: Held, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A key without the reach serves one person's answer to another. Delete this and the check
    can pass on an install whose cache does exactly that."""
    from brain.gate import cache_key

    kept = cache_key.cache_key

    def reachless(parts: Any) -> str:
        from dataclasses import replace

        return kept(replace(parts, ent_hash="x" * 32))

    monkeypatch.setattr(cache_key, "cache_key", reachless)

    assert run_checks(database, mine())[NAME] == (
        FAILED,
        "a colleague without the price grant was served the answer cached for somebody with it",
    )


@pytest.mark.needs_db
def test_the_check_fails_when_an_upload_does_not_move_the_key(
    database: str, held: Held, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A key with no upload in it is the defect this package fixed. Delete this and the check can
    pass on an install that serves the old price after a new upload."""
    from brain import api_routes

    kept = api_routes.caching_of

    def epochless(state: Any, policies: Any, sources: Any, epochs: Any = None) -> Any:
        del epochs
        return kept(state, policies, sources, {})

    monkeypatch.setattr(api_routes, "caching_of", epochless)

    assert run_checks(database, mine())[NAME] == (
        FAILED,
        "a price list uploaded again was answered from the old upload's cache",
    )
