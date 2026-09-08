"""A member's own home, held to the rules that stop a personal surface answering for anybody
else.

Two claims run through the file. The first is that a personal surface has nobody to widen to:
every function is narrowed by a principal that is keyword-only and has no default, and the
reach and the audience handed in have to belong to that person, because a caller that passes a
name in one argument and a reach in another can pass two different people and both answers are
internally consistent.

The second is that ownership admits a row and recall admits the words. A memory is this
person's by authorship, which `brain.memory.formation` says is for the audit question and never
permits a recall, so the statement goes through `may_recall` as well. The discriminating
fixture is somebody reading their own preferences page after the grant the memory was formed
under has been revoked: the row must go, and a page that read ownership as permission would
show them the text (M40.4.1.1).

Real `Turn`s, real `AgentRecord`s, a real signed template through `hand_built`, real
`Learning`s built through `brain.memory.tiers.propose`, real `BudgetRow`s and the real store
enum throughout. The tier boundaries are asserted against `brain.memory.tiers.Tier`'s own
ordering rather than against numbers written here, and the retention dispositions against
`brain.ops.erasure.disposition_of` rather than against a list.

Task ids: M40.2.1.1, M40.2.1.2, M40.2.1.3, M40.2.1.4, M40.2.2.1, M40.2.2.2, M40.2.2.3
Task ids: M40.2.2.4, M40.2.2.5, M40.4.1.1, M40.4.1.2, M40.4.1.3, M40.4.1.4, M40.4.2.1
Task ids: M40.4.2.2, M40.4.2.3
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from brain.agents.model import (
    AgentAudience,
    AgentAuthority,
    AgentRecord,
    AgentViewer,
    visible_to,
)
from brain.agents.template import blank_template, hand_built
from brain.audit.ledger import SUBJECT_KINDS, AuditAction
from brain.channels.adapter import ChannelCapabilities, Feature
from brain.chat.turns import Turn, TurnKind
from brain.console.workspace import Tab, deep_link
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.field_policy import Classification, FieldPolicy, policy_from_rows
from brain.core.lane import Lane
from brain.core.principal import PrincipalKind
from brain.core.scope import Scope
from brain.gate.context import Channel, TrafficClass
from brain.knowledge.visibility import Visibility
from brain.member_activity import (
    KEPT_THROUGH_OPT_OUT,
    MEMBER_SURFACE,
    MY_EXPORT_REASON,
    PERSONAL_CALLS,
    STOPPED_BY_OPT_OUT,
    AgentRequest,
    AgentRow,
    CallableAgent,
    DeletionRequest,
    DeletionRoute,
    DigestForm,
    LearningOptOut,
    MemberError,
    MonthlyActivity,
    PersonalCeiling,
    Provision,
    activity_this_month,
    build_personal_agent,
    callable_agents,
    digest_for_channel,
    export_my_history,
    learned_about_me,
    member_gaps,
    member_notes,
    my_agents,
    open_workspace,
    opt_out,
    personal_audience,
    personal_budget,
    request_agent,
    request_deletion,
    route,
    undo_all,
    undo_one,
    what_is_stored,
)
from brain.memory.correction import Correction, Demotion
from brain.memory.digest import Learning
from brain.memory.formation import Formation
from brain.memory.signals import Signal
from brain.memory.tiers import Change, Tier, propose
from brain.ops.budgets import BudgetLevel, BudgetPeriod, BudgetRow
from brain.ops.erasure import Disposition, disposition_of
from brain.ops.export import ExportReason
from brain.ops.retention import Store
from brain.ops.spend import Actual

NOW = datetime(2027, 2, 9, 9, 0, tzinfo=UTC)
MONTH_AGO = NOW - timedelta(days=30)

ME = "u_me"
THEM = "u_them"

WEB = "web"

READ_NAME = "read:client.name"
READ_VALUE = "read:client.contract_value"

#: A real policy, so the classification a run could reach is derived from rules rather than
#: from a number here. Two rules at two levels, which is what makes the channel offer differ
#: between two agents with different ceilings.
POLICY: FieldPolicy = policy_from_rows(
    [
        ("client", "display_name", READ_NAME, Classification.INTERNAL),
        ("client", "contract_value", READ_VALUE, Classification.RESTRICTED),
    ]
)

#: One surface that carries internal answers and one that carries anything.
INTERNAL_ONLY = ChannelCapabilities(
    channel=Channel.WHATSAPP,
    features=frozenset(),
    max_classification=Classification.INTERNAL,
)
ANYTHING = ChannelCapabilities(
    channel=Channel.CONSOLE,
    features=frozenset({Feature.CARDS}),
    max_classification=Classification.RESTRICTED,
)


# --------------------------------------------------------------------------- fixtures
def holding(*capabilities: str, principal: str = ME) -> EntitlementSet:
    """A caller holding these capabilities company-wide."""
    return EntitlementSet(
        principal_id=principal,
        grants=tuple(
            Grant(capability=Capability(value=one), scope=Scope(clauses=())) for one in capabilities
        ),
    )


def a_viewer(principal: str = ME, *, departments: frozenset[str] = frozenset({WEB})) -> AgentViewer:
    """One person as the audience predicate sees them."""
    return AgentViewer(principal_id=principal, departments=departments)


def an_agent(
    agent_id: str,
    *,
    level: Visibility = Visibility.PERSONAL,
    owner_id: str = ME,
    department: str = "",
    capabilities: tuple[str, ...] = (READ_NAME,),
    disabled_at: datetime | None = None,
) -> AgentRecord:
    """One real agent, so `visible_to` and `entitlement_ceiling` answer for a real record."""
    return AgentRecord(
        agent_id=agent_id,
        display_name=f"Agent {agent_id}",
        persona="Answers questions in the house voice.",
        audience=AgentAudience(level=level, owner_id=owner_id, department=department),
        authority=AgentAuthority(capabilities=tuple(Capability(value=one) for one in capabilities)),
        created_by=THEM,
        disabled_at=disabled_at,
    )


def a_turn(kind: TurnKind, *, at: datetime = NOW, principal: str = ME, text: str = "") -> Turn:
    """One turn, which is the only shape a member's activity can be counted from."""
    return Turn(kind=kind, at=at, principal_id=principal, text=text)


