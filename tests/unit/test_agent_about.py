"""The About flow, held to its inputs over generated agents rather than over the ones imagined.

`brain.console.agent_about.about_flow` says what an agent is set up to do, and the failure that
matters is a sentence about something it is not set up to do. A handful of hand-built agents would
check the wording of a handful of setups; the properties below generate the channels, the
automations, the sources, the ceiling, the registered tools and the leash, and ask of every flow
that each line speaks only for what was handed in, in the structure every line carries, so a
property never has to trust a sentence. The literal cases after them pin the wording of one agent,
so a change of words is a failing comparison rather than a property that still holds.

Task ids: none
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from hypothesis import given, settings
from hypothesis import strategies as st

from brain.agents.model import AgentAuthority
from brain.console.agent_about import (
    AN_AGENT_NEVER_SEES_MORE_THAN_ITS_CALLER,
    APPROVER_RULE,
    CHANNEL_WORDS,
    AboutFlow,
    FlowLine,
    Line,
    NeverLine,
    Offered,
    Scheduled,
    Setup,
    Step,
    about_flow,
    about_gaps,
)
from brain.console.agent_profile import at_most, rungs_for
from brain.console.agent_tabs import RenderProfile
from brain.console.workspace_capabilities import ConnectorRow, Presence
from brain.core.envelope import SideEffect, ToolDefinition
from brain.core.scope import Clause, Op, Scope
from brain.gate.context import Channel
from brain.gate.injection import AutonomyTier
from brain.gate.leash import Leash, LeashEntry

AGENT = "quote_helper"
SHADOW, ASSISTED, AUTONOMOUS = AutonomyTier.SHADOW, AutonomyTier.ASSISTED, AutonomyTier.AUTONOMOUS
WEB = Scope(clauses=(Clause(field="department", op=Op.EQ, value="web"),))
ORDER = list(SideEffect)

#: Tool names with no word in them a sentence about sending, paying or approving could be read by,
#: so a property about the words is a property about the module's sentences and not the fixture's.
NAMES = (
    "alpha.read_row",
    "alpha.make_row",
    "beta.put_row",
    "beta.post_note",
    "gamma.pay_bill",
    "gamma.list_bill",
)
#: A name a ceiling may allow that nothing registers.
UNREGISTERED = "delta.ghost_row"

#: What would describe an agent as sending or moving money, in any tense.
SENDING = re.compile(r"\b(send|sends|sending|sent|leaves the building|money)\b", re.IGNORECASE)


def tool(name: str, effect: SideEffect) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description="a tool under test",
        entity="row",
        required_capability="read:row.reference",
        side_effect=effect,
        source=name.partition(".")[0],
    )


@st.composite
def setups(draw: st.DrawFn, largest: SideEffect | None = None) -> Setup:
    registered = tuple(
        tool(name, draw(st.sampled_from(tuple(SideEffect))))
        for name in draw(st.lists(st.sampled_from(NAMES), unique=True))
    )
    allowed = draw(st.frozensets(st.sampled_from((*NAMES, UNREGISTERED))))
    entries = draw(
        st.lists(
            st.builds(
                LeashEntry,
                agent_id=st.sampled_from((AGENT, "someone_else")),
                target=st.sampled_from(NAMES),
                scope=st.sampled_from((Scope(), WEB)),
                rung=st.sampled_from(tuple(AutonomyTier)),
            ),
            max_size=6,
        )
    )
    return Setup(
        agent_id=AGENT,
        authority=AgentAuthority(
            scope=draw(st.sampled_from((Scope(), WEB))),
            allowed_tools=allowed,
            max_side_effect=largest or draw(st.sampled_from(tuple(SideEffect))),
        ),
        registered=registered,
        leash=Leash(entries=tuple(entries)),
    )


channels = st.lists(
    st.builds(
        Offered,
        channel=st.sampled_from((Channel.EMAIL, Channel.SLACK, Channel.LARK)),
        profile=st.sampled_from(tuple(RenderProfile)),
    ),
    max_size=3,
)
automations = st.none() | st.lists(
    st.builds(
        Scheduled,
        automation_id=st.sampled_from(("auto_one", "auto_two", "auto_three")),
        name=st.just("I summarise the week"),
        schedule=st.just("every monday at 08:00 UTC"),
        running=st.booleans(),
    ),
    max_size=3,
)
sources = st.lists(
    st.builds(
        ConnectorRow,
        source=st.sampled_from(("alpha", "beta", "omega")),
        presence=st.sampled_from(tuple(Presence)),
    ),
    max_size=3,
)


def lines(flow: AboutFlow) -> list[FlowLine]:
    return [line for step in flow.steps for line in step.lines]


def of_step(flow: AboutFlow, step: Step) -> list[FlowLine]:
    return [line for one in flow.steps if one.step is step for line in one.lines]


def callable_tools(setup: Setup) -> dict[str, ToolDefinition]:
    """What a run of this setup could call, worked out here from the three facts, not the module."""
    return {
        one.name: one
        for one in setup.registered
        if one.name in setup.authority.allowed_tools
        and at_most(one.side_effect, setup.authority.max_side_effect)
    }


# ----------------------------------------------------------------------------- properties
@settings(max_examples=300, deadline=None)
@given(
    setup=setups(largest=SideEffect.DRAFT),
    offered=channels,
    scheduled=automations,
    rows=sources,
)
def test_an_agent_whose_largest_side_effect_is_a_draft_is_never_described_as_sending(
    setup: Setup,
    offered: list[Offered],
    scheduled: list[Scheduled] | None,
    rows: list[ConnectorRow],
) -> None:
    """No line attributes an effect above a draft to the agent, and no sentence in any step says
    it sends anything or moves money, whatever tools the registry holds.

    What breaks if this is deleted: a draft agent holding a registered sending tool is described
    as sending, which is the one sentence a reader deciding whether to trust it must not be told."""
    flow = about_flow(channels=offered, automations=scheduled, sources=rows, setup=setup)
    for line in lines(flow):
        assert line.effect is None or ORDER.index(line.effect) <= ORDER.index(SideEffect.DRAFT)
        assert not SENDING.search(line.text), line.text


@settings(max_examples=100, deadline=None)
@given(offered=channels, scheduled=automations, rows=sources)
def test_an_agent_with_a_sending_action_that_can_be_carried_out_is_described_as_sending(
    offered: list[Offered], scheduled: list[Scheduled] | None, rows: list[ConnectorRow]
) -> None:
    """The positive sibling: an agent whose ceiling admits sending, with a sending tool held on the
    assisted rung, has an action line and a result line that say so.

    What breaks if this is deleted: the property above is satisfied by a flow that never mentions
    any effect at all."""
    setup = Setup(
        agent_id=AGENT,
        authority=AgentAuthority(
            allowed_tools=frozenset({"beta.post_note"}), max_side_effect=SideEffect.SEND
        ),
        registered=(tool("beta.post_note", SideEffect.SEND),),
        leash=Leash(
            entries=(
                LeashEntry(agent_id=AGENT, target="beta.post_note", scope=Scope(), rung=ASSISTED),
            )
        ),
    )
    flow = about_flow(channels=offered, automations=scheduled, sources=rows, setup=setup)
    said = {(line.kind, line.effect) for line in lines(flow)}
    assert (Line.ACTION, SideEffect.SEND) in said
    assert (Line.CARRIED_OUT, SideEffect.SEND) in said
    assert any(SENDING.search(line.text) for line in of_step(flow, Step.RESULT))


@settings(max_examples=300, deadline=None)
@given(setup=setups(), offered=channels, scheduled=automations, rows=sources)
def test_a_shadow_action_is_never_described_as_awaiting_approval(
    setup: Setup,
    offered: list[Offered],
    scheduled: list[Scheduled] | None,
    rows: list[ConnectorRow],
) -> None:
    """An action whose every rung is Shadow is never on an approval line and is said to be only
    practised; every approval line is for an action one of whose rungs is Assisted; and the rule
    about who approves appears exactly when some action waits.

    What breaks if this is deleted: the page tells a person to expect an approval for something
    nothing will ever carry out, or promises a person steps in where nobody does."""
    flow = about_flow(channels=offered, automations=scheduled, sources=rows, setup=setup)
    waiting = [line for line in lines(flow) if line.kind is Line.AWAITS_APPROVAL]
    for line in waiting:
        assert line.tool is not None
        assert ASSISTED in rungs_for(setup.leash, AGENT, line.tool)
    for name in callable_tools(setup):
        told = rungs_for(setup.leash, AGENT, name)
        if told == (SHADOW,):
            assert name not in {line.tool for line in waiting}
    approver = [line for line in of_step(flow, Step.PERSON) if line.kind is Line.APPROVER]
    assert bool(approver) is bool(waiting)
    assert all(line.text == APPROVER_RULE for line in approver)


@settings(max_examples=300, deadline=None)
@given(setup=setups(), offered=channels, scheduled=automations, rows=sources)
def test_the_flow_names_nothing_the_agent_is_not_set_up_with(
    setup: Setup,
    offered: list[Offered],
    scheduled: list[Scheduled] | None,
    rows: list[ConnectorRow],
) -> None:
    """Every channel on a line was offered, every automation is one handed in running, every source
    is one attached, and every tool is allowed, registered and inside the largest side effect, with
    an action's rungs exactly the leash's and its link exactly whether an entry names it.

    What breaks if this is deleted: the flow describes a surface, a schedule, a source or an action
    the agent does not have, which is the whole failure a derived description exists to prevent."""
    flow = about_flow(channels=offered, automations=scheduled, sources=rows, setup=setup)
    can_call = callable_tools(setup)
    running = {one.automation_id for one in scheduled or () if one.running}
    attached = {one.source for one in rows if one.presence is Presence.ATTACHED}
    for line in lines(flow):
        assert set(line.channels) <= {one.channel for one in offered}
        if line.automation_id is not None:
            assert line.automation_id in running
        if line.kind is Line.SOURCE:
            assert line.source in attached
        if line.tool is not None:
            assert line.tool in can_call
        if line.kind is Line.ACTION:
            assert line.tool is not None
            assert can_call[line.tool].side_effect is not SideEffect.NONE
            assert line.effect is can_call[line.tool].side_effect
            assert line.rungs == rungs_for(setup.leash, AGENT, line.tool)
            assert line.leash_entry is any(
                one.agent_id == AGENT and one.target == line.tool for one in setup.leash.entries
            )
        if line.kind is Line.READ_TOOL:
            assert line.tool is not None
            assert can_call[line.tool].side_effect is SideEffect.NONE
    actions = {line.tool for line in lines(flow) if line.kind is Line.ACTION}
    assert actions == {
        name for name, one in can_call.items() if one.side_effect is not SideEffect.NONE
    }


@settings(max_examples=300, deadline=None)
@given(setup=st.none() | setups(), offered=channels, scheduled=automations, rows=sources)
def test_the_steps_are_numbered_from_one_without_a_gap_and_none_is_empty(
    setup: Setup | None,
    offered: list[Offered],
    scheduled: list[Scheduled] | None,
    rows: list[ConnectorRow],
) -> None:
    """What breaks if this is deleted: a step a reader may not be told about leaves a gap in the
    numbering, which is a count of something withheld, or a heading is drawn over nothing."""
    flow = about_flow(channels=offered, automations=scheduled, sources=rows, setup=setup)
    assert [step.number for step in flow.steps] == list(range(1, len(flow.steps) + 1))
    assert all(step.lines for step in flow.steps)
    assert [step.step for step in flow.steps] == sorted(
        (step.step for step in flow.steps), key=list(Step).index
    )
    assert flow.never[-1] == NeverLine(
        text=AN_AGENT_NEVER_SEES_MORE_THAN_ITS_CALLER, every_agent=True
    )


@settings(max_examples=200, deadline=None)
@given(offered=channels, scheduled=automations, rows=sources)
def test_a_reader_without_the_settings_read_is_told_nothing_about_tools_rungs_effects_or_rows(
    offered: list[Offered], scheduled: list[Scheduled] | None, rows: list[ConnectorRow]
) -> None:
    """With no setup there is no step about what the agent does or where a person steps in, no line
    carries a tool, an effect or a rung, and the only thing it will never do is the sentence true of
    every agent.

    What breaks if this is deleted: the About tab becomes a way round the Settings tab's grant,
    publishing the ceiling and the leash to everybody the audience covers."""
    flow = about_flow(channels=offered, automations=scheduled, sources=rows, setup=None)
    assert {step.step for step in flow.steps} <= {Step.STARTS, Step.READS, Step.RESULT}
    for line in lines(flow):
        assert (line.tool, line.effect, line.rungs, line.leash_entry) == (None, None, (), None)
        assert line.kind not in {Line.ROWS, Line.NOTHING_WRITTEN, Line.CARRIED_OUT}
    assert flow.never == (
        NeverLine(text=AN_AGENT_NEVER_SEES_MORE_THAN_ITS_CALLER, every_agent=True),
    )


@settings(max_examples=200, deadline=None)
@given(setup=st.none() | setups(), offered=channels, rows=sources)
def test_a_reader_without_the_automations_read_is_told_no_schedule_and_never_that_nothing_starts_it(
    setup: Setup | None, offered: list[Offered], rows: list[ConnectorRow]
) -> None:
    """With no automations handed in there is no schedule line, no line about a run's result and no
    "nothing starts it", because that would be false whenever an automation is running.

    What breaks if this is deleted: a reader who may not see the Automations tab learns from the
    About tab whether the agent runs on a schedule."""
    flow = about_flow(channels=offered, automations=None, sources=rows, setup=setup)
    kinds = {line.kind for line in lines(flow)}
    assert not kinds & {Line.SCHEDULED, Line.RUN_RESULT, Line.NOTHING_STARTS}


def test_nothing_starts_it_is_said_only_where_no_surface_or_running_automation_was_seen() -> None:
    """A reader of the Automations tab shown a stopped automation and offered no surface is told
    nothing starts it; a running one or an offered surface replaces that line.

    What breaks if this is deleted: the one negative sentence in the first step is said beside a
    schedule, or never said at all."""
    stopped = [Scheduled("auto_one", "I summarise the week", "every monday at 08:00 UTC", False)]
    running = [Scheduled("auto_one", "I summarise the week", "every monday at 08:00 UTC", True)]

    def starts(offered: list[Offered], scheduled: list[Scheduled]) -> list[Line]:
        flow = about_flow(channels=offered, automations=scheduled, sources=[], setup=None)
        return [line.kind for line in of_step(flow, Step.STARTS)]

    assert starts([], stopped) == [Line.NOTHING_STARTS]
    assert starts([], running) == [Line.SCHEDULED]
    assert starts([Offered(Channel.EMAIL, RenderProfile.PLAIN)], stopped) == [Line.ASKED]


# ------------------------------------------------------------------------ one agent, worded
def test_one_agent_reads_as_the_flow_the_owner_asked_for() -> None:
    """Every step of a drafting agent with a practised sending action, worded literally.

    What breaks if this is deleted: the properties above hold for sentences nobody would want to
    read, and a change of wording reaches the page without anybody reading it first."""
    setup = Setup(
        agent_id=AGENT,
        authority=AgentAuthority(
            scope=WEB,
            allowed_tools=frozenset({"alpha.read_row", "alpha.make_row", "beta.post_note"}),
            max_side_effect=SideEffect.SEND,
        ),
        registered=(
            tool("alpha.read_row", SideEffect.NONE),
            tool("alpha.make_row", SideEffect.DRAFT),
            tool("beta.post_note", SideEffect.SEND),
        ),
        leash=Leash(
            entries=(
                LeashEntry(agent_id=AGENT, target="alpha.make_row", scope=Scope(), rung=ASSISTED),
            )
        ),
    )
    flow = about_flow(
        channels=[
            Offered(Channel.EMAIL, RenderProfile.ATTACHMENT),
            Offered(Channel.SLACK, RenderProfile.CARD),
        ],
        automations=[
            Scheduled("auto_one", "I summarise the week", "every monday at 08:00 UTC", True)
        ],
        sources=[
            ConnectorRow("alpha", Presence.ATTACHED),
            ConnectorRow("omega", Presence.REQUESTED),
        ],
        setup=setup,
    )

    assert [
        (step.number, step.title, [line.text for line in step.lines]) for step in flow.steps
    ] == [
        (
            1,
            "What starts it",
            [
                "Somebody asks it, on a surface that can carry its answer to them: email or Slack.",
                "I summarise the week, on a schedule: every monday at 08:00 UTC.",
            ],
        ),
        (
            2,
            "What it reads",
            [
                "It reads from alpha.",
                "It may call alpha.read_row, which changes nothing.",
                "Only rows where department is web.",
            ],
        ),
        (
            3,
            "What it does",
            [
                "alpha.make_row, which prepares a draft: it gets this ready, and a person approves "
                "it first.",
                "beta.post_note, which sends a message: it only practises this, and nothing is "
                "carried out.",
            ],
        ),
        (
            4,
            "Where a person steps in",
            [
                "alpha.make_row waits for a person to approve it before anything is carried out.",
                APPROVER_RULE,
                "beta.post_note is only practised, so there is nothing to approve.",
            ],
        ),
        (
            5,
            "Where the result goes",
            [
                "An answer goes back to whoever asked, on the surface they asked on, as a card or "
                "with its files attached.",
                "What a scheduled run found is shown only to the person it runs as; anybody else "
                "sees that it ran, when, and how it ended.",
                "Anything it prepares stays a draft until a person acts on it.",
            ],
        ),
    ]
    assert [one.text for one in flow.never] == [
        "It never moves money.",
        "It never reads a row unless department is web.",
        "It never sees more than the person it is working for could see themselves.",
    ]
    action = next(line for line in lines(flow) if line.tool == "beta.post_note")
    assert action.leash_entry is False
    assert next(line for line in lines(flow) if line.tool == "alpha.make_row").leash_entry is True


def test_an_agent_whose_actions_are_all_practised_writes_nothing_yet_and_one_without_answers() -> (
    None
):
    """What breaks if this is deleted: an agent with a sending tool held at Shadow is said to leave
    messages behind it, or an agent with no action is said to have practised ones."""
    authority = AgentAuthority(
        allowed_tools=frozenset({"beta.post_note"}), max_side_effect=SideEffect.SEND
    )
    practised = about_flow(
        channels=[],
        automations=None,
        sources=[],
        setup=Setup(AGENT, authority, (tool("beta.post_note", SideEffect.SEND),), Leash()),
    )
    reads_only = about_flow(
        channels=[],
        automations=None,
        sources=[],
        setup=Setup(AGENT, AgentAuthority(), (), Leash()),
    )
    assert [line.text for line in of_step(practised, Step.RESULT)] == [
        "Nothing is written anywhere yet: every action it has is only practised."
    ]
    assert [line.text for line in of_step(reads_only, Step.RESULT)] == [
        "Nothing is written anywhere: an answer is all it produces."
    ]
    assert [line.text for line in of_step(reads_only, Step.DOES)] == [
        "It takes no action: it only reads and answers."
    ]
    assert [line.kind for line in of_step(reads_only, Step.PERSON)] == [Line.NOBODY_WAITS]


# ------------------------------------------------------------------------- the diagnostic
def test_no_line_can_name_a_person_and_every_surface_can_be_said() -> None:
    """The line type has no field an approver could be written into and every channel has words,
    and a type or a table that breaks either is reported.

    What breaks if this is deleted: somebody adds the approver's id to a line to save a lookup, and
    the About tab publishes who holds a capability."""
    assert about_gaps() == ()
    assert set(CHANNEL_WORDS) == set(Channel)

    @dataclass(frozen=True)
    class Named:
        text: str
        approver_id: str

    assert about_gaps(line_type=Named)
    assert about_gaps(channel_words={Channel.EMAIL: "email"})
