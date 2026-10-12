"""The copied-answer check, passing on PostgreSQL at head and failing with the product broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M16.2.2
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any, Final

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE: Final = "brain.ops.acceptance_checks_copied"
NAME: Final = "a_copied_answer_is_one_signal_naming_it_and_no_words"


def test_the_check_names_the_leaf_it_proves() -> None:
    """One check, one leaf. Delete this and the check can lose its leaf with the page showing the
    same row, or start closing a leaf it does not prove."""
    from brain.ops import acceptance_checks_copied as module

    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [(NAME, ("M16.2.2",))]
    assert checks_in(MODULE) == [NAME]
    assert 870 <= module.CHECK_ORDER <= 889


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_copied") as url:
        yield url


def run_check(url: str) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url

    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings_from({"BRAIN_DATABASE_URL": url}),
            commit="abc1234",
            checks=list(registered((MODULE,))),
            force=True,
        )
    )
    return {one.name: (one.outcome, one.reason) for one in results}


@pytest.mark.needs_db
def test_the_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The check as the worker runs it.** It passes and nothing it wrote is left. Delete this
    and a check that can never pass on a real schema reaches the owner's server."""
    before = counts(install)
    assert run_check(install) == {NAME: (PASSED, "")}
    assert counts(install) == before


@pytest.mark.needs_db
def test_a_route_that_keeps_nothing_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The copy kept nowhere. Delete this and the check closes M16.2.2 on a route that says
    noted and writes nothing."""
    from brain.ops.signal_store import StoredSignals

    async def nowhere(self: Any, **kwargs: Any) -> bool:
        return True

    monkeypatch.setattr(StoredSignals, "copied", nowhere)
    outcome, reason = run_check(install)[NAME]
    assert outcome == FAILED
    assert "was not kept" in reason


@pytest.mark.needs_db
def test_a_route_that_says_whether_the_trace_was_the_callers_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The route telling a person their copy was of somebody else's answer. Delete this and the
    check closes M16.2.2 on a route that is a way to find out which traces exist."""
    from brain import api_routes

    async def telling(request: Any, asked: Any, body: Any) -> Any:
        signals = api_routes.signals_of(request.app.state)
        assert signals is not None
        kept = await signals.copied(
            principal_id=asked.caller.principal.id, trace_id=body.trace_id, now=asked.now
        )
        return api_routes.CopiedView(told="Noted." if kept else "That is not your answer.")

    monkeypatch.setattr(api_routes, "copied_answer", telling)
    outcome, reason = run_check(install)[NAME]
    assert outcome == FAILED
    assert "answered differently" in reason