def an_actual(agent_id: str, *, at: datetime = NOW, principal: str = ME) -> Actual:
    """One completed run, built through the real accounting row and all its validators."""
    return Actual(
        principal_id=principal,
        principal_kind=PrincipalKind.HUMAN,
        traffic=TrafficClass.HUMAN_INTERACTIVE,
        department=WEB,
        agent_id=agent_id,
        model="a-model",
        lane=Lane.ANSWER,
        cost_minor=100,
        at=at,
    )


def a_row(
    period: BudgetPeriod, *, subject: str = ME, level: BudgetLevel = BudgetLevel.USER
) -> BudgetRow:
    """One ceiling with an alert fraction on it, so the alert half of the row is real."""
    return BudgetRow(
        level=level,
        subject=subject,
        period=period,
        ceiling_minor=1000,
        version=1,
        author="u_admin",
        effective_from=MONTH_AGO,
        alert_fractions=(0.5,),
    )


def a_learning(
    memory_id: str,
    *,
    change: Change = Change.PREFERENCE,
    principal: str = ME,
    capability: str = READ_NAME,
    formed_at: datetime = NOW,
    evidence: frozenset[Signal] = frozenset({Signal.REASKED}),
    replaced_id: str | None = None,
) -> Learning:
    """One learning, with its tier from `propose` so it cannot claim one of its own."""
    return Learning(
        memory_id=memory_id,
        proposal=propose(change, subject="tone"),
        formation=Formation(
            principal_id=principal,
            capabilities=(Capability(value=capability),),
            scope=Scope(clauses=()),
            ent_hash="0" * 32,
            formed_at=formed_at,
        ),
        evidence=evidence,
        replaced_id=replaced_id,
    )


# --- what was asked this month (M40.2.1.1) ---------------------------------------------


def test_a_month_counts_questions_and_corrections_apart_and_counts_no_answers() -> None:
    """**M40.2.1.1.** Corrections separated out is the leaf, and the reason is what a
    correction is: `brain.chat.turns.Correction` is a person saying an answer was wrong,
    recorded as a signal and never as a fact. A home page that folded them into the question
    count would report somebody's worst week as their busiest.

    Answers are not counted at all, because an answer is the system speaking and counting it
    would double every question.

    The window is half open and both bounds are asserted at one second, because a turn on the
    boundary is what a closed interval puts into two consecutive months, and the second month
    then reports activity the person has already read about.

    Delete this and the two figures become one, or the boundary turn is counted twice.
    """
    turns = [
        a_turn(TurnKind.QUESTION),
        a_turn(TurnKind.QUESTION, at=NOW - timedelta(days=1)),
        a_turn(TurnKind.CORRECTION),
        a_turn(TurnKind.ANSWER),
        a_turn(TurnKind.QUESTION, principal=THEM),
        a_turn(TurnKind.QUESTION, at=MONTH_AGO),
        a_turn(TurnKind.QUESTION, at=MONTH_AGO + timedelta(seconds=1)),
    ]

    counted = activity_this_month(turns, principal_id=ME, since=MONTH_AGO, until=NOW)

    assert counted == MonthlyActivity(
        principal_id=ME,
        covers_from=MONTH_AGO,
        covers_to=NOW,
        questions=3,
        corrections=1,
    )
    assert not {
        name for name in MonthlyActivity.__dataclass_fields__ if name in {"total", "answers"}
    }


# --- agents this person can call (M40.2.1.2) -------------------------------------------


def test_the_agent_split_is_who_stands_behind_one_and_a_disabled_one_is_absent() -> None:
    """**M40.2.1.2.** The split the leaf asks for, read off the audience level. A personal
    agent is theirs to change; a department one and a company one are somebody else's, and a
    third member would put an administrative distinction on a page where it decides nothing.

    `runnable_agent_ids` decides membership rather than `visible_agent_ids`, so a disabled
    agent is absent: a home page offering an agent the selector would not choose is offering
    something that does nothing and the person cannot find out why. A colleague's personal
    agent is absent on the other axis, which is the audience.

    Delete this and either a disabled agent is offered, or every agent reads as provided,
    which hides the ones a person can actually edit.
    """
    mine = an_agent("a_mine")
    departmental = an_agent("a_dept", level=Visibility.DEPARTMENT, owner_id=THEM, department=WEB)
    company = an_agent("a_all", level=Visibility.COMPANY, owner_id=THEM)
    off = an_agent("a_off", disabled_at=NOW)
    theirs = an_agent("a_theirs", owner_id=THEM)

    rows = callable_agents(
        [mine, departmental, company, off, theirs], principal_id=ME, viewer=a_viewer()
    )

    assert rows == (
        CallableAgent(agent_id="a_all", provision=Provision.PROVIDED),
        CallableAgent(agent_id="a_dept", provision=Provision.PROVIDED),
        CallableAgent(agent_id="a_mine", provision=Provision.PERSONAL),
    )
    assert visible_to(theirs.audience, a_viewer()) is False


def test_a_page_rendered_from_somebody_elses_audience_is_refused() -> None:
    """**M40.2.1.2.** The viewer and the principal are two arguments and they can name two
    people, at which point the page lists the agents somebody else can see under this
    person's name. It is the same fault `brain.knowledge.visibility.approve_promotion` refuses
    about an approver and their entitlement.

    The positive half is the matching pair, so this is not passing because the function
    refuses everybody.

    Delete this and one handler with the wrong variable in scope renders a colleague's agents.
    """
    mine = an_agent("a_mine")
    with pytest.raises(MemberError, match="viewer offered"):
        callable_agents([mine], principal_id=ME, viewer=a_viewer(THEM))
    assert callable_agents([mine], principal_id=ME, viewer=a_viewer()) == (
        CallableAgent(agent_id="a_mine", provision=Provision.PERSONAL),
    )


