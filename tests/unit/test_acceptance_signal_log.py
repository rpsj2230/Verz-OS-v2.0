"""The signal log's install checks: registered, passing on PostgreSQL at head, and able to fail.

The pure half holds the two checks to their leaves and their page order. The database half runs
them as the worker would, with the stand-in model the answer checks use, and both pass and leave
nothing behind. Then each property a check proves is broken the way it would plausibly break,
one at a time, in the product's code or in the install's own policies, and the check fails with
the sentence written for that property.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M16.2.8, M9.2.4, M15.3.4
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from typing import Any, Final

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, check_modules, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import INSTALL, at_head, checks_in, counts
from tests.unit.test_acceptance_models import Providers

MODULE: Final = "brain.ops.acceptance_checks_signal_log"
LOGGED: Final = "a_reask_and_a_correction_are_logged_by_id_and_never_in_words"
RETRIEVED: Final = "a_retrieval_is_logged_at_its_trace_as_the_passages_shown"

#: What these checks write beyond the suite's list.
ALSO_WRITTEN: Final = ("chat.conversation", "chat.message", "gate.escalation")


def test_the_signal_log_checks_are_listed_with_their_leaves_in_page_order() -> None:
    """Two checks, each closing its own leaves, found by the suite. Delete this and a check can
    lose a leaf, or drop off the Install page, with the page simply listing one fewer row."""
    assert MODULE in check_modules()
    assert checks_in(MODULE) == [LOGGED, RETRIEVED]
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (LOGGED, ("M16.2.8", "M9.2.4")),
        (RETRIEVED, ("M15.3.4", "M16.2.8")),
    ]


# --------------------------------------------------------------------- on an install
@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_signal_log") as url:
        yield url


@pytest.fixture
def vaulted(monkeypatch: pytest.MonkeyPatch) -> Providers:
    """The hosted profile with keys and providers answering in the process, as
    `tests/unit/test_acceptance_answers.py` sets them, so the stand-in is planned."""
    from tests.unit.test_acceptance_answers import vault_the_providers

    return vault_the_providers(monkeypatch)


@pytest.fixture
def issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


def run_checks(url: str, *names: str) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url

    settings = settings_from({"BRAIN_DATABASE_URL": url})
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


def _counts(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    both = counts(url)
    # The names are this module's constants, never input.
    both.update(
        {one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0]) for one in ALSO_WRITTEN}  # noqa: S608
    )
    return both


@pytest.mark.needs_db
def test_both_checks_pass_on_an_install_and_leave_nothing(
    install: str, issuer: None, vaulted: Providers
) -> None:
    """**The module as the worker runs it.** Both pass, nothing a check wrote is left (the
    signals, the retrievals, the threads and the handoff included), and no provider of the
    product is asked. Delete this and a check that can never pass on a real schema, or one that
    commits a person's signals, reaches the owner's server first."""
    before = _counts(install)
    outcomes = run_checks(install)
    assert outcomes == {LOGGED: (PASSED, ""), RETRIEVED: (PASSED, "")}
    assert _counts(install) == before
    assert vaulted.sent == []


# ------------------------------------------------------------------------ the breaks
def _no_reask(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain.chat import thread_store

    monkeypatch.setattr(thread_store, "is_reask", lambda *args, **kwargs: False)


def _every_question_a_reask(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain.chat import thread_store

    monkeypatch.setattr(thread_store, "is_reask", lambda *args, **kwargs: True)


def _correction_feeds_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain.chat import thread_store

    async def nothing(*args: Any) -> None:
        return None

    monkeypatch.setattr(thread_store, "_answer_at", nothing)


def _the_question_copied_into_the_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    """A writer that keeps the earlier question's last word as the trace, as a hurried 'so we
    can tell which question it was' would: the planted word fits the trace grammar."""
    from brain.chat import thread_store
    from brain.memory.signals import is_reask
    from brain.ops.signal_store import noticed as original

    said: list[str] = []

    def remembering(earlier: str, later: str, **kwargs: Any) -> bool:
        said.append(earlier)
        return is_reask(earlier, later, **kwargs)

    async def copying(session: Any, observation: Any, *, trace_id: str | None) -> bool:
        words = said[-1].split() if said else []
        return await original(session, observation, trace_id=words[-1] if words else trace_id)

    monkeypatch.setattr(thread_store, "is_reask", remembering)
    monkeypatch.setattr(thread_store, "noticed", copying)


