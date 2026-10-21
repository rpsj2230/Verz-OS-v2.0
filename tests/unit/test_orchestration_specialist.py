"""A specialist is asked its subtask as a question and what it answers is read as values.

Over `brain.orchestration.specialist`: the question a subtask becomes, the values a reply is read
into, and the refusal a turned-away question is. The function that puts the question to an agent is
a script here; `tests/unit/test_coordination_routes.py` drives the real route over a recorded one.

Task ids: M18.5.2
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

import pytest

from brain.agents.model import CEILING_PRINCIPAL_PREFIX
from brain.core.entitlement import EntitlementSet
from brain.orchestration.contract import FieldKind, FieldSpec
from brain.orchestration.coordinator import ChildWork, SpecialistRefusedError
from brain.orchestration.specialist import (
    KIND_WORDS,
    Answer,
    AskingSpecialist,
    question_for,
    values_from,
)

OUTPUT = (
    FieldSpec(name="score", kind=FieldKind.INTEGER),
    FieldSpec(name="seen_at", kind=FieldKind.TIMESTAMP),
)


def _work(upstream: dict[str, dict[str, object]] | None = None) -> ChildWork:
    reach = EntitlementSet(principal_id="u_asker", grants=())
    return ChildWork(
        run_id="r",
        subtask_id="one",
        callee_id="web",
        objective="Find the site score for this client",
        output=OUTPUT,
        tool_hints=(),
        reach=reach,
        lenses=(EntitlementSet(principal_id=f"{CEILING_PRINCIPAL_PREFIX}web", grants=()),),
        upstream=upstream or {},
    )


def test_every_kind_of_value_has_words_a_model_is_asked_in() -> None:
    """Delete this and a kind added to the contract's vocabulary is asked for in no words at all."""
    assert set(KIND_WORDS) == set(FieldKind)


def test_the_question_carries_the_objective_and_the_shape_of_the_answer_and_no_reach() -> None:
    """Delete this and what a specialist is told is not what it is asked for, or names its reach."""
    asked = question_for(_work())
    assert asked.startswith("Find the site score for this client")
    assert '"score" (a whole number)' in asked
    assert '"seen_at" (a date and time in ISO 8601 with a time zone)' in asked
    assert "u_asker" not in asked and "agent:" not in asked


def test_earlier_steps_are_told_as_their_checked_values_only() -> None:
    """Delete this and a later step is handed nothing of what an earlier one found, or handed
    more than its validated values."""
    when = datetime(2999, 1, 1, tzinfo=UTC)
    asked = question_for(_work({"zero": {"count": 3, "at": when}}))
    assert json.dumps({"zero": {"at": when.isoformat(), "count": 3}}, sort_keys=True) in asked
    assert "Earlier steps found" not in question_for(_work())


def test_a_reply_is_read_into_the_values_the_contract_names_and_nothing_else() -> None:
    """Delete this and a reply's extra fields reach the check, or a timestamp stays text."""
    reply = 'Here you go: {"score": 7, "seen_at": "2999-01-01T00:00:00+00:00", "note": "x"} thanks'
    values = values_from(reply, OUTPUT)
    assert values == {"score": 7, "seen_at": datetime(2999, 1, 1, tzinfo=UTC)}


@pytest.mark.parametrize(
    "reply",
    ["no object here", "{not json", "[1, 2]", '{"score": NaN}', ""],
)
def test_a_reply_with_no_readable_object_is_no_values_at_all(reply: str) -> None:
    """Delete this and a specialist that answered in prose returns something rather than nothing."""
    assert values_from(reply, OUTPUT) == {}


def test_a_missing_field_is_absent_so_the_contract_states_it_missing() -> None:
    """Delete this and an absent field is filled in with a guess before the check can see it."""
    assert values_from('{"score": 1}', OUTPUT) == {"score": 1}


def test_a_timestamp_that_is_not_one_is_left_as_text_for_the_contract_to_refuse() -> None:
    """Delete this and an unreadable date is dropped or crashes the read."""
    assert values_from('{"seen_at": "tomorrow"}', OUTPUT) == {"seen_at": "tomorrow"}


def test_an_answered_question_is_delivered_with_its_cost_and_time() -> None:
    """Delete this and the cost and time a route measured never reach the run's trace."""

    async def ask(work: ChildWork, question: str) -> Answer:
        assert work.subtask_id == "one" and "Find the site score" in question
        return Answer(text='{"score": 2}', minor=5, seconds=1.25)

    delivered = asyncio.run(AskingSpecialist(ask).run(_work()))
    assert dict(delivered.values) == {"score": 2}
    assert (delivered.minor, delivered.seconds) == (5, 1.25)


@pytest.mark.parametrize("answer", [Answer(text=None), Answer(text="{}", refused=True)])
def test_a_question_that_was_turned_away_is_a_refusal(answer: Answer) -> None:
    """Delete this and a halted or unavailable specialist is read as a specialist that answered."""

    async def ask(work: ChildWork, question: str) -> Answer:
        return answer

    with pytest.raises(SpecialistRefusedError):
        asyncio.run(AskingSpecialist(ask).run(_work()))