# --- the personal cap (M40.2.1.3) ------------------------------------------------------


def test_a_personal_cap_shows_this_persons_ceilings_and_nobody_elses_budget() -> None:
    """**M40.2.1.3.** The join `brain.console.own_things.own_allowances` makes, in the shape a
    member reads. Three rows go in and one comes out: a department ceiling, somebody else's
    user ceiling and this person's own, and only the last is theirs.

    The alert fractions crossed come through, which is the half a member actually acts on:
    `brain.ops.budgets.AN_ALERT_IS_NOT_A_CEILING` argues the two are separate numbers, and
    this is the screen where the earlier one is useful.

    A period nobody supplied a window for is absent rather than reported at zero, which is
    that module's `A_CEILING_WITH_NO_WINDOW_REPORTS_FULL_HEADROOM`, and it is asserted here
    because the reassuring direction is the one that reaches a person about to start something
    expensive.

    Delete this and a member's page can show a department's headroom as their own.
    """
    rows = [
        a_row(BudgetPeriod.DAY),
        a_row(BudgetPeriod.MONTH),
        a_row(BudgetPeriod.DAY, subject=THEM),
        a_row(BudgetPeriod.DAY, subject=WEB, level=BudgetLevel.DEPARTMENT),
    ]
    spent = [
        an_actual("a_1"),
        an_actual("a_1"),
        an_actual("a_1"),
        an_actual("a_1"),
        an_actual("a_1"),
    ]
    six_hundred = [*spent, an_actual("a_1")]

    shown = personal_budget(
        rows,
        six_hundred,
        principal_id=ME,
        windows={BudgetPeriod.DAY: (MONTH_AGO, NOW)},
    )

    assert shown == (
        PersonalCeiling(
            period=BudgetPeriod.DAY,
            ceiling_minor=1000,
            spent_minor=600,
            headroom_minor=400,
            alerts_crossed=(0.5,),
        ),
    )
    assert not set(PersonalCeiling.__dataclass_fields__) & {"department", "company", "share"}


# --- the agents tab (M40.2.2.1) --------------------------------------------------------


def test_an_agents_tab_counts_this_persons_runs_and_offers_channels_at_the_run_reach() -> None:
    """**M40.2.2.1.** Source, where each one runs, and how often this person used it.

    The channel half is the disclosure decision and it is asserted by making the two agents
    differ only in their ceiling: the agent that can reach a restricted field is not offered a
    surface that carries at most internal, and the agent that cannot is. That is
    `A_CHANNEL_OFFERED_AT_THE_CEILING_DESCRIBES_THE_CEILING` computed at `E_run` rather than
    at the ceiling, and a version that read the caller's own reach would offer both.

    Usage counts this person's own runs only, and a colleague's run of the same agent inside
    the same window is asserted not to move the figure, because a member's page has no basis
    to say whose the number is.

    Delete this and either the channel row describes the agent rather than the run, or the
    usage figure becomes the department's.
    """
    narrow = an_agent("a_narrow", capabilities=(READ_NAME,))
    wide = an_agent("a_wide", capabilities=(READ_NAME, READ_VALUE))
    reach = holding(READ_NAME, READ_VALUE)

    rows = my_agents(
        [narrow, wide],
        [
            an_actual("a_narrow"),
            an_actual("a_narrow"),
            an_actual("a_wide"),
            an_actual("a_narrow", principal=THEM),
            an_actual("a_narrow", at=MONTH_AGO - timedelta(seconds=1)),
        ],
        principal_id=ME,
        viewer=a_viewer(),
        reach=reach,
        capabilities=[INTERNAL_ONLY, ANYTHING],
        policy=POLICY,
        since=MONTH_AGO,
        until=NOW,
    )

    assert rows == (
        AgentRow(
            agent_id="a_narrow",
            provision=Provision.PERSONAL,
            channels=(Channel.WHATSAPP, Channel.CONSOLE),
            uses=2,
        ),
        AgentRow(
            agent_id="a_wide",
            provision=Provision.PERSONAL,
            channels=(Channel.CONSOLE,),
            uses=1,
        ),
    )
    with pytest.raises(MemberError, match="reach offered"):
        my_agents(
            [narrow],
            [],
            principal_id=ME,
            viewer=a_viewer(),
            reach=holding(READ_NAME, principal=THEM),
            policy=POLICY,
            since=MONTH_AGO,
            until=NOW,
        )


# --- opening one into the workspace (M40.2.2.2) ----------------------------------------


def test_a_member_workspace_link_lands_or_returns_nothing_and_never_says_which() -> None:
    """**M40.2.2.2.** The same surface, which means the same function:
    `brain.console.workspace.resolve` is what the console uses, and
    `A_DEEP_LINK_THAT_REFUSES_DIFFERENTLY_IS_AN_ORACLE` only survives being called from here
    because nothing is added between the failure and the caller.

    Four failures and one success, and the four are asserted to be the same `None`: a
    colleague's personal agent, a tab with no grant behind it, a tab with nothing in it, and a
    malformed address. A version that raised on one of them would be an oracle, because the
    address bar is where somebody tries ids.

    Delete this and the member surface grows a reason field, which answers the question the
    link was being used to ask.
    """
    mine = an_agent("a_mine")
    theirs = an_agent("a_theirs", owner_id=THEM)
    reach = holding("read:document", "read:console.existence")
    populated = [Tab.KNOWLEDGE]

    landed = open_workspace(
        deep_link("a_mine", Tab.KNOWLEDGE),
        principal_id=ME,
        reach=reach,
        viewer=a_viewer(),
        records=[mine, theirs],
        populated=populated,
    )
    assert landed is not None
    assert landed.agent_id == "a_mine"
    assert landed.tab.tab is Tab.KNOWLEDGE

    misses = (
        open_workspace(
            deep_link("a_theirs", Tab.KNOWLEDGE),
            principal_id=ME,
            reach=reach,
            viewer=a_viewer(),
            records=[mine, theirs],
            populated=populated,
        ),
        open_workspace(
            deep_link("a_mine", Tab.MEMORY),
            principal_id=ME,
            reach=reach,
            viewer=a_viewer(),
            records=[mine, theirs],
            populated=[Tab.MEMORY],
        ),
        open_workspace(
            deep_link("a_mine", Tab.KNOWLEDGE),
            principal_id=ME,
            reach=reach,
            viewer=a_viewer(),
            records=[mine, theirs],
            populated=[],
        ),
        open_workspace(
            "/knowledge",
            principal_id=ME,
            reach=reach,
            viewer=a_viewer(),
            records=[mine, theirs],
            populated=populated,
        ),
    )
    assert misses == (None, None, None, None)