def _counted_per_person(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain.ops import signal_store

    def anything(observations: Any, field: str) -> dict[str, int]:
        found: dict[str, int] = {}
        for one in observations:
            key = str(getattr(one, field))
            found[key] = found.get(key, 0) + 1
        return found

    monkeypatch.setattr(signal_store, "counts_by", anything)


def _no_retrieval(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain import api_routes

    monkeypatch.setattr(api_routes, "logging_retrievals", lambda lane, kept: lane)


def _handoff_kept_as_an_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    import dataclasses

    from brain.chat import remember

    original = remember.exchange_of

    def plain(*args: Any) -> Any:
        found = original(*args)
        return None if found is None else dataclasses.replace(found, escalated=False)

    monkeypatch.setattr(remember, "exchange_of", plain)


#: Each break in the product's code, the check it is run against, and the reason it must give.
BREAKS: Final[dict[str, tuple[Callable[[pytest.MonkeyPatch], None], str, str]]] = {
    "no_reask": (_no_reask, LOGGED, "NO_REASK_KEPT"),
    "every_question_a_reask": (
        _every_question_a_reask,
        LOGGED,
        "AN_UNRELATED_QUESTION_WAS_A_REASK",
    ),
    "correction_feeds_nothing": (_correction_feeds_nothing, LOGGED, "NO_CORRECTION_KEPT"),
    "question_copied": (_the_question_copied_into_the_signal, LOGGED, "WORDS_IN_A_SIGNAL"),
    "counted_per_person": (_counted_per_person, LOGGED, "COUNTED_BY_PERSON"),
    "no_retrieval": (_no_retrieval, RETRIEVED, "NO_RETRIEVAL_KEPT"),
    "handoff_kept_as_an_answer": (_handoff_kept_as_an_answer, RETRIEVED, "NO_ESCALATION_KEPT"),
}


@pytest.mark.needs_db
@pytest.mark.parametrize("broken", sorted(BREAKS))
def test_each_check_fails_where_the_product_is_broken(
    install: str,
    issuer: None,
    vaulted: Providers,
    monkeypatch: pytest.MonkeyPatch,
    broken: str,
) -> None:
    """One break per property, each failing its check with its own sentence: no re-ask kept,
    every follow-up kept as one, a correction that feeds nothing, the question's words copied
    into a signal, signals counted per person, no retrieval kept, and a handoff kept as an
    ordinary answer. Delete this and the checks can pass with any of those properties gone."""
    import brain.ops.acceptance_checks_signal_log as module

    setup, name, reason = BREAKS[broken]
    setup(monkeypatch)
    assert run_checks(install, name) == {name: (FAILED, getattr(module, reason))}


#: Each break in the install's own policies: the statement that breaks it, the one that puts it
#: back, the check, and the reason it must give.
POLICY_BREAKS: Final[dict[str, tuple[str, str, str, str]]] = {
    "signals_read_by_anybody": (
        "ALTER POLICY signal_read_by_its_person ON mem.signal USING (true)",
        "ALTER POLICY signal_read_by_its_person ON mem.signal"
        " USING (principal_id = current_setting('app.principal_id', true))",
        LOGGED,
        "ANOTHER_PERSON_REACHED_A_SIGNAL",
    ),
    "signals_written_in_anybodys_name": (
        "ALTER POLICY signal_noticed_in_the_sessions_name ON mem.signal WITH CHECK (true)",
        "ALTER POLICY signal_noticed_in_the_sessions_name ON mem.signal"
        " WITH CHECK (principal_id = current_setting('app.principal_id', true))",
        LOGGED,
        "ANOTHER_PERSON_REACHED_A_SIGNAL",
    ),
    "retrievals_read_by_anybody": (
        "ALTER POLICY retrieval_read_by_its_person ON mem.retrieval USING (true)",
        "ALTER POLICY retrieval_read_by_its_person ON mem.retrieval"
        " USING (principal_id = current_setting('app.principal_id', true))",
        RETRIEVED,
        "A_RETRIEVAL_WAS_READ_BY_ANOTHER",
    ),
}


@pytest.mark.needs_db
@pytest.mark.parametrize("broken", sorted(POLICY_BREAKS))
def test_each_check_fails_where_the_installs_policy_is_broken(
    install: str, issuer: None, vaulted: Providers, broken: str
) -> None:
    """The per-person policies `0197` writes, each opened on the install for one run and put
    back: anybody reading a person's signals, anybody writing one in their name, and anybody
    reading a person's retrievals. Delete this and the checks can pass on an install whose
    policies say nothing about whose a signal is, which is the property the table exists for."""
    import brain.ops.acceptance_checks_signal_log as module
    from tests.fixtures.scratch_postgres import sql

    breaking, mending, name, reason = POLICY_BREAKS[broken]
    sql(install, breaking)
    try:
        assert run_checks(install, name) == {name: (FAILED, getattr(module, reason))}
    finally:
        sql(install, mending)
