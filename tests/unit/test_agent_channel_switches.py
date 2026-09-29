"""Which channels an agent answers on, once switches are pressed, and which agents a question keeps.

Real `AgentRecord`s and real `ChannelRow`s from `brain.console.agent_tabs`, so the rows are the ones
the page is drawn from. Dates are pinned far from any wall clock, for CLAUDE.md's reason.

Task ids: M39.2.4.1, M39.2.4.2, M39.2.4.3, M39.2.4.4
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from brain.agents.channel_switches import (
    ALREADY_OFF,
    ALREADY_ON,
    NOT_A_CHANNEL_HERE,
    NOT_REACHABLE,
    WEB,
    ChannelSwitch,
    ChannelSwitchError,
    answering_on,
    reachable,
    states,
    switched_on,
    to_switch,
)
from brain.agents.model import AgentAudience, AgentAuthority, AgentRecord
from brain.console.agent_tabs import ChannelRow, RenderProfile
from brain.gate.context import Channel
from brain.knowledge.visibility import Visibility
from brain.tables.channel_switch import WEB_PAGE

AT = datetime(2019, 3, 6, 9, 0, tzinfo=UTC)


def record(agent_id: str) -> AgentRecord:
    return AgentRecord(
        agent_id=agent_id,
        display_name=agent_id.title(),
        persona="Answers briefly.",
        audience=AgentAudience(level=Visibility.COMPANY, owner_id="p_steward"),
        authority=AgentAuthority(capabilities=()),
        created_by="p_steward",
    )


def switch(agent_id: str, channel: Channel, on: bool, *, minutes: int) -> ChannelSwitch:
    return ChannelSwitch(
        agent_id=agent_id,
        channel=channel,
        switched_on=on,
        at=AT + timedelta(minutes=minutes),
        changed_by="p_admin",
    )


def test_the_newest_switch_decides_and_a_channel_nobody_switched_on_is_off() -> None:
    """**M39.2.4.1.** A later off beats an earlier on whatever order the switches are read in, an
    agent whose every switch is off is absent rather than mapped to nothing, and nothing switched is
    nothing on. Delete this and a stale switch decides, or a list read newest first switches an
    agent back on."""
    on = switch("desk", Channel.LARK, True, minutes=1)
    off = switch("desk", Channel.LARK, False, minutes=2)
    web = switch("desk", Channel.CONSOLE, True, minutes=3)
    quiet = switch("quiet", Channel.CONSOLE, False, minutes=4)

    assert switched_on([off, on, web, quiet]) == {"desk": frozenset({Channel.CONSOLE})}
    assert switched_on([web, off, on]) == switched_on([on, off, web])
    assert switched_on([on]) == {"desk": frozenset({Channel.LARK})}
    assert switched_on([]) == {}


def test_a_question_keeps_only_the_agents_switched_on_for_its_channel_in_the_order_given() -> None:
    """**The requirement itself.** Asked on the web page, an agent switched on only for a chat and
    an agent nothing switched on are left out; asked on that chat, the web-only agent is. Delete
    this and an agent answers on a channel nobody switched on for it."""
    web_only, chat_only, nowhere = record("web_only"), record("chat_only"), record("nowhere")
    on = {
        "web_only": frozenset({Channel.CONSOLE}),
        "chat_only": frozenset({Channel.LARK}),
    }
    records = (chat_only, web_only, nowhere)

    assert answering_on(records, on, Channel.CONSOLE) == (web_only,)
    assert answering_on(records, on, Channel.LARK) == (chat_only,)
    assert answering_on(records, {}, Channel.CONSOLE) == ()


def test_the_web_page_is_always_drawn_first_and_every_offered_surface_after_it() -> None:
    """**M39.2.4.1, M39.2.4.3 and M39.2.4.4 on the page.** The web page is a row whatever the
    surfaces offer, with no profile of its own; each offered surface keeps its derived profile and
    its group flag; and whether each is on is the switches' word. Delete this and the one channel
    every agent answered on has no switch, or a chat's profile is dropped on its way to the page."""
    rows = (
        ChannelRow(
            channel=Channel.LARK, enabled=True, profile=RenderProfile.CARD, group_installable=False
        ),
        ChannelRow(
            channel=Channel.EMAIL,
            enabled=False,
            profile=RenderProfile.ATTACHMENT,
            group_installable=False,
        ),
    )
    drawn = states(rows, frozenset({Channel.LARK}))

    assert [(one.channel, one.on, one.profile) for one in drawn] == [
        (Channel.CONSOLE, False, None),
        (Channel.LARK, True, RenderProfile.CARD),
        (Channel.EMAIL, False, RenderProfile.ATTACHMENT),
    ]
    assert states((), frozenset({Channel.CONSOLE}))[0].on is True
    assert WEB is WEB_PAGE is Channel.CONSOLE


def test_a_switch_is_refused_off_the_page_and_to_the_state_it_is_already_in() -> None:
    """A channel with no row is refused in one sentence, whether the install has no such surface or
    the run could not be carried there; switching on what is on, or off what is off, is refused; and
    a real change is allowed. Delete this and a switch records a binding nothing delivers, or the
    ledger fills with presses that changed nothing."""
    drawn = states(
        (
            ChannelRow(
                channel=Channel.LARK,
                enabled=False,
                profile=RenderProfile.CARD,
                group_installable=False,
            ),
        ),
        frozenset({Channel.CONSOLE}),
    )

    to_switch(drawn, Channel.LARK, True)
    to_switch(drawn, Channel.CONSOLE, False)
    for channel, on, said in (
        (Channel.API, True, NOT_A_CHANNEL_HERE),
        (Channel.SLACK, False, NOT_A_CHANNEL_HERE),
        (Channel.CONSOLE, True, ALREADY_ON),
        (Channel.LARK, False, ALREADY_OFF),
    ):
        with pytest.raises(ChannelSwitchError) as refused:
            to_switch(drawn, channel, on)
        assert str(refused.value) == said


def test_an_agent_switched_on_nowhere_is_not_reachable_and_the_page_says_so_in_words() -> None:
    """Delete this and an agent that answers nowhere reads as one that answers, or the sentence the
    owner asked for drifts into a code."""
    assert reachable(frozenset()) is False
    assert reachable(frozenset({Channel.LARK})) is True
    assert NOT_REACHABLE == "Not reachable: no channel is switched on"