# --- building a personal agent (M40.2.2.3, M40.2.2.4) ----------------------------------


def test_a_personal_agent_cannot_declare_a_ceiling_its_builder_does_not_reach() -> None:
    """**M40.2.2.3.** "Within the person's own ceiling" is the leaf, and
    `brain.builder.publish.widened_capabilities` is the comparison: a capability the builder
    does not hold at all, and one they hold in a narrower scope, are both a widening.

    Both directions in one pass. The same overlay is built twice, once declaring a capability
    the builder holds and once declaring one they do not, and only the second is refused. The
    refusal names what was declared and not what the person holds.

    A real signed template through `hand_built`, so the pin is checked, the overlay is
    revalidated and the `AgentRecord` comes out of its own constructor: an `AgentRecord`
    assembled here would test this function against a record no install could produce.

    Delete this and a self-service builder writes ceilings nobody could have granted.
    """
    key = "installation-key"
    signed = blank_template(key=key, at=NOW)
    within = hand_built(
        key=key,
        instance_id="my_helper",
        created_by=ME,
        at=NOW,
        overlay={
            "persona": "Helps with hosting questions.",
            "authority.capabilities": [{"value": READ_NAME}],
        },
    )
    beyond = hand_built(
        key=key,
        instance_id="my_bigger_helper",
        created_by=ME,
        at=NOW,
        overlay={
            "persona": "Helps with hosting questions.",
            "authority.capabilities": [{"value": READ_NAME}, {"value": READ_VALUE}],
        },
    )
    reach = holding(READ_NAME)

    built = build_personal_agent(signed, within, principal_id=ME, reach=reach, now=NOW)
    assert built.record.agent_id == "my_helper"

    with pytest.raises(MemberError, match=READ_VALUE):
        build_personal_agent(signed, beyond, principal_id=ME, reach=reach, now=NOW)


def test_a_personal_agent_is_visible_to_nobody_else_and_nothing_here_can_widen_it() -> None:
    """**M40.2.2.4.** Personal audience, owned by the builder, and no parameter by which this
    module produces anything else: `personal_audience` takes a principal and nothing more, and
    `build_personal_agent` has no audience argument at all.

    The visibility half is asserted through `brain.agents.model.visible_to` against a
    colleague who holds every capability in the fixture, because holding capabilities is
    exactly what an audience does not answer to: `AUDIENCE_IS_NOT_AUTHORITY`.

    The blank owner is refused in both spellings, because a personal scope with no owner is
    the unrestricted scope and a form supplies a space rather than an empty string.

    Delete this and an audience parameter arrives on the builder, which is the widening path
    with a friendly name on it.
    """
    key = "installation-key"
    signed = blank_template(key=key, at=NOW)
    instance = hand_built(
        key=key,
        instance_id="my_helper",
        created_by=ME,
        at=NOW,
        overlay={"persona": "Helps with hosting questions."},
    )

    built = build_personal_agent(
        signed, instance, principal_id=ME, reach=holding(READ_NAME), now=NOW
    )
    assert built.record.audience.level is Visibility.PERSONAL
    assert built.record.audience.owner_id == ME
    assert visible_to(built.record.audience, a_viewer(THEM)) is False
    assert visible_to(built.record.audience, a_viewer(ME)) is True
    assert "audience" not in set(inspect.signature(build_personal_agent).parameters)

    for blank in ("", " "):
        with pytest.raises(MemberError, match="no owner"):
            personal_audience(blank)

    with pytest.raises(MemberError, match="installed"):
        build_personal_agent(
            signed, instance, principal_id=THEM, reach=holding(READ_NAME, principal=THEM), now=NOW
        )


# --- asking for one you cannot run (M40.2.2.5) -----------------------------------------


def test_a_request_for_an_agent_you_cannot_see_reads_like_one_that_does_not_exist() -> None:
    """**M40.2.2.5.** A request form is the easiest place to lose
    `A_HIDDEN_AGENT_AND_A_MISSING_AGENT_ARE_ONE_ANSWER`: type an id, be told you cannot have
    that one, and the form has confirmed the agent exists.

    Asserted on the message rather than on the exception type, because two different sentences
    are the oracle even when both are refusals. The invented id and the colleague's personal
    agent produce the same words.

    An agent already runnable is refused with a different sentence, and correctly so: that is
    a fact the person already has.

    Delete this and the request form becomes the catalogue the agent list refuses to be.
    """
    theirs = an_agent("a_theirs", owner_id=THEM)
    mine = an_agent("a_mine")
    wanted = an_agent(
        "a_wanted", level=Visibility.DEPARTMENT, owner_id=THEM, department=WEB, disabled_at=NOW
    )
    records = [theirs, mine, wanted]

    hidden = pytest.raises(MemberError, match="there is no agent")
    with hidden:
        request_agent("a_theirs", records, principal_id=ME, viewer=a_viewer(), at=NOW)
    with hidden:
        request_agent("a_never_existed", records, principal_id=ME, viewer=a_viewer(), at=NOW)

    with pytest.raises(MemberError, match="can already run"):
        request_agent("a_mine", records, principal_id=ME, viewer=a_viewer(), at=NOW)

    asked = request_agent("a_wanted", records, principal_id=ME, viewer=a_viewer(), at=NOW)
    assert asked == AgentRequest(agent_id="a_wanted", requested_by=ME, department=WEB, at=NOW)


