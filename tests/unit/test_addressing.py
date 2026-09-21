"""Addressing an agent by name, from the web application and from a chat mention.

`select_agent` decides; these tests hold that both surfaces hand it the same name for the same
intent, and that what reaches it keeps DENIED and ABSENT one answer.

Task ids: M3.9.8
"""

from __future__ import annotations

from brain.gate.addressing import Address, from_mention, from_web
from brain.gate.context import Channel
from brain.gate.select import SelectionStage, select_agent

MINE = frozenset({"support_helper", "finance_helper"})


def chosen(address: Address) -> tuple[str, SelectionStage, str]:
    selection = select_agent(
        address.question,
        Channel.CONSOLE,
        visible_agents=MINE,
        default_agent="support_helper",
        addressed=address.agent_id,
    )
    return selection.agent_id, selection.stage, selection.reason


def test_a_named_agent_the_person_may_use_gets_the_request_from_either_surface() -> None:
    """M3.9.8's first half. Deleting this lets the web picker and the chat mention resolve one
    intent to two names, and one of them silently lands on the router's choice instead."""
    web = from_web("what is overdue?", " Finance_Helper ")
    chat = from_mention("@finance_helper what is overdue?")
    assert web == chat == Address(question="what is overdue?", agent_id="finance_helper")
    assert chosen(web)[:2] == ("finance_helper", SelectionStage.ADDRESSED)


def test_an_agent_the_person_may_not_use_answers_as_one_that_does_not_exist() -> None:
    """M3.9.8's second half, DENIED and ABSENT as one answer through both surfaces. Deleting
    this lets an address probe which agents a company runs, one name at a time."""
    hidden_web = chosen(from_web("q", "payroll_helper"))
    hidden_chat = chosen(from_mention("@payroll_helper q"))
    never = chosen(from_web("q", "no_such_thing"))
    assert hidden_web == hidden_chat == never
    assert hidden_web[1] is not SelectionStage.ADDRESSED
    assert "payroll" not in hidden_web[2]


def test_with_nobody_named_the_router_chooses() -> None:
    """The positive case for the router. Deleting this is satisfied by an address that always
    names something, which would put every unaddressed question on one agent."""
    assert from_web("hello", None) == from_web("hello", "  ") == Address(question="hello")
    assert chosen(from_web("hello", None))[1] is SelectionStage.DEFAULT


def test_only_a_mention_that_opens_the_message_addresses_an_agent() -> None:
    """Text quoted from an email can carry an `@name`. Deleting this lets retrieved or pasted
    text choose the agent, and therefore the tools, that handle a question."""
    assert from_mention("please forward to @finance_helper") == Address(
        question="please forward to @finance_helper"
    )
    assert from_mention("  @Finance_Helper: overdue?") == Address(
        question="overdue?", agent_id="finance_helper"
    )
    assert from_mention("@finance_helperx q").agent_id == "finance_helperx"
    assert from_mention("@finance_helper") == Address(question="", agent_id="finance_helper")
