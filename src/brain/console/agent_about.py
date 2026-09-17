"""What an agent is for and how it works, as a flow derived from its setup and nothing else.

The owner asked on 2026-09-17 for an About tab anybody opening an agent can read: what starts
it, what it reads, what it does, where a person steps in, where the result goes, and what it
will never do. Written by a person, that is a paragraph that goes on describing the agent after
somebody narrows its ceiling, lowers a rung or stops its automation, and nothing anywhere
notices. So this module writes it, from the channels a run could be carried on, the automations
that are running, the sources the agent is attached to, the ceiling, the tools and the leash,
and every sentence it produces is a line with the thing it is about attached.

**The flow cannot describe what the agent is not set up to do, and that is a property of its
inputs rather than of its wording.** A channel line names only a surface handed in as offered,
a schedule line only an automation handed in as running, a source line only a connector
attached to the agent, and an action line only a tool the ceiling allows, the registry holds
and the largest side effect admits, which is `brain.console.agent_profile.tool_rows` deciding
exactly as `brain.gate.catalogue.project` does. Each line carries the channel, automation,
source, tool, effect and rungs it speaks for, so a property test reads the structure and never
has to trust the sentence. See `THE_FLOW_IS_DERIVED_FROM_THE_SETUP_AND_CANNOT_OUTRUN_IT`.

**A result line names only an effect some action can actually have.** An action held at Shadow
on every record is practised and never carried out, so an agent whose only sending tool is in
Shadow is not described as sending anything anywhere in the flow; its result is that nothing is
written yet. The largest side effect still shapes the "never" sentences, because those are what
the ceiling rules out whatever the tools are. See
`A_RESULT_IS_AN_EFFECT_SOME_ACTION_CAN_HAVE_AND_NEVER_THE_CEILING_ALONE`.

**Approvers are described by the rule that chooses them, and never by name.** Whoever may decide
an approval is somebody holding the action's own capability over the record it targets, which is
`brain.console.role_surfaces.pending_for`, and a list of their names would publish who holds a
capability, which is the People screen's question behind `read:grant`. `FlowLine` has no field a
person could be written into, and `about_gaps` reports one if a later edit adds it. See
`APPROVERS_ARE_DESCRIBED_BY_RULE_AND_NEVER_BY_NAME`.

**What a reader may not be told is an absent step, and the steps are numbered without a gap.**
The route hands this function `None` for the automations of a reader without the Automations
tab's read and `None` for the setup of a reader without the Settings tab's, and the sources are
already narrowed to what `brain.api_routes.reachable_sources` lets this reader be told. A step
with nothing in it is left out and the next one takes its number, so a missing step is not a
count of something withheld. "Nothing starts it" is said only to a reader who could have been
told about an automation, because to anybody else it would be false whenever one is running.

**One sentence is true of every agent and is said to everybody:** it never sees more than the
person it is working for could see themselves, which is `E_run(caller, agent) = E(caller) ∩
agent_ceiling` in words. See `AN_AGENT_NEVER_SEES_MORE_THAN_ITS_CALLER`.

Rejected: computing the flow in the console, which is what the design spike did. It was quicker
to draw, and it put a second reading of the leash, the side effect order and the ceiling into a
TypeScript file that nothing on this side tests, which is the copy that drifts.

Scope: domain logic. Nothing here opens a connection, reads a clock or renders markup.

It is written for the About tab of M27.11.16, and claims no leaf: that leaf closes when the page
exists.

Task ids: none
"""

from __future__ import annotations

import enum
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields
from types import MappingProxyType
from typing import Final

from brain.agents.model import AgentAuthority
from brain.console.agent_profile import (
    ToolRow,
    above,
    clause_words,
    leash_rows,
    rungs_for,
    scope_sentence,
    tool_rows,
)
from brain.console.agent_tabs import RenderProfile
from brain.console.workspace_capabilities import ConnectorRow, Presence
from brain.core.envelope import SideEffect, ToolDefinition
from brain.core.scope import Op
from brain.gate.context import Channel
from brain.gate.injection import AutonomyTier
from brain.gate.leash import Leash
from brain.ops.jobs import hidden_count_fields