def test_a_request_routed_to_no_department_is_refused_rather_than_filed() -> None:
    """**M40.2.2.5.** "Routed to the department admin" needs a department, and a company-wide
    agent's audience carries none. Filing the request anyway puts it in a queue nobody reads,
    which is worse than being told now, and the person believes they asked.

    Whitespace as well as empty, because a department arrives from a form and a bare falsiness
    check passes a space. The naive instant is refused for the same reason a submission's is:
    a queue ordered by how long things have waited is wrong by the host's offset.

    Delete this and a request for a company agent disappears into a department that does not
    exist.
    """
    company = an_agent("a_all", level=Visibility.COMPANY, owner_id=THEM, disabled_at=NOW)
    with pytest.raises(MemberError, match="no department"):
        request_agent("a_all", [company], principal_id=ME, viewer=a_viewer(), at=NOW)

    for blank in ("", " "):
        with pytest.raises(MemberError, match="no department"):
            AgentRequest(agent_id="a_1", requested_by=ME, department=blank, at=NOW)
    for name in ("agent_id", "requested_by"):
        for blank in ("", " "):
            fields = {"agent_id": "a_1", "requested_by": ME, "department": WEB, "at": NOW}
            fields[name] = blank
            with pytest.raises(MemberError, match=f"no {name}"):
                AgentRequest(**fields)  # type: ignore[arg-type]
    with pytest.raises(MemberError, match="no timezone"):
        AgentRequest(agent_id="a_1", requested_by=ME, department=WEB, at=NOW.replace(tzinfo=None))
    assert not {
        name
        for name in AgentRequest.__dataclass_fields__
        if name in {"approver", "decision", "granted"}
    }


# --- what was learnt about me (M40.4.1.1, M40.2.1.4) -----------------------------------


def test_ownership_admits_the_row_and_recall_admits_the_words() -> None:
    """**M40.4.1.1.** The claim the leaf turns on. A memory is this person's by authorship,
    which `brain.memory.formation` records for the audit question and says is never a recall
    permission, so the statement goes through `may_recall` as well as through ownership.

    The discriminating fixture is the same person and the same memory read twice: once while
    they hold the capability it was formed under, and once after it has been revoked. The
    second read returns nothing, and a page that treated ownership as permission would show
    them the words.

    Three more absences in the same pass, each for a different reason: a memory formed from
    somebody else's conversation is not theirs, a gated proposal has not taken effect, and a
    session learning is in neither table. The last two are `may_digest`'s refusals rather than
    a second filter written here.

    Delete this and a preferences page becomes a way of reading back text the reader's current
    grants would refuse them everywhere else.
    """
    mine = a_learning("m_1")
    theirs = a_learning("m_2", principal=THEM)
    gated = a_learning("m_3", change=Change.SCOPE_WIDENING)
    session = a_learning("m_4", change=Change.SESSION_CONTEXT)
    entries = [
        (mine, "prefers short answers"),
        (theirs, "prefers long answers"),
        (gated, "should see the sales scope"),
        (session, "is talking about the Acme brief"),
    ]

    page = learned_about_me(entries, principal_id=ME, reader=holding(READ_NAME), now=NOW)
    assert [one.memory_id for one in page.items] == ["m_1"]
    assert page.items[0].statement == "prefers short answers"
    assert page.items[0].evidence == (Signal.REASKED,)
    assert page.items[0].change is Change.PREFERENCE

    revoked = learned_about_me(entries, principal_id=ME, reader=holding(), now=NOW)
    assert revoked.items == ()


def test_the_count_on_a_preferences_page_counts_the_rows_it_showed() -> None:
    """**M40.2.1.4.** "Count of things learned about this person, each reversible." The count
    is derived from the tuple rather than stored, so it cannot be made to count anything but
    what was rendered; `brain.knowledge.quality`'s rule about a count of what was shown is the
    same argument one surface along.

    Reversibility is on each row as `control_writes`, and both of its values are exercised
    from real learnings: a learning that replaced an earlier memory restores it, and one that
    replaced nothing is demoted. `Correction` has two members and deliberately no third, so
    the field cannot express a removal.

    Delete this and the page grows a stored total, which beside a filtered list is the number
    of things the reader may not see.
    """
    replaced = a_learning("m_1", replaced_id="m_0")
    fresh = a_learning("m_2", formed_at=NOW - timedelta(days=1))
    page = learned_about_me(
        [(replaced, "prefers short answers"), (fresh, "prefers metric units")],
        principal_id=ME,
        reader=holding(READ_NAME),
        now=NOW,
    )

    assert page.learned == 2
    assert page.learned == len(page.items)
    assert [one.control_writes for one in page.items] == [
        Correction.SUPERSEDED,
        Correction.DEMOTED,
    ]
    assert "total" not in set(page.__dataclass_fields__)


def test_a_preferences_page_assembled_from_somebody_elses_reach_is_refused() -> None:
    """**M40.4.1.1.** The reader and the subject are two arguments. Passing a colleague's reach
    with this person's name would decide recall against grants that are not theirs, in the one
    direction that matters: a colleague with a wider set would unlock text this person may not
    read, on a page headed with their own name.

    The positive half is the matching pair.

    Delete this and one handler with the wrong variable in scope reads a memory back at
    somebody else's reach.
    """
    mine = a_learning("m_1")
    with pytest.raises(MemberError, match="reach offered"):
        learned_about_me(
            [(mine, "prefers short answers")],
            principal_id=ME,
            reader=holding(READ_NAME, principal=THEM),
            now=NOW,
        )
    assert (
        learned_about_me(
            [(mine, "prefers short answers")],
            principal_id=ME,
            reader=holding(READ_NAME),
            now=NOW,
        ).learned
        == 1
    )


