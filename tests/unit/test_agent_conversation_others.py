"""Other people's conversations with an agent: who is told they happened, and in what words.

Over `brain.agent_conversation_routes.oversees` and `brain.console.agent_conversations.outcome_of`
with no database; the rows themselves, and the policy that lets them be read, are the install
check's (`brain.ops.acceptance_checks_agent_oversight`).

Task ids: M39.11.1
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from brain.agent_conversation_routes import ConversationsView, OtherConversationView, oversees
from brain.agents.lifecycle import AGENT_LIFECYCLE_CAPABILITY
from brain.agents.model import AgentAudience, AgentAuthority, AgentRecord
from brain.console.agent_conversations import OUTCOME_WORDS, outcome_of
from brain.core.entitlement import EntitlementSet, Grant
from brain.core.scope import Scope
from brain.gate.stop import StopReason
from brain.knowledge.visibility import Visibility

#: Far from any wall clock: nothing here is about the present.
NOW = datetime(2019, 3, 1, 9, 0, tzinfo=UTC)


def agent(audience: AgentAudience) -> AgentRecord:
    return AgentRecord(
        agent_id="desk",
        display_name="Desk",
        persona="Answers questions for the desk.",
        audience=audience,
        authority=AgentAuthority(scope=Scope.unrestricted()),
        created_by="u_maker",
    )


def reader(person: str, *grants: Grant) -> Any:
    return SimpleNamespace(
        caller=SimpleNamespace(principal=SimpleNamespace(id=person)),
        reach=EntitlementSet(principal_id=person, grants=grants),
        now=NOW,
    )


ADMINISTERS = Grant(capability=AGENT_LIFECYCLE_CAPABILITY, scope=Scope.unrestricted())
TEAM = AgentAudience(level=Visibility.DEPARTMENT, owner_id="u_steward", department="web")


def test_the_steward_and_an_administrator_are_told_and_a_colleague_is_not() -> None:
    """The positive and the refusals together: the steward is told, a holder of the lifecycle
    authority is told, and a colleague who holds neither is not.

    Delete this and a colleague can be told who used an agent, or an administrator cannot."""
    record = agent(TEAM)

    assert oversees(record, reader("u_steward"))
    assert oversees(record, reader("u_admin", ADMINISTERS))
    assert not oversees(record, reader("u_colleague"))


def test_a_personal_agent_tells_nobody_but_its_owner_anything_about_other_people() -> None:
    """A personal agent has no other people, so even an administrator holding the lifecycle
    authority over everything is not told, and neither is its owner a list of others.

    Delete this and an administrator can read through a personal agent's run record."""
    record = agent(AgentAudience(level=Visibility.PERSONAL, owner_id="u_owner"))

    assert not oversees(record, reader("u_admin", ADMINISTERS))
    assert not oversees(record, reader("u_owner"))


@pytest.mark.parametrize(
    ("reason", "word"),
    [
        (StopReason.ANSWERED, "answered"),
        (StopReason.DECLINED, "declined"),
        (StopReason.FAULTED, "failed"),
        (StopReason.REFUSED, "failed"),
        (StopReason.TURN_BOUND, "failed"),
        (StopReason.TOOL_CALL_BOUND, "failed"),
        (StopReason.TIME_BOUND, "failed"),
        (StopReason.SPEND_BOUND, "failed"),
    ],
)
def test_every_way_a_run_can_end_reads_as_answered_declined_or_failed(
    reason: StopReason, word: str
) -> None:
    """Every `StopReason` has a word, so a new bound cannot reach a person as a blank, and the
    words are the three the page draws.

    Delete this and a stop reason added later can be told as nothing at all."""
    assert outcome_of(reason.value) == word
    assert word in OUTCOME_WORDS


def test_a_conversation_told_to_an_overseer_has_no_field_that_could_hold_a_word_of_it() -> None:
    """The view says who, when and how it ended and carries no field for a question, an answer, a
    title or a count; the whole answer has none either.

    Delete this and a field that would carry what was said can be added with nothing failing."""
    other = set(OtherConversationView.model_fields)
    assert other == {"person", "started_at", "ended_at", "outcome"}
    forbidden = {"question", "answer", "title", "preview", "total", "count", "text", "body"}
    assert not forbidden & other
    assert not forbidden & set(ConversationsView.model_fields)
