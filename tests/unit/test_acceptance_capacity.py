"""The capacity acceptance checks: registered, passing on a real schema, and able to fail.

The database half builds PostgreSQL to head and runs the first check as the worker would: it
passes, leaves `ops.setting` and the ledger as they were, and leaves what the process holds as it
was. Then it is run against a product broken three ways, each the way it would break in practice:
bounds that refuse nothing, a reload that reads nothing, and budgets that ignore what was saved.
Each is a failed check with its own sentence. The cache half is not run without a cache, with its
own sentence, which is how the worker records it; the cache run is inside the application's
container, where the window check in `brain.ops.acceptance_checks` runs too.

Task ids: M22.1.2, M22.4.1
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from brain.ops import acceptance_checks_capacity as capacity
from brain.ops import tuning
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, Check, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, counts

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_capacity"

LEAVES = {
    "budgets_and_windows_are_rows_saved_within_bounds_and_audited": ("M22.1.2", "M22.4.1"),
    "the_rate_limits_screen_lists_the_windows_refusing_now": ("M22.4.1",),
}

#: Pinned far from any wall clock, for CLAUDE.md's reason about fixtures with dates in them.
LONG_AGO = datetime(2019, 3, 6, 9, 0, tzinfo=UTC)


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_capacity_checks_are_registered_with_the_leaves_they_prove() -> None:
    """Each check names its leaves, and each is a leaf of the work breakdown. Delete this and a
    check can close a leaf it does not exercise, or name an id no task has."""
    assert {name: one.leaves for name, one in mine().items()} == LEAVES
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    assert {leaf for one in LEAVES.values() for leaf in one} <= leaves


def test_the_check_restates_the_route_s_authority_rather_than_importing_it() -> None:
    """`CHANGES_LIMITS` is held against the route's own constant from outside the check. Delete
    this and the route could move to another authority with the check asking the old one."""
    from brain.settings_routes import INSTALL_SETTING_AUTHORITY

    assert INSTALL_SETTING_AUTHORITY.value == capacity.CHANGES_LIMITS


def run_checks(
    url: str, checks: Sequence[Check], env: dict[str, str]
) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url
    from brain.ops.acceptance_run import run_suite
    from brain.session import make_app_engine

    async def run() -> Any:
        engine = make_app_engine(normalise_database_url(url))
        try:
            return await run_suite(
                engine,
                checks,
                settings=settings_from({"BRAIN_DATABASE_URL": url, **env}),
                stream=sys.stderr,
            )
        finally:
            await engine.dispose()

    return {one.name: (one.outcome, one.reason) for one in asyncio.run(run())}


def settings_rows(url: str) -> int:
    from tests.fixtures.scratch_postgres import sql

    return int(sql(url, "SELECT count(*) FROM ops.setting")[0][0])


def saved_check() -> Check:
    return mine()["budgets_and_windows_are_rows_saved_within_bounds_and_audited"]


@pytest.mark.needs_db
def test_on_a_real_database_the_capacity_checks_pass_or_say_why_not_and_leave_nothing_behind() -> (
    None
):
    """**The checks as the worker runs them, against PostgreSQL at head, with no cache.** The rows
    check passes; the cache check is not run with its own sentence; `ops.setting`, the ledger and
    what this process holds are as they were. Delete this and a check that cannot pass on the
    real schema, or one that commits a saved limit to a client's install, reaches the owner's
    server first."""
    held = dict(tuning.held())
    with at_head("brain_acceptance_capacity") as url:
        before = (counts(url), settings_rows(url))
        outcomes = run_checks(url, tuple(mine().values()), {})
        after = (counts(url), settings_rows(url))

    assert outcomes == {
        "budgets_and_windows_are_rows_saved_within_bounds_and_audited": (PASSED, ""),
        "the_rate_limits_screen_lists_the_windows_refusing_now": (
            NOT_RUN,
            capacity.NO_CACHE_TO_ASK,
        ),
    }
    assert after == before
    assert dict(tuning.held()) == held


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("bounds", "a value outside the product's bounds was not refused"),
        ("reload", "the reload every process runs did not read back what was saved"),
        ("budgets", "the budgets admission reads did not carry the saved row"),
    ],
)
def test_the_rows_check_fails_when_the_product_is_broken_where_it_proves(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Three breaks, each one line of the product: bounds that admit anything, a reload that
    reads an empty namespace, and budgets that never lay a saved row over the seed. Each fails the
    check with its own sentence. Delete this and the check can pass with the property it names
    gone."""
    import brain.ops.install_settings as install_settings

    if broken == "bounds":
        monkeypatch.setattr(tuning, "problem", lambda name, raw: "")
    elif broken == "reload":

        async def nothing(session: Any) -> dict[str, int]:
            del session
            return {}

        monkeypatch.setattr(install_settings, "load_tuned", nothing)
    else:
        monkeypatch.setattr(tuning, "configured_budgets", lambda saved=None: tuning.seed_budgets())
    with at_head(f"brain_acceptance_capacity_{broken}") as url:
        outcome = run_checks(url, (saved_check(),), {})
    assert outcome[saved_check().name] == (FAILED, reason)