# --- undo, one and all (M40.4.1.2) -----------------------------------------------------


def test_undo_all_refuses_a_batch_it_cannot_apply_whole() -> None:
    """**M40.4.1.2.** One control per row and an undo-all beside it. The batch is refused
    rather than partially applied, which is `brain.console.reads.notices_for`' argument: the
    interesting item is the one that went missing, and a caller who gets a shorter list than
    they expected cannot tell which.

    Two refusals with different causes. A memory formed from somebody else's conversation,
    where undoing the rest would leave somebody believing they had cleared their page; and the
    same memory twice, where the second mark would be written against a memory the first had
    already marked, because `brain.memory.digest.undo` is idempotent across calls and cannot
    be idempotent inside a list it never sees.

    Idempotence itself is inherited and asserted rather than reimplemented: a memory already
    demoted comes back as an undo that took no effect.

    Delete this and undo-all writes a second correction over a memory something else marked.
    """
    mine = a_learning("m_1", replaced_id="m_0")
    also_mine = a_learning("m_2")
    theirs = a_learning("m_3", principal=THEM)

    done = undo_all([mine, also_mine], principal_id=ME, at=NOW)
    assert [one.memory_id for one in done] == ["m_1", "m_2"]
    assert [one.took_effect for one in done] == [True, True]

    with pytest.raises(MemberError, match="somebody else's conversation"):
        undo_all([mine, theirs], principal_id=ME, at=NOW)
    with pytest.raises(MemberError, match="appears twice"):
        undo_all([mine, mine], principal_id=ME, at=NOW)

    already = Demotion(memory_id="m_2", field="tone", at=NOW)
    repeated = undo_all([also_mine], principal_id=ME, at=NOW, demotions=[already])
    assert repeated[0].took_effect is False
    assert undo_one(also_mine, principal_id=ME, at=NOW, demotions=[already]).took_effect is False


# --- the digest in their own channel (M40.4.1.3) ---------------------------------------


def test_a_digest_travels_with_its_controls_only_where_the_surface_can_draw_one() -> None:
    """**M40.4.1.3.** "In the person's own channel with the same controls." The controls are
    what makes a weekly digest worth sending, so a surface that cannot render one gets a link
    back to the surface that can, and never the same list with the buttons silently absent.

    The decision reads `brain.channels.adapter.Feature.CARDS` off the surface's own declared
    capabilities rather than inferring it from which channel it is, which is what that enum's
    own docstring requires of every caller.

    The other half is that the channel cannot change what is in the digest: the same learnings
    go to both surfaces and the gated one is absent from each, because `may_digest` decides
    that and a delivery decision has no way to reach it.

    Delete this and a digest arrives on a surface that cannot show the undo button, reading as
    a list of things there is nothing to be done about.
    """
    learnings = [a_learning("m_1"), a_learning("m_2", change=Change.SCOPE_WIDENING)]
    reader = holding(READ_NAME)

    rich = digest_for_channel(now=NOW, reader=reader, learnings=learnings, capabilities=ANYTHING)
    plain = digest_for_channel(
        now=NOW, reader=reader, learnings=learnings, capabilities=INTERNAL_ONLY
    )

    assert rich.form is DigestForm.WITH_CONTROLS
    assert plain.form is DigestForm.LINK_ONLY
    assert rich.channel is Channel.CONSOLE
    assert plain.channel is Channel.WHATSAPP
    assert [one.memory_id for one in rich.digest.entries] == ["m_1"]
    assert rich.digest.entries == plain.digest.entries


# --- opting out (M40.4.1.4) ------------------------------------------------------------


def test_an_opt_out_stops_every_tier_above_the_session_and_says_what_it_keeps() -> None:
    """**M40.4.1.4.** "With the cost stated honestly", and the honest part is what it cannot
    do: tier zero lives in a cache keyed by thread and a conversation that cannot remember its
    own previous turn is not a conversation. An opt-out claiming to stop it would be promising
    something the product cannot do.

    The two sets are asserted against `Tier`'s own ordering rather than against a literal list,
    which is what survives a member being added: a tier above the gate is stopped by
    construction. They are also asserted to partition the enum, and the constructor refuses one
    that does not, so an opt-out quietly keeping a tier cannot be built.

    The cost is asserted to be present and to name the thing the person loses, because a switch
    with no stated cost is one somebody flips without being told what stops working.

    Delete this and an opt-out becomes a boolean that reads as off and is not.
    """
    chosen = opt_out(principal_id=ME, at=NOW)

    assert chosen.stops == frozenset({Tier.AUTOMATIC, Tier.PROMOTED, Tier.GATED})
    assert chosen.keeps == frozenset({Tier.SESSION})
    assert chosen.stops == STOPPED_BY_OPT_OUT
    assert chosen.keeps == KEPT_THROUGH_OPT_OUT
    assert chosen.stops | chosen.keeps == frozenset(Tier)
    assert not chosen.stops & chosen.keeps
    assert "deletion" in chosen.cost

    with pytest.raises(MemberError, match="not every tier exactly once"):
        LearningOptOut(
            principal_id=ME,
            at=NOW,
            stops=frozenset({Tier.AUTOMATIC}),
            keeps=frozenset({Tier.SESSION}),
            cost=chosen.cost,
        )


