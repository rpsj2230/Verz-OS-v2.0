"""The record caches' checks: not run without a cache, passing with one standing where the install's
stands, and failing with the product broken.

No Valkey runs here, so each check is run once with the process given no cache's address, where it
says it was not run, and then with an in-memory client standing where the install's client stands.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M6.2.3, M6.2.4
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from typing import Any, Final

import pytest

from brain.ops import acceptance_checks_record_caches as module
from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE: Final = "brain.ops.acceptance_checks_record_caches"
RETRIEVAL: Final = "a_cached_retrieval_is_served_only_to_the_reach_it_was_ranked_for"
EMBEDDING: Final = "an_embedding_is_kept_under_its_content_and_model_alone"


class Held:
    """The synchronous client the record caches are given, in memory, with the two calls the
    check's cleanup makes."""

    def __init__(self) -> None:
        self.held: dict[str, bytes] = {}

    def get(self, name: str) -> bytes | None:
        return self.held.get(name)

    def setex(self, name: str, time: int, value: bytes) -> object:
        assert time >= 1
        self.held[name] = value
        return True

    def ping(self) -> object:
        return True

    def delete(self, *names: str) -> int:
        return sum(self.held.pop(one, None) is not None for one in names)

    def close(self) -> None:
        return None


def test_each_check_names_the_leaf_it_proves() -> None:
    """Two checks, each closing its own leaf. Delete this and a check can lose a leaf with the page
    showing the same row, or start closing a leaf it does not prove (not M6.2.5, which waits)."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (RETRIEVAL, ("M6.2.3",)),
        (EMBEDDING, ("M6.2.4",)),
    ]
    assert checks_in(MODULE) == [RETRIEVAL, EMBEDDING]
    assert 800 <= module.CHECK_ORDER <= 899


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_record_caches") as url:
        yield url


def run_checks(url: str, *names: str, valkey: bool = True) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url

    env = {"BRAIN_DATABASE_URL": url}
    if valkey:
        env["BRAIN_VALKEY_URL"] = "redis://localhost:1"
    settings = settings_from(env)
    checks = [one for one in registered((MODULE,)) if not names or one.name in names]
    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings,
            commit="abc1234",
            checks=checks,
            force=True,
        )
    )
    return {one.name: (one.outcome, one.reason) for one in results}


@pytest.fixture
def a_cache_stands_here(monkeypatch: pytest.MonkeyPatch) -> Held:
    held = Held()
    monkeypatch.setattr("brain.cache.make_client", lambda url, **kwargs: held)
    return held


@pytest.mark.needs_db
def test_without_a_cache_each_check_says_it_was_not_run(install: str) -> None:
    """The process holds no cache address. Delete this and an install with no cache reads as
    failing, or as passing, the two caches."""
    assert run_checks(install, valkey=False) == {
        RETRIEVAL: (NOT_RUN, module.NO_CACHE),
        EMBEDDING: (NOT_RUN, module.NO_CACHE),
    }


@pytest.mark.needs_db
def test_with_a_cache_both_checks_pass_and_leave_nothing(
    install: str, a_cache_stands_here: Held
) -> None:
    """**The checks as the worker runs them**, with a cache standing where the install's does. Both
    pass, every table they write holds what it held, and the cache holds nothing the check wrote
    once it has ended. Delete this and a check that can never pass on a real schema, or one that
    leaves its keys behind, reaches the owner's server."""
    before = counts(install)
    assert run_checks(install) == {RETRIEVAL: (PASSED, ""), EMBEDDING: (PASSED, "")}
    assert counts(install) == before
    assert a_cache_stands_here.held == {}


def _never_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    class Nothing:
        def get(self, key: str) -> None:
            return None

        def set(self, key: str, value: Any, ttl_seconds: int) -> None:
            return None

    monkeypatch.setattr("brain.cache.retrieval_cache", lambda client, health=None: Nothing())


def _one_key_for_everybody(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain.knowledge import document_tools

    monkeypatch.setattr(document_tools, "retrieval_key", lambda *args, **kwargs: "ret:one")


def _no_corpus_epoch(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain.knowledge import document_tools

    monkeypatch.setattr(document_tools, "corpus_epoch_of", lambda row: 0)


def _no_model_in_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    import hashlib

    from brain.gate import caches

    monkeypatch.setattr(
        caches,
        "embedding_key",
        lambda content, *, model: "emb:" + hashlib.sha256(content.encode()).hexdigest(),
    )


BREAKS: Final[dict[str, tuple[Callable[[pytest.MonkeyPatch], None], str, str]]] = {
    "never_kept": (_never_kept, RETRIEVAL, "NOT_SERVED_FROM_THE_CACHE"),
    "one_key_for_everybody": (_one_key_for_everybody, RETRIEVAL, "SERVED_ACROSS_REACH"),
    "no_corpus_epoch": (_no_corpus_epoch, RETRIEVAL, "STALE_AFTER_A_CHANGE"),
    "no_model_in_the_key": (_no_model_in_the_key, EMBEDDING, "THE_KEY_DID_NOT_MOVE"),
}


@pytest.mark.needs_db
@pytest.mark.parametrize("broken", sorted(BREAKS))
def test_each_check_fails_where_the_product_is_broken(
    install: str, a_cache_stands_here: Held, monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    """Four breaks, each failing with its own sentence: a ranking never kept, one key for every
    reach, a key with no corpus epoch in it, and an embedding key that ignores its model. Delete
    this and either check can pass with any of those properties gone."""
    setup, name, reason = BREAKS[broken]
    setup(monkeypatch)
    assert run_checks(install, name) == {name: (FAILED, getattr(module, reason))}
