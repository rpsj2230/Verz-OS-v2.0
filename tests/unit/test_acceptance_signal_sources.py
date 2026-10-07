"""The contradiction check, passing on PostgreSQL at head and failing with the product broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M16.2.3
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from typing import Any, Final

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import INSTALL, at_head, checks_in, counts

MODULE: Final = "brain.ops.acceptance_checks_signal_sources"
NAME: Final = "a_follow_up_saying_the_answer_was_wrong_is_a_signal_about_it"

#: What these checks write beyond the suite's list.
ALSO_WRITTEN: Final = ("chat.conversation", "chat.message")


def test_the_check_names_the_leaf_it_proves() -> None:
    """One check, one leaf. Delete this and the check can lose its leaf with the page showing the
    same row, or start closing a leaf it does not prove."""
    from brain.ops import acceptance_checks_signal_sources as module

    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [(NAME, ("M16.2.3",))]
    assert checks_in(MODULE) == [NAME]
    assert 800 <= module.CHECK_ORDER <= 899


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_signal_sources") as url:
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


def _counts(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    both = counts(url)
    # The names are this module's constants, never input.
    both.update(
        {one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0]) for one in ALSO_WRITTEN}  # noqa: S608
    )
    return both


@pytest.mark.needs_db
def test_the_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The check as the worker runs it.** It passes and nothing it wrote is left, signals and
    threads included. Delete this and a check that can never pass on a real schema, or one that
    commits a person's signals, reaches the owner's server."""
    before = _counts(install)
    assert run_check(install) == {NAME: (PASSED, "")}
    assert _counts(install) == before


def _never_noticed(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain.chat import thread_store

    monkeypatch.setattr(thread_store, "is_contradiction", lambda *args, **kwargs: False)


def _every_follow_up_contradicts(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain.chat import thread_store

    monkeypatch.setattr(thread_store, "is_contradiction", lambda *args, **kwargs: True)


def _the_words_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    """A writer that keeps the follow-up's last word as the signal's trace, as a hurried 'so we
    can tell what was said' would: the planted word fits the trace grammar."""
    from brain.chat import thread_store
    from brain.ops.signal_store import noticed as original

    said: list[str] = []
    real = thread_store._contradicted

    async def remembering(session: Any, held: Any, question: str) -> Any:
        said.append(question)
        return await real(session, held, question)

    async def copying(session: Any, observation: Any, *, trace_id: str | None) -> bool:
        words = said[-1].split() if said else []
        return await original(session, observation, trace_id=words[-1] if words else trace_id)

    monkeypatch.setattr(thread_store, "_contradicted", remembering)
    monkeypatch.setattr(thread_store, "noticed", copying)


BREAKS: Final[dict[str, tuple[Callable[[pytest.MonkeyPatch], None], str]]] = {
    "never_noticed": (_never_noticed, "NO_CONTRADICTION_KEPT"),
    "every_follow_up_contradicts": (_every_follow_up_contradicts, "A_PLAIN_FOLLOW_UP_WAS_ONE"),
    "words_kept": (_the_words_kept, "THE_FOLLOW_UP_WAS_KEPT"),
}


@pytest.mark.needs_db
@pytest.mark.parametrize("broken", sorted(BREAKS))
def test_the_check_fails_where_the_product_is_broken(
    install: str, monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    """Three breaks, each failing with its own sentence: a correction in words never noticed,
    every follow-up taken for one, and the follow-up's words kept in the signal. Delete this and
    the check can pass with any of those properties gone."""
    import brain.ops.acceptance_checks_signal_sources as module

    setup, reason = BREAKS[broken]
    setup(monkeypatch)
    assert run_check(install) == {NAME: (FAILED, getattr(module, reason))}