def test_an_opt_out_belonging_to_nobody_or_carrying_no_cost_is_refused() -> None:
    """**M40.4.1.4.** Three validators, and each is reachable from a form. A blank principal
    switches learning off for everybody; a blank cost is the switch with nothing beside it,
    which is exactly what the leaf refuses; a naive instant decides on the host's offset
    whether a learning formed in the gap is kept.

    Whitespace in both string cases, because that is what a tabbed-past field supplies and a
    bare falsiness check passes it.

    Delete this and the honest half of this leaf is one empty string away from being gone.
    """
    good = opt_out(principal_id=ME, at=NOW)
    for blank in ("", " "):
        with pytest.raises(MemberError, match="belonging to nobody"):
            LearningOptOut(
                principal_id=blank,
                at=NOW,
                stops=good.stops,
                keeps=good.keeps,
                cost=good.cost,
            )
        with pytest.raises(MemberError, match="no stated cost"):
            LearningOptOut(principal_id=ME, at=NOW, stops=good.stops, keeps=good.keeps, cost=blank)
    with pytest.raises(MemberError, match="no timezone"):
        LearningOptOut(
            principal_id=ME,
            at=NOW.replace(tzinfo=None),
            stops=good.stops,
            keeps=good.keeps,
            cost=good.cost,
        )


# --- what is stored about me (M40.4.2.1) -----------------------------------------------


def test_what_is_stored_covers_every_store_and_says_what_a_deletion_would_not_reach() -> None:
    """**M40.4.2.1.** In plain language, over every store there is, with the disposition beside
    each: a page saying "this is everything we hold" next to a delete control has to say, on
    the same rows, which of them a deletion does not reach, or the pair makes a promise neither
    of them makes alone.

    Coverage is asserted against `brain.ops.retention.Store` itself and the dispositions
    against `brain.ops.erasure.disposition_of`, so a store added to the system moves both sides
    rather than only the one written here.

    A store that could not be searched is distinguished from an empty one, which is
    `StoreHolding`'s own rule and the reason a subject access request can be honest about being
    incomplete.

    Delete this and a personal page can quietly omit the store nobody reached.
    """
    page = what_is_stored(
        subject_id=ME,
        at=NOW,
        found={Store.MEMORY: 3, Store.CONVERSATION: 12},
        unreachable=[Store.INDEX],
    )

    assert {one.store for one in page.things} == set(Store)
    assert all(one.disposition is disposition_of(one.store) for one in page.things)
    assert page.complete is False
    by_store = {one.store: one for one in page.things}
    assert by_store[Store.MEMORY].items == 3
    assert by_store[Store.INDEX].reached is False
    assert by_store[Store.INDEX].items == 0
    assert by_store[Store.AUDIT].disposition is Disposition.RETAINED
    assert "could not be searched" in by_store[Store.INDEX].line()
    assert "deletion here: erase" in by_store[Store.MEMORY].line()
    assert page.lines()[-1].startswith("incomplete:")


def test_a_page_about_a_blank_subject_is_refused_before_it_reads_complete() -> None:
    """**M40.4.2.1.** `brain.ops.erasure.SubjectAccess` refuses an empty subject and a string
    of spaces is what a form supplies, so a whitespace id produces a complete-looking document
    about a person who does not exist, with every count honestly nought.

    The positive half is the same call with a real subject.

    Delete this and a tabbed-past field yields a subject access page that says nothing is held
    about somebody, which is true of nobody in particular.
    """
    for blank in ("", " "):
        with pytest.raises(MemberError, match="blank subject"):
            what_is_stored(subject_id=blank, at=NOW, found={})
    assert what_is_stored(subject_id=ME, at=NOW, found={}).complete is True


# --- my history and taking it (M40.4.2.2) ----------------------------------------------


def test_a_person_taking_their_own_history_is_recorded_as_a_subject_access_request() -> None:
    """**M40.4.2.2.** The export is `brain.console.own_things.export_own_history`'s, built from
    the narrowed turns. The addition is the row that records it, and the row is the point: the
    difference between a person reading their own transcript and an administrator taking it on
    their behalf is entirely in who is recorded as having asked.

    Requester and subject come from one argument, so they cannot differ, `all_subjects` is
    false and there is no argument that could set it, and the item count is taken off the
    export rather than off the input, so a row cannot report more turns than the narrowing
    produced. The colleague's turn in the input is what proves that last part.

    The reason reference is required in both spellings, because a blank one leaves a row saying
    a copy of a conversation left the system and nothing about why.

    Delete this and a self-service export leaves no trace, or leaves one attributed to whoever
    ran the handler.
    """
    turns = [
        a_turn(TurnKind.QUESTION, text="when does hosting renew"),
        a_turn(TurnKind.ANSWER, text="on the third", principal=THEM),
    ]

    taken, row = export_my_history(
        turns,
        principal_id=ME,
        conversation_id="c_1",
        at=NOW,
        export_id="x_1",
        reason_reference="self-service request",
    )

    assert taken.subject_id == ME
    assert [one.text for one in taken.turns] == ["when does hosting renew"]
    assert row.requested_by == ME
    assert row.subjects == (ME,)
    assert row.all_subjects is False
    assert row.reason is ExportReason.SUBJECT_ACCESS_REQUEST
    assert row.reason is MY_EXPORT_REASON
    assert row.items == len(taken.turns)
    assert row.stores == (Store.CONVERSATION,)

    for blank in ("", " "):
        with pytest.raises(MemberError, match="no written request"):
            export_my_history(
                turns,
                principal_id=ME,
                conversation_id="c_1",
                at=NOW,
                export_id="x_1",
                reason_reference=blank,
            )


# --- asking for a deletion (M40.4.2.3) -------------------------------------------------


