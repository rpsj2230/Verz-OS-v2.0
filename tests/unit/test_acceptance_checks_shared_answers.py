"""The install check for sharing one answer run, passing on PostgreSQL at head and failing with the
product broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M36.2.3.1, M36.2.3.2
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest

from brain.ops import acceptance_checks_shared_answers, acceptance_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.ops.acceptance_checks_shared_answers import CHECK_ORDER
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_shared_answers"
SHARING = "equal_reach_waits_for_a_run_in_flight_other_reach_does_not"


def test_the_module_names_its_leaves_in_one_check_inside_its_range() -> None:
    """One check naming both leaves, in a range of its own. Delete this and a leaf can move to a
    check that never looked at it."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (SHARING, ("M36.2.3.1", "M36.2.3.2"))
    ]
    assert checks_in(MODULE) == [SHARING]
    assert 2125 < CHECK_ORDER < 2150


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_shared_answers") as url:
        yield url


def run_module(url: str) -> dict[str, tuple[str, str]]:
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


@pytest.mark.needs_db
def test_the_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The module as the worker runs it.** It passes and nothing is left behind, the switch it
    turned on included. Delete this and a check that can never pass on a real schema reaches the
    owner's server."""
    before = counts(install)
    assert run_module(install) == {SHARING: (PASSED, "")}
    assert counts(install) == before


@pytest.mark.needs_db
def test_a_registry_that_makes_nobody_wait_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every arrival made a leader. Delete this and sharing can stop waiting while the check
    goes on passing on an answer the colleague computed for themselves."""
    from brain.connectors.federation import FlightRole
    from brain.ops import shared_answers

    monkeypatch.setattr(shared_answers, "share_role", lambda waiting, running: FlightRole.LEADER)
    outcome, reason = run_module(install)[SHARING]
    assert outcome == FAILED
    assert "not held back" in reason


@pytest.mark.needs_db
def test_a_registry_keyed_on_the_question_alone_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The key losing the entitlement hash, in the registry and in the rule that decides sharing.
    Both, because either alone is caught by the other. Delete this and a colleague without the
    price grant could be held for, and served from, a run made at somebody else's reach."""
    from brain.gate.cache_key import CacheKeyParts, normalise_question
    from brain.ops import scaling, shared_answers

    def question_only(parts: CacheKeyParts) -> str:
        return normalise_question(parts.question)

    monkeypatch.setattr(shared_answers, "cache_key", question_only)
    monkeypatch.setattr(scaling, "cache_key", question_only)
    monkeypatch.setattr(acceptance_checks_shared_answers, "HELD_BACK_FOR_TOO_LONG", 3.0)
    outcome, reason = run_module(install)[SHARING]
    assert outcome == FAILED
    assert "held back for another reach's run" in reason


@pytest.mark.needs_db
def test_a_switch_left_off_fails_the_check(install: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """The answer path ignoring the install's switch. Delete this and the check passes with the
    wiring removed."""
    from brain import api_routes

    async def never(sessions: object) -> bool:
        del sessions
        return False

    monkeypatch.setattr(api_routes, "answers_are_shared", never)
    outcome, reason = run_module(install)[SHARING]
    assert outcome == FAILED
    assert "never registered" in reason