# --------------------------------------------------------------------------- the cache half
class HeldCache:
    """`tests.unit.test_limit_store.FakeClient`, which answers the window store's statements as
    Valkey does, with the key removal the harness's undoing calls."""

    def __init__(self) -> None:
        from tests.unit.test_limit_store import FakeClient

        self.client = FakeClient()

    def __getattr__(self, name: str) -> Any:
        return getattr(self.client, name)

    def delete(self, *names: str) -> int:
        gone = 0
        for one in names:
            gone += self.client.sets.pop(one, None) is not None
            gone += self.client.counters.pop(one, None) is not None
        return gone


def window_check() -> Check:
    return mine()["the_rate_limits_screen_lists_the_windows_refusing_now"]


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("broken", "outcome"),
    [
        ("", (PASSED, "")),
        ("unlisted", (FAILED, "the screen's reading did not list the window refusing now")),
        ("unnarrowed", (FAILED, "a reader of one department was shown a window refusing now")),
    ],
)
def test_the_window_check_passes_over_a_cache_and_fails_when_the_screen_misreads_it(
    monkeypatch: pytest.MonkeyPatch, broken: str, outcome: tuple[str, str]
) -> None:
    """**The cache check over a cache that answers as Valkey does, and every key it wrote gone
    afterwards.** Then with the screen's reading broken two ways: listing nothing, and ignoring
    the reader's grant. Delete this and the check can pass over a screen that never lists a
    refusing window, or one that lists it to a department's reader, and leave the check's own
    windows in the install's cache."""
    import brain.cache as cache
    import brain.console.installation as installation

    held = HeldCache()
    monkeypatch.setattr(cache, "make_client", lambda url: held)
    original = installation.throttled_now
    if broken == "unlisted":
        monkeypatch.setattr(installation, "throttled_now", lambda *a, **k: ())
    elif broken == "unnarrowed":

        def everyone(limits: Any, state: Any, reader: Any, *, now: datetime) -> Any:
            del reader
            from brain.core.entitlement import Capability, EntitlementSet, Grant
            from brain.core.scope import Scope

            wide = EntitlementSet(
                principal_id="u_everywhere",
                grants=(
                    Grant(
                        capability=Capability(value=capacity.READS_LIMITS),
                        scope=Scope.unrestricted(),
                    ),
                ),
            )
            return original(limits, state, wide, now=now)

        monkeypatch.setattr(installation, "throttled_now", everyone)
    env = {"BRAIN_VALKEY_URL": "redis://cache.invalid:6379/0"}
    with at_head(f"brain_acceptance_capacity_cache{broken}") as url:
        found = run_checks(url, (window_check(),), env)
    assert found[window_check().name] == outcome
    assert held.client.sets == {}
    assert held.client.counters == {}