def test_a_deletion_request_is_routed_and_carries_no_completion_and_no_eraser() -> None:
    """**M40.4.2.3.** "Routed to the retention policy rather than performed silently." The
    request is a value, the route is a description, and neither is a deletion:
    `brain.ops.erasure.StoreEraser` is a protocol nothing implements and building a second
    path here would make it the only one.

    The route is asserted against `brain.ops.erasure`'s own answers rather than against a list
    written here, and the four tuples are asserted to partition every store, so a store added
    to the system cannot fall out of a page about what will happen.

    There is no completion time, no certificate and no callable parameter, all asserted on the
    shapes rather than in prose, because a field is all it would take.

    Delete this and the member surface acquires a delete button, which is the second deletion
    path in the file that argues against one.
    """
    asked = request_deletion(subject_id=ME, at=NOW)
    where = route(asked)

    assert where.request is asked
    assert set(where.order) == set(Store)
    assert sorted((*where.reaches, *where.rotates_out, *where.retained)) == sorted(where.order)
    assert Store.AUDIT in where.retained
    assert Store.BACKUP in where.rotates_out
    assert Store.CACHE in where.reaches
    assert not set(DeletionRequest.__dataclass_fields__) & {
        "completed_at",
        "certificate",
        "removed",
    }
    assert not set(inspect.signature(route).parameters) & {"eraser", "execute", "perform"}
    assert not set(inspect.signature(request_deletion).parameters) & {"eraser", "holds"}


def test_a_route_that_describes_a_store_twice_or_not_at_all_is_refused() -> None:
    """**M40.4.2.3.** The partition guard, driven with a route that does not partition, because
    a validator no fixture reaches is a validator that survives every mutation.

    Two shapes, and they fail for different reasons: one silent about a store, which tells
    somebody where their request goes and leaves out something it would either empty or keep;
    and one naming a store on two sides, where a page would say a deletion both reaches it and
    does not.

    Delete this and the guard on the page a person reads before asking for their data to be
    removed is never exercised.
    """
    asked = request_deletion(subject_id=ME, at=NOW)
    whole = route(asked)

    with pytest.raises(MemberError, match="silent about"):
        DeletionRoute(
            request=asked,
            order=whole.order[:-1],
            reaches=whole.reaches,
            rotates_out=whole.rotates_out,
            retained=whole.retained,
        )
    with pytest.raises(MemberError, match="do not add up"):
        DeletionRoute(
            request=asked,
            order=whole.order,
            reaches=whole.reaches,
            rotates_out=(*whole.rotates_out, Store.AUDIT),
            retained=whole.retained,
        )


def test_a_deletion_request_naming_nobody_or_dated_naively_is_refused() -> None:
    """**M40.4.2.3.** A request with no subject is a request to delete everybody, and a form
    supplies a string of spaces rather than an empty one. A naive instant orders wrongly
    against the holds and the backups it will be compared with.

    Both spellings and both validators, plus the positive case, so this is not passing because
    the constructor refuses everything.

    Delete this and one whitespace character reaches `brain.ops.erasure.erase`, whose own
    check is `if not self.subject_id`.
    """
    for blank in ("", " "):
        with pytest.raises(MemberError, match="no subject"):
            request_deletion(subject_id=blank, at=NOW)
    with pytest.raises(MemberError, match="no timezone"):
        request_deletion(subject_id=ME, at=NOW.replace(tzinfo=None))
    assert request_deletion(subject_id=ME, at=NOW).subject_id == ME


# --- the diagnostic and the notes ------------------------------------------------------


def test_the_diagnostic_reports_every_way_this_surface_could_answer_for_somebody_else() -> None:
    """The deployment check is green and that proves nothing, so every branch is driven with a
    constructed input. `brain.console.own_things.own_gaps` records the same argument about its
    own parameters.

    The first branch is `own_gaps` reused rather than reimplemented, and it is exercised with a
    function that takes `everyone` beside its principal, which is how a personal surface
    actually becomes a directory: not by deleting the principal, but by somebody adding a
    parameter for an administrative screen.

    Five more: a hidden count, a budget that is not this person's, a request carrying a
    completion, a request carrying a decision, and a route that could be handed an eraser.

    Delete this and `member_gaps` becomes a function that returns an empty tuple.
    """
    assert member_gaps() == ()

    def directory(rows: list[str], *, principal_id: str, everyone: bool = False) -> None:
        """A personal function with the parameter that makes it an administrative one."""

    def performing(one: object, *, eraser: object) -> None:
        """A request path that could carry the request out."""

    def per_tier(*, principal_id: str, at: datetime, tier: Tier) -> None:
        """An opt-out that asks which tiers matter."""

    @dataclass(frozen=True)
    class Counting:
        hidden_count: int = 0

    @dataclass(frozen=True)
    class Wider:
        department: str = ""

    @dataclass(frozen=True)
    class Performed:
        completed_at: str = ""

    @dataclass(frozen=True)
    class Deciding:
        approver_id: str = ""

    assert "everyone" in member_gaps(personal=[directory])[0]
    assert member_gaps(surface=[Counting]) == (
        "Counting.hidden_count would tell a reader how much they were not shown",
    )
    assert len(member_gaps(budget_type=Wider)) == 1
    assert len(member_gaps(request_types=[Performed])) == 1
    assert len(member_gaps(deciding_types=[Deciding])) == 1
    assert "eraser" in member_gaps(routing=[performing])[0]
    assert "takes a tier" in member_gaps(opt=per_tier)[0]
    assert set(PERSONAL_CALLS) <= set(PERSONAL_CALLS)
    assert MonthlyActivity in MEMBER_SURFACE


def test_the_two_declined_leaves_name_the_field_that_is_missing() -> None:
    """The findings `member_notes` reports, asserted against the modules they are about so a
    note cannot go stale silently in either direction.

    A `Turn` carries no thread and no channel, which is why threads across surfaces cannot be
    assembled here; and `AuditAction` has no member meaning a read, with `SUBJECT_KINDS`
    carrying nothing for a personnel record, which is why the HR question cannot be answered
    from the ledger. Both are asserted on the real vocabularies rather than on the sentence.

    Delete this and the day somebody adds either field, the notes keep saying it is missing and
    the two leaves stay unclaimed for a reason that stopped being true.
    """
    assert not set(Turn.__dataclass_fields__) & {"thread_id", "conversation_id", "channel"}
    assert not {one for one in AuditAction if "read" in one.value}
    assert "record" not in SUBJECT_KINDS
    assert len(member_notes()) == 2
    assert "no thread id and no channel" in member_notes()[0]
    assert "none of" in member_notes()[1]
