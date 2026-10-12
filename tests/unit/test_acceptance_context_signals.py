"""The context and escalation checks, passing on PostgreSQL at head and failing with the product
broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M16.2.4, M16.6.1
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_context_signals"
CONTEXT = "a_turns_trace_names_its_parts_and_never_what_they_said"
ESCALATION = "a_question_handed_to_a_person_is_a_signal_naming_its_answer"


def test_the_module_declares_each_check_naming_the_leaf_it_proves() -> None:
    """Two checks, one leaf each. Delete this and a check can lose its leaf with the page
    showing the same row, or start closing a leaf it does not prove."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (CONTEXT, ("M16.6.1",)),
        (ESCALATION, ("M16.2.4",)),
    ]
    assert checks_in(MODULE) == [CONTEXT, ESCALATION]
    from brain.ops import acceptance_checks_context_signals as module

    assert 870 <= module.CHECK_ORDER <= 889


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_context_signals") as url:
        yield url


def run_module(url: str) -> dict[str, tuple[str, str]]:
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
def test_the_context_and_escalation_checks_pass_on_an_install_and_leave_nothing(
    install: str,
) -> None:
    """**The checks as the worker runs them.** Both pass and nothing they wrote is left. Delete
    this and a check that can never pass on a real schema reaches the owner's server."""
    before = counts(install)
    assert run_module(install) == {CONTEXT: (PASSED, ""), ESCALATION: (PASSED, "")}
    assert counts(install) == before


@pytest.mark.needs_db
def test_an_assembler_that_names_no_context_fails_the_context_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The note dropped from every turn. Delete this and the check closes M16.6.1 on a trace that
    never says what a model was shown."""
    from brain.gate import turn_context

    monkeypatch.setattr(turn_context.ContextParts, "note", lambda self: None)
    outcome, reason = run_module(install)[CONTEXT]
    assert outcome == FAILED
    assert "no note of its context" in reason


@pytest.mark.needs_db
def test_an_assembler_that_never_shows_the_askers_memory_fails_the_context_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The asker's memories left out of the assembled parts. Delete this and the check passes on
    an assembler that forgets a part."""
    from brain.gate import turn_context

    real = turn_context.ContextParts._held

    def without_memory(self: turn_context.ContextParts) -> dict[turn_context.Part, bool]:
        return {**real(self), turn_context.Part.ASKER_MEMORY: False}

    monkeypatch.setattr(turn_context.ContextParts, "_held", without_memory)
    outcome, reason = run_module(install)[CONTEXT]
    assert outcome == FAILED
    assert "did not include the asker's memory" in reason


@pytest.mark.needs_db
def test_a_handoff_that_never_marks_its_answer_fails_the_escalation_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The handoff never marking the answer as handed on, so the thread has no escalation to keep.
    Delete this and the check closes M16.2.4 on a handoff the learning loop never hears of."""
    from brain import escalation_routes

    async def unmarked(request: object, answered: object, **kwargs: object) -> object:
        return answered

    monkeypatch.setattr(escalation_routes, "escalated", unmarked)
    outcome, reason = run_module(install)[ESCALATION]
    assert outcome == FAILED
    assert "escalation" in reason