# ------------------------------------------------------------------ written-down reasons

#: Why every line is about something handed in.
THE_FLOW_IS_DERIVED_FROM_THE_SETUP_AND_CANNOT_OUTRUN_IT: Final = (
    "A description a person writes goes on describing an agent after its ceiling is narrowed, "
    "a rung is lowered or an automation is stopped. The flow is computed from the channels a run "
    "could be carried on, the automations running, the sources attached, the ceiling, the tools "
    "and the leash, and each line carries what it speaks for, so no line can name a surface, a "
    "schedule, a source or an action the agent does not have."
)

#: Why a result is named from the actions that can happen.
A_RESULT_IS_AN_EFFECT_SOME_ACTION_CAN_HAVE_AND_NEVER_THE_CEILING_ALONE: Final = (
    "A largest side effect of send with no sending tool, or with one held at Shadow on every "
    "record, sends nothing. So where the result goes is said from the actions that could be "
    "carried out, and an agent whose actions are all practised writes nothing yet. What the "
    "ceiling rules out is said separately, as what the agent will never do."
)

#: Why nobody who approves is named.
APPROVERS_ARE_DESCRIBED_BY_RULE_AND_NEVER_BY_NAME: Final = (
    "An approval is decided by somebody holding the action's own capability over the record it "
    "targets, and a list of those people is a list of who holds a capability, which is the "
    "People screen's question behind read:grant. The flow says the rule, and no line has a "
    "field a person could be written into."
)

#: The sentence true of every agent.
AN_AGENT_NEVER_SEES_MORE_THAN_ITS_CALLER: Final = (
    "It never sees more than the person it is working for could see themselves."
)

# ------------------------------------------------------------------------ the vocabulary


class Step(enum.StrEnum):
    """The five steps of the flow, in the order a person reads it."""

    STARTS = "starts"
    READS = "reads"
    DOES = "does"
    PERSON = "person"
    RESULT = "result"


#: Each step's heading.
STEP_TITLES: Final[Mapping[Step, str]] = MappingProxyType(
    {
        Step.STARTS: "What starts it",
        Step.READS: "What it reads",
        Step.DOES: "What it does",
        Step.PERSON: "Where a person steps in",
        Step.RESULT: "Where the result goes",
    }
)


class Line(enum.StrEnum):
    """What one line of the flow says. Closed, so a property can be asked of each kind."""

    #: Somebody asks it on a surface that can carry its answer.
    ASKED = "asked"
    #: A running automation starts it on a schedule.
    SCHEDULED = "scheduled"
    #: No surface carries it and no automation is running, said only where both were visible.
    NOTHING_STARTS = "nothing_starts"
    #: A source it is attached to.
    SOURCE = "source"
    #: A tool it may call that changes nothing.
    READ_TOOL = "read_tool"
    #: The rows its ceiling admits.
    ROWS = "rows"
    #: A tool it may call that changes something, with the rungs it could be held to.
    ACTION = "action"
    #: It has no such tool.
    NO_ACTION = "no_action"
    #: An action that could wait for a person.
    AWAITS_APPROVAL = "awaits_approval"
    #: Who decides such an approval, by rule.
    APPROVER = "approver"
    #: An action held at Shadow on every record, so there is nothing to approve.
    PRACTISED = "practised"
    #: Nothing it does could wait for a person.
    NOBODY_WAITS = "nobody_waits"
    #: An answer goes back on the surface it was asked on.
    ANSWER = "answer"
    #: A scheduled run's result goes to whom it ran as.
    RUN_RESULT = "run_result"
    #: Nothing it does is carried out.
    NOTHING_WRITTEN = "nothing_written"
    #: One effect some action of it can have, and where that leaves the result.
    CARRIED_OUT = "carried_out"


