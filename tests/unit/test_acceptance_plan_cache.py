"""The plan-cache and freshness install checks: registered, passing on PostgreSQL, able to fail.

No cache runs here, so each check is run once with the process given no cache's address, where it
says it was not run, and then with a dictionary standing where the install's cache stands, where it
passes and every table it writes holds what it held before. Then the product is broken one part at
a time (a plan that keeps more than tool ids, a projection that keeps everything, a reading that
is never kept, one that never moves an answer's key) and each check fails with its own sentence.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M6.2.2, M6.2.5
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops import acceptance_checks_plan_cache as module
from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in

MODULE = "brain.ops.acceptance_checks_plan_cache"
PLAN = "a_plan_is_kept_as_tool_ids_and_replayed_through_a_projection"
FRESH = "a_source_epoch_is_read_through_the_cache_and_moves_the_key"

WRITTEN = (
    "proj.source_epoch",
    "auth.principal",
    "gate.capability_grant",
    "gate.department",
    "obs.audit_entry",
)


class Memory:
    """A record cache in a dictionary, remembering the lifetime each key was given."""

    def __init__(self) -> None:
        self.held: dict[str, Any] = {}
        self.lifetimes: dict[str, int] = {}

    def get(self, key: str) -> Any:
        return self.held.get(key)

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        self.held[key] = value
        self.lifetimes[key] = ttl_seconds


def in_memory(*, forget_to_keep: bool = False) -> Any:
    """`caches_of` over dictionaries. `forget_to_keep` is a cache that keeps nothing."""
    plans, epochs = Memory(), Memory()
    if forget_to_keep:
        epochs.set = lambda key, value, ttl_seconds: None  # type: ignore[method-assign]

    def caches_of(_: Any) -> Any:
        return module.Caches(
            plans=module.KeptKeys(plans),
            epochs=module.KeptKeys(epochs),
            lifetime=lambda key: epochs.lifetimes.get(key, -2),
            drop=lambda key: epochs.held.pop(key, None) and None,
        )

    return caches_of


def test_the_module_declares_each_check_naming_the_leaf_it_proves() -> None:
    """Each check names its own leaf and no other. Delete this and a check can lose its leaf with
    the Install page showing the same row, or close a leaf it does not prove."""
    assert {one.name: one.leaves for one in registered((MODULE,))} == {
        PLAN: ("M6.2.2",),
        FRESH: ("M6.2.5",),
    }
    assert checks_in(MODULE) == [PLAN, FRESH]
    assert 880 <= module.CHECK_ORDER <= 899


def test_the_plan_leaf_stays_held_while_no_request_path_stores_a_plan() -> None:
    """M6.2.2 is in the proof sweep's holds, with the reason. Delete this and the leaf closes on a
    pass over the cache's own parts while nothing in a request stores a plan."""
    import json

    from tests.unit.test_acceptance import ROOT

    held = json.loads((ROOT / "docs" / "proof-sweep-holds.json").read_text(encoding="utf-8"))
    assert "M6.2.2" in held["held"]
    assert "plan" in held["held"]["M6.2.2"]


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_plan_cache") as url:
        yield url


def run_mine(url: str) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url

    settings = settings_from({"BRAIN_DATABASE_URL": url})
    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings,
            commit="abc1234",
            checks=list(registered((MODULE,))),
            force=True,
        )
    )
    return {one.name: (one.outcome, one.reason) for one in results}


def held(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    return {one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0]) for one in WRITTEN}  # noqa: S608


@pytest.mark.needs_db
def test_both_checks_say_they_were_not_run_where_no_cache_is_given(install: str) -> None:
    """With the process given no cache address, each says so in the module's own sentence rather
    than passing on nothing. Delete this and an install with no cache shows these as passed."""
    assert run_mine(install) == {
        PLAN: (NOT_RUN, module.NO_CACHE_ADDRESS),
        FRESH: (NOT_RUN, module.NO_CACHE_ADDRESS),
    }


@pytest.mark.needs_db
def test_both_checks_pass_over_a_cache_and_leave_nothing(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**The checks as the worker runs them, with a store standing where the cache stands.** Both
    pass and the tables they wrote hold what they held. Delete this and a check that can never pass
    on a real schema, or one that commits, reaches the owner's server."""
    monkeypatch.setattr(module, "caches_of", in_memory())
    before = held(install)
    assert run_mine(install) == {PLAN: (PASSED, ""), FRESH: (PASSED, "")}
    assert held(install) == before


@pytest.mark.needs_db
def test_a_plan_that_keeps_more_than_tool_ids_fails_the_plan_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The plan type given a field for a description. Delete this and the check closes M6.2.2 on a
    plan that stores what a model was told, which is the sentence that teaches a capability."""
    import dataclasses

    from brain.gate import caches

    monkeypatch.setattr(module, "caches_of", in_memory())
    original = caches.CachedPlan
    widened = dataclasses.make_dataclass(
        "CachedPlan",
        [("description", str, dataclasses.field(default=""))],
        bases=(original,),
        frozen=True,
    )
    monkeypatch.setattr(caches, "CachedPlan", widened)
    [(outcome, reason)] = [run_mine(install)[PLAN]]
    assert outcome == FAILED
    assert "other than tool ids" in reason


@pytest.mark.needs_db
def test_a_replay_that_ignores_the_reusers_projection_fails_the_plan_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A replay giving back the stored list whoever asks. Delete this and the check closes M6.2.2
    on a cache that hands one caller's tools to a caller who cannot reach them."""
    from brain.gate import caches

    monkeypatch.setattr(module, "caches_of", in_memory())
    monkeypatch.setattr(
        caches, "replay", lambda plan, catalogue: caches.ReplayedPlan(tool_ids=plan.tool_ids)
    )
    outcome, reason = run_mine(install)[PLAN]
    assert outcome == FAILED
    assert "lacking one tool" in reason


@pytest.mark.needs_db
def test_a_cache_that_never_keeps_the_reading_fails_the_freshness_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A store that drops every write, so each read goes back to the database. Delete this and the
    check closes M6.2.5 on a cache that saves nothing."""
    monkeypatch.setattr(module, "caches_of", in_memory(forget_to_keep=True))
    outcome, reason = run_mine(install)[FRESH]
    assert outcome == FAILED
    assert "lifetime" in reason or "read from the database again" in reason


@pytest.mark.needs_db
def test_an_answer_key_that_ignores_the_source_epochs_fails_the_freshness_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The answer key built without the epochs it is given. Delete this and the check closes M6.2.5
    on a key that a changed source never moves, so a stale answer is served after the change."""
    from brain.gate import caches

    monkeypatch.setattr(module, "caches_of", in_memory())
    original = caches.answer_key

    def blind(question: str, caller: Any, **kwargs: Any) -> str:
        return original(question, caller, **{**kwargs, "source_epochs": {}})

    monkeypatch.setattr(caches, "answer_key", blind)
    outcome, reason = run_mine(install)[FRESH]
    assert outcome == FAILED
    assert "answer key did not change" in reason
