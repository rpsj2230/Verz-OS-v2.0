"""The session memory check: not run without a cache, passing with one standing where the install's
stands, and failing with the product broken.

No Valkey runs here, so the check is run once with the process given no cache's address, where it
says it was not run, and then with an in-memory client standing where the install's client stands.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M16.1.1, M16.3.1
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from typing import Any, Final

import pytest

from brain.ops import acceptance_checks_session as module
from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import INSTALL, at_head, checks_in, counts

MODULE: Final = "brain.ops.acceptance_checks_session"
NAME: Final = "session_memory_is_one_conversations_own_and_silent"

#: What the check writes beyond the suite's list.
ALSO_WRITTEN: Final = ("chat.conversation", "chat.message")


class Held:
    """The async client the session store is given, in memory, standing where the cache stands."""

    def __init__(self) -> None:
        self.held: dict[str, bytes] = {}

    async def get(self, name: str) -> bytes | None:
        return self.held.get(name)

    async def setex(self, name: str, time: int, value: bytes) -> object:
        assert time >= 1
        self.held[name] = value
        return True

    async def ping(self) -> object:
        return True


def test_the_check_names_the_leaves_it_proves() -> None:
    """One check, two leaves. Delete this and the check can lose a leaf with the page showing the
    same row, or start closing a leaf it does not prove."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (NAME, ("M16.1.1", "M16.3.1"))
    ]
    assert checks_in(MODULE) == [NAME]
    assert 800 <= module.CHECK_ORDER <= 899


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_session") as url:
        yield url


@pytest.fixture(autouse=True)
def an_issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


def run_check(url: str) -> dict[str, tuple[str, str]]:
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


def _a_cache_stands_here(monkeypatch: pytest.MonkeyPatch) -> Held:
    held = Held()
    monkeypatch.setattr(module, "session_client", lambda h: module.KeptKeys(held))
    return held


def _counts(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    both = counts(url)
    # The names are this module's constants, never input.
    both.update(
        {one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0]) for one in ALSO_WRITTEN}  # noqa: S608
    )
    return both


@pytest.mark.needs_db
def test_without_a_cache_the_check_says_it_was_not_run(install: str) -> None:
    """The process holds no cache address, so there is nothing to keep a conversation's notes in.
    Delete this and an install with no cache reads as failing, or as passing, session memory."""
    [(outcome, reason)] = run_check(install).values()
    assert (outcome, reason) == (NOT_RUN, module.NO_CACHE)


@pytest.mark.needs_db
def test_with_a_cache_the_check_passes_and_leaves_nothing_in_the_database(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**The check as the worker runs it**, with a cache standing where the install's does. It
    passes and every table it writes holds what it held before. Delete this and a check that can
    never pass on a real schema reaches the owner's server."""
    held = _a_cache_stands_here(monkeypatch)
    before = _counts(install)
    assert run_check(install) == {NAME: (PASSED, "")}
    assert _counts(install) == before
    assert held.held, "the check kept nothing in the cache, so it proved nothing"


def _nothing_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain.ops.session_memory_store import StoredSessions

    async def nothing(self: Any, thread_id: str, principal_id: str, said: Any, *, now: Any) -> None:
        return None

    monkeypatch.setattr(StoredSessions, "remember", nothing)


def _one_key_for_everybody(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain.ops import session_memory_store

    monkeypatch.setattr(session_memory_store, "session_key", lambda thread, person: "one-key")


def _never_bound_to_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain import api_routes

    monkeypatch.setattr(api_routes, "with_session", lambda state, lane, **kwargs: lane)


BREAKS: Final[dict[str, tuple[Callable[[pytest.MonkeyPatch], None], str]]] = {
    "nothing_kept": (_nothing_kept, "NOT_KEPT_IN_THE_CACHE"),
    "one_key_for_everybody": (_one_key_for_everybody, "SHOWN_ELSEWHERE"),
    "never_bound_to_the_model": (_never_bound_to_the_model, "NOT_SHOWN_ON_THE_NEXT_TURN"),
}


@pytest.mark.needs_db
@pytest.mark.parametrize("broken", sorted(BREAKS))
def test_the_check_fails_where_the_product_is_broken(
    install: str, monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    """Three breaks, each failing with its own sentence: nothing kept, one key for every person and
    conversation, and a memory kept and never shown to the model. Delete this and the check can
    pass with any of those properties gone."""
    _a_cache_stands_here(monkeypatch)
    setup, reason = BREAKS[broken]
    setup(monkeypatch)
    assert run_check(install) == {NAME: (FAILED, getattr(module, reason))}