#: How each surface is named in a sentence. Total over `Channel`, which a test holds.
CHANNEL_WORDS: Final[Mapping[Channel, str]] = MappingProxyType(
    {
        Channel.CONSOLE: "the console",
        Channel.LARK: "Lark",
        Channel.WHATSAPP: "WhatsApp",
        Channel.EMAIL: "email",
        Channel.TELEGRAM: "Telegram",
        Channel.API: "the API",
        Channel.SCHEDULER: "the scheduler",
        Channel.WEBHOOK: "a webhook",
        Channel.WIDGET: "a website chat",
        Channel.SLACK: "Slack",
        Channel.TEAMS: "Teams",
    }
)

#: How an answer is laid out on a surface of each profile.
PROFILE_WORDS: Final[Mapping[RenderProfile, str]] = MappingProxyType(
    {
        RenderProfile.CARD: "as a card",
        RenderProfile.ATTACHMENT: "with its files attached",
        RenderProfile.PLAIN: "as plain text",
    }
)

#: What an action with each effect does. `NONE` is absent: a tool that changes nothing reads.
DOING: Final[Mapping[SideEffect, str]] = MappingProxyType(
    {
        SideEffect.DRAFT: "prepares a draft",
        SideEffect.WRITE: "changes a record",
        SideEffect.SEND: "sends a message",
        SideEffect.MONEY: "moves money",
    }
)

#: What a rung means for an action.
RUNG_DOING: Final[Mapping[AutonomyTier, str]] = MappingProxyType(
    {
        AutonomyTier.AUTONOMOUS: "it does this on its own",
        AutonomyTier.ASSISTED: "it gets this ready, and a person approves it first",
        AutonomyTier.SHADOW: "it only practises this, and nothing is carried out",
    }
)

#: Where the result of an action with each effect ends up.
RESULT_OF: Final[Mapping[SideEffect, str]] = MappingProxyType(
    {
        SideEffect.DRAFT: "Anything it prepares stays a draft until a person acts on it.",
        SideEffect.WRITE: "A record it changes is changed in the system it came from.",
        SideEffect.SEND: "A message it sends leaves the building.",
        SideEffect.MONEY: "Money it moves is moved.",
    }
)

#: Each effect as something the agent never does, for the effects above its ceiling.
NEVER_DOING: Final[Mapping[SideEffect, str]] = MappingProxyType(
    {
        SideEffect.DRAFT: "prepares a draft",
        SideEffect.WRITE: "changes a record",
        SideEffect.SEND: "sends anything",
        SideEffect.MONEY: "moves money",
    }
)

APPROVER_RULE: Final = (
    "Whoever approves it holds that action's own permission over that record, because nobody may "
    "approve what they could not do themselves."
)
RUN_RESULT_RULE: Final = (
    "What a scheduled run found is shown only to the person it runs as; anybody else sees that it "
    "ran, when, and how it ended."
)
NOTHING_STARTS_IT: Final = (
    "Nothing starts it: no surface can carry its answers and none of its automations is running."
)
NO_ACTION_TAKEN: Final = "It takes no action: it only reads and answers."
NOBODY_WAITS_FOR: Final = "Nothing it does waits for a person to approve it."
ONLY_AN_ANSWER: Final = "Nothing is written anywhere: an answer is all it produces."
ONLY_PRACTISED: Final = "Nothing is written anywhere yet: every action it has is only practised."

#: Field names that would put a person on a line. See
#: `APPROVERS_ARE_DESCRIBED_BY_RULE_AND_NEVER_BY_NAME`.
NAMES_THAT_WOULD_NAME_A_PERSON: Final[frozenset[str]] = frozenset(
    {"approver", "approvers", "approver_id", "person", "people", "principal", "principal_id", "who"}
)


def _joined(items: Sequence[str], last: str) -> str:
    if len(items) <= 1:
        return "".join(items)
    return f"{', '.join(items[:-1])} {last} {items[-1]}"


# ---------------------------------------------------------------------------- the inputs
@dataclass(frozen=True)
class Offered:
    """A surface a run of this agent by this reader could be carried on, and its layout."""

    channel: Channel
    profile: RenderProfile


@dataclass(frozen=True)
class Scheduled:
    """One of the agent's automations this reader may see.

    `running` is whether it has a next run. A stopped automation starts nothing, and it is handed
    in so that the flow is what decides it says nothing about one.
    """

    automation_id: str
    name: str
    #: The cadence in words, as the Automations tab says it.
    schedule: str
    running: bool


@dataclass(frozen=True)
class Setup:
    """The agent's configuration, for a reader of the Settings tab and nobody else.

    The registry's tools are handed in whole and narrowed here by `tool_rows`, so the flow and
    the Profile decide which tools the agent could call in one place.
    """

    agent_id: str
    authority: AgentAuthority
    registered: tuple[ToolDefinition, ...]
    leash: Leash


# ---------------------------------------------------------------------------- the output
@dataclass(frozen=True)
class FlowLine:
    """One sentence of the flow, with what it speaks for attached.

    `effect` is the side effect the sentence says the agent has, and is None for a line that
    says it has none. `rungs` are `agent_profile.rungs_for` for an action's own target.
    `leash_entry` is whether a leash entry names that target, which is where the page links an
    action: its row on the Profile, or the leash card for a target on the Shadow default.
    """

    kind: Line
    text: str
    channels: tuple[Channel, ...] = ()
    automation_id: str | None = None
    source: str | None = None
    tool: str | None = None
    effect: SideEffect | None = None
    rungs: tuple[AutonomyTier, ...] = ()
    leash_entry: bool | None = None


@dataclass(frozen=True)
class FlowStep:
    """One step with something in it, numbered from one without a gap."""

    number: int
    step: Step
    title: str
    lines: tuple[FlowLine, ...]


@dataclass(frozen=True)
class NeverLine:
    """One thing the agent will never do. `every_agent` marks the sentence true of all of them."""

    text: str
    every_agent: bool


@dataclass(frozen=True)
class AboutFlow:
    """The flow and the "never" sentences, for one reader of one agent."""

    steps: tuple[FlowStep, ...]
    never: tuple[NeverLine, ...]


# ------------------------------------------------------------------------------ the flow
def _starts(
    channels: Sequence[Offered], running: Sequence[Scheduled], automations_visible: bool
) -> list[FlowLine]:
    lines: list[FlowLine] = []
    surfaces = tuple(dict.fromkeys(one.channel for one in channels))
    if surfaces:
        words = [CHANNEL_WORDS[one] for one in surfaces]
        lines.append(
            FlowLine(
                kind=Line.ASKED,
                text=(
                    "Somebody asks it, on a surface that can carry its answer to them: "
                    f"{_joined(words, 'or')}."
                ),
                channels=surfaces,
            )
        )
    lines.extend(
        FlowLine(
            kind=Line.SCHEDULED,
            text=f"{one.name}, on a schedule: {one.schedule}.",
            automation_id=one.automation_id,
        )
        for one in running
    )
    if not lines and automations_visible:
        lines.append(FlowLine(kind=Line.NOTHING_STARTS, text=NOTHING_STARTS_IT))
    return lines


def _reads(attached: Sequence[str], rows: Sequence[ToolRow], setup: Setup | None) -> list[FlowLine]:
    lines = [
        FlowLine(kind=Line.SOURCE, text=f"It reads from {source}.", source=source)
        for source in attached
    ]
    lines.extend(
        FlowLine(
            kind=Line.READ_TOOL,
            text=f"It may call {one.name}, which changes nothing.",
            tool=one.name,
            source=one.source,
            effect=SideEffect.NONE,
        )
        for one in rows
        if one.reads
    )
    if setup is not None:
        lines.append(FlowLine(kind=Line.ROWS, text=scope_sentence(setup.authority.scope)))
    return lines


def _action_text(one: ToolRow, effect: SideEffect, rungs: Sequence[AutonomyTier]) -> str:
    if len(rungs) == 1:
        held = RUNG_DOING[rungs[0]]
    else:
        held = f"depending on the record, {_joined([RUNG_DOING[r] for r in reversed(rungs)], 'or')}"
    return f"{one.name}, which {DOING[effect]}: {held}."


def about_flow(
    *,
    channels: Sequence[Offered],
    automations: Sequence[Scheduled] | None,
    sources: Sequence[ConnectorRow],
    setup: Setup | None,
) -> AboutFlow:
    """The About flow for one reader, from what that reader may be told and nothing else.

    `automations` is None for a reader without the Automations tab's read and `setup` is None
    for a reader without the Settings tab's; the channels and sources are already at this
    reader's reach. See the module docstring for what each step may say and why.
    """
    running = sorted(
        (one for one in automations or () if one.running),
        key=lambda one: (one.name, one.automation_id),
    )
    attached = sorted({one.source for one in sources if one.presence is Presence.ATTACHED})
    rows = () if setup is None else tool_rows(setup.authority, setup.registered)

    drafted: dict[Step, list[FlowLine]] = {step: [] for step in Step}
    drafted[Step.STARTS] = _starts(channels, running, automations is not None)
    drafted[Step.READS] = _reads(attached, rows, setup)

    carried: set[SideEffect] = set()
    if setup is not None:
        acting = [one for one in rows if one.acts]
        linked = {
            one.target: one.configured
            for one in leash_rows(setup.leash, setup.agent_id, (a.name for a in acting))
        }
        waiting: list[FlowLine] = []
        practised: list[FlowLine] = []
        for one in acting:
            effect = one.side_effect
            if effect is None:
                # Unreachable: `acts` is True only for a tool the registry describes. Here so
                # the type says so rather than a cast.
                continue
            rungs = rungs_for(setup.leash, setup.agent_id, one.name)
            drafted[Step.DOES].append(
                FlowLine(
                    kind=Line.ACTION,
                    text=_action_text(one, effect, rungs),
                    tool=one.name,
                    source=one.source,
                    effect=effect,
                    rungs=rungs,
                    leash_entry=linked[one.name],
                )
            )
            if AutonomyTier.ASSISTED in rungs:
                waiting.append(
                    FlowLine(
                        kind=Line.AWAITS_APPROVAL,
                        text=(
                            f"{one.name} waits for a person to approve it before anything is "
                            "carried out."
                            if rungs == (AutonomyTier.ASSISTED,)
                            else f"{one.name} waits for a person to approve it on the records "
                            "where it is held to that."
                        ),
                        tool=one.name,
                        rungs=rungs,
                    )
                )
            if rungs == (AutonomyTier.SHADOW,):
                practised.append(
                    FlowLine(
                        kind=Line.PRACTISED,
                        text=f"{one.name} is only practised, so there is nothing to approve.",
                        tool=one.name,
                        rungs=rungs,
                    )
                )
            else:
                carried.add(effect)
        if not acting:
            drafted[Step.DOES].append(FlowLine(kind=Line.NO_ACTION, text=NO_ACTION_TAKEN))
        drafted[Step.PERSON].extend(waiting)
        if waiting:
            drafted[Step.PERSON].append(FlowLine(kind=Line.APPROVER, text=APPROVER_RULE))
        else:
            drafted[Step.PERSON].append(FlowLine(kind=Line.NOBODY_WAITS, text=NOBODY_WAITS_FOR))
        drafted[Step.PERSON].extend(practised)

    profiles = sorted({one.profile for one in channels}, key=list(RenderProfile).index)
    if profiles:
        drafted[Step.RESULT].append(
            FlowLine(
                kind=Line.ANSWER,
                text=(
                    "An answer goes back to whoever asked, on the surface they asked on, "
                    f"{_joined([PROFILE_WORDS[one] for one in profiles], 'or')}."
                ),
                channels=tuple(dict.fromkeys(one.channel for one in channels)),
            )
        )
    if running:
        drafted[Step.RESULT].append(FlowLine(kind=Line.RUN_RESULT, text=RUN_RESULT_RULE))
    if setup is not None:
        order = list(SideEffect)
        for effect in sorted(carried, key=order.index):
            drafted[Step.RESULT].append(
                FlowLine(kind=Line.CARRIED_OUT, text=RESULT_OF[effect], effect=effect)
            )
        if not carried:
            said = ONLY_PRACTISED if any(one.acts for one in rows) else ONLY_AN_ANSWER
            drafted[Step.RESULT].append(FlowLine(kind=Line.NOTHING_WRITTEN, text=said))

    present = [step for step in Step if drafted[step]]
    return AboutFlow(
        steps=tuple(
            FlowStep(
                number=number,
                step=step,
                title=STEP_TITLES[step],
                lines=tuple(drafted[step]),
            )
            for number, step in enumerate(present, start=1)
        ),
        never=never_lines(setup),
    )


def never_lines(setup: Setup | None) -> tuple[NeverLine, ...]:
    """What the agent will never do: what its ceiling rules out, and what no agent ever does.

    The first two are the Settings tab's content and are absent without it. The largest side
    effect's sentence names every effect `agent_profile.above` it, and the rows sentence names
    the scope's own conditions; an unrestricted scope rules out no row of its own, so it says
    nothing here and the sentence about the caller covers it.
    """
    said: list[NeverLine] = []
    if setup is not None:
        ruled_out = [NEVER_DOING[one] for one in above(setup.authority.max_side_effect)]
        if ruled_out:
            said.append(NeverLine(text=f"It never {_joined(ruled_out, 'or')}.", every_agent=False))
        scope = setup.authority.scope
        if not scope.is_unrestricted():
            conditions = [clause_words(one) for one in scope.clauses if one.op is not Op.ANY]
            said.append(
                NeverLine(
                    text=f"It never reads a row unless {_joined(conditions, 'and')}.",
                    every_agent=False,
                )
            )
    said.append(NeverLine(text=AN_AGENT_NEVER_SEES_MORE_THAN_ITS_CALLER, every_agent=True))
    return tuple(said)


# ------------------------------------------------------------------------- the diagnostic
#: The types a reader of the About tab is handed.
ABOUT_SURFACE: Final[tuple[type, ...]] = (FlowLine, FlowStep, NeverLine, AboutFlow)


def about_gaps(
    *,
    line_type: type = FlowLine,
    surface: Sequence[type] = ABOUT_SURFACE,
    channel_words: Mapping[Channel, str] = CHANNEL_WORDS,
) -> tuple[str, ...]:
    """Everything about the flow that would name a person, count what was withheld, or leave a
    surface unsayable.

    Takes its inputs for `brain.console.workspace.workspace_gaps`' reason.
    """
    gaps = [
        f"{line_type.__name__}.{one.name} would put a person on a line. "
        f"{APPROVERS_ARE_DESCRIBED_BY_RULE_AND_NEVER_BY_NAME}"
        for one in fields(line_type)
        if one.name in NAMES_THAT_WOULD_NAME_A_PERSON
    ]
    gaps.extend(
        f"{found} would tell a reader how much they were not shown"
        for found in hidden_count_fields(surface)
    )
    gaps.extend(
        f"{one.value} has no words, so a flow offered on it cannot be said"
        for one in Channel
        if one not in channel_words
    )
    return tuple(gaps)
