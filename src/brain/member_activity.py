"""A member's own home: what they asked, what they can call, what was learnt, what is held.

This is the reading half of `brain.console.own_things` turned round to face the person it is
about, plus the four controls a person operates on themselves. It reuses that module's
predicate rather than writing a second one, for the reason stated there at length: "their own"
is a permission claim and not a filter, and a second construction of it is a second place for
the empty-owner check to be missing.

**There is no basis here and there is nowhere to put one.** `brain.console.workspace.Basis`
exists because an agent's front page is about an agent and a reader may legitimately be shown
everybody's figures on it. Every figure on this surface is about one person, that person is in
the signature of every function, and a basis could therefore only ever widen it. That is
`brain.console.own_things`' rejected-basis argument unchanged, and `member_gaps` reads these
signatures through `own_gaps` rather than restating the rule.

**Ownership admits the row and recall admits the words.** M40.4.1.1 asks for every preference
learned with the evidence that produced it, and those are two disclosures rather than one.
Which memories are this person's is authorship, which is `Formation.principal_id`, and
`brain.memory.formation` says in its own comment that the field is for the audit question and
never permits a recall. So the statement goes through `brain.console.reach_view.readable`,
which asks `may_recall` about the reader as they are now: somebody who formed a memory while
holding a grant they have since lost sees the row disappear rather than reading its words back
off their own preferences page. See `OWNERSHIP_ADMITS_THE_ROW_AND_RECALL_ADMITS_THE_WORDS`.

**The evidence line is the signal kinds and it cannot be anything else.**
`brain.memory.digest.EVIDENCE_NAMES_WHAT_WAS_NOTICED_AND_NEVER_WHOSE_CONVERSATION_IT_WAS` is
the rule, and the argument that this is the person's own page does not lift it: `Learning`
carries a `frozenset[Signal]` and no observations, so there is no conversation id here to
show, and adding one would put a transcript pointer on a record that refuses to hold one. What
that costs is stated there: the reader cannot follow the evidence from here, and the audit view
is the surface built to hold that.

**The preferences page is `may_digest`'s filter and not a second one.** A tier-three learning
has not taken effect, `brain.memory.digest.Learning` says so in its own docstring, and a page
headed "what the system has learnt about you" listing proposals waiting for a person would be
describing something that is not true yet. `may_digest` refuses those on two independent
grounds and refuses session memory as well, which is the right answer here for a second reason:
a session memory is in neither table and `reach_view.provenance_of` refuses it, so a viewer
showing one would be showing something nobody can go back and look at.

**Opting out cannot stop a conversation remembering itself, and saying it does is the failure.**
Tier zero lives in a cache keyed by thread and dies with the conversation, and a conversation
that cannot remember its own previous turn is not a conversation. So `opt_out` stops everything
above the session and says which tier it keeps, on the value rather than in a footnote. It also
removes nothing: what has already been learnt is a deletion request, which is a different
control with a different route. See `OPTING_OUT_CANNOT_STOP_A_CONVERSATION_REMEMBERING_ITSELF`.

**A deletion request is routed and a route is not a delete.** `brain.ops.retention` and
`brain.ops.erasure` own the order, the dispositions and the certificate; `StoreEraser` is a
protocol nothing implements and that module says so. So this builds a request and reports where
it would go, there is no callable parameter an eraser could arrive through, and `member_gaps`
reads the signature to say so. See `A_DELETION_REQUEST_IS_ROUTED_AND_A_ROUTE_IS_NOT_A_DELETE`.

Rejected: reading legal holds when the request is made. `brain.ops.erasure.erase` refuses a
held subject outright and it is right to, and checking here as well would be a second
evaluation of the same thing at the wrong moment: a hold placed between the request and the run
is missed by a request that checked at request time and reported the route as clear. It would
also print the existence of a dispute onto a self-service screen. See
`A_HOLD_READ_AT_REQUEST_TIME_IS_A_HOLD_READ_TOO_EARLY`.

Rejected: a backup horizon on the route. `brain.ops.erasure.backup_horizon` is measured from
when a deletion completed, deliberately, because the backup taken between the request and the
completion still holds the data. A date computed from the request would be earlier than the
truth, which is the direction that makes a document wrong, so the route carries no date at all
and the certificate is where one appears.

Scope: domain logic. Nothing here opens a connection, delivers anything or reads a clock; `now`
and the windows are parameters, as in every module this one calls.

**Two leaves of M40 are not claimed and both are named in the body above and below.** M40.2.1.5
asks for recent threads continued from any channel: `brain.chat.turns.Turn` carries a principal,
an instant and an agent, and no thread id and no channel, so there is nothing to group by and
nothing to say which surface a turn arrived on. `brain.tables.chat.ConversationRow` is declared
and nothing in `src` queries it. M40.4.2.4 asks which agents have read this person's HR record
from the audit ledger: `brain.audit.ledger.AuditAction` is closed, pinned by an invariant test,
and none of its eight members is a read; `SUBJECT_KINDS` has no member for a personnel record;
and an ordinary entitled read is in the trace rather than in the ledger. Both need a decision
and a migration rather than a surface. `member_notes` reports them.

Task ids: M40.2.1.1, M40.2.1.2, M40.2.1.3, M40.2.1.4, M40.2.2.1, M40.2.2.2, M40.2.2.3
Task ids: M40.2.2.4, M40.2.2.5, M40.4.1.1, M40.4.1.2, M40.4.1.3, M40.4.1.4, M40.4.2.1
Task ids: M40.4.2.2, M40.4.2.3
"""

from __future__ import annotations

import enum
import inspect
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from brain.agents.model import (
    AgentAudience,
    AgentRecord,
    AgentViewer,
    entitlement_ceiling,
    runnable_agent_ids,
    visible_agent_ids,
)
from brain.agents.template import EffectiveAgent, SignedManifest, TemplateInstance, materialise
from brain.builder.publish import widened_capabilities
from brain.channels.adapter import ChannelCapabilities, Feature
from brain.chat.turns import Turn, TurnKind
from brain.console.own_things import delete_own_memory, export_own_history, is_own, own_gaps
from brain.console.own_things import own_allowances as _own_allowances
from brain.console.reach_view import readable
from brain.console.workspace import Landing, Tab, resolve
from brain.console.workspace_capabilities import offered_channels, run_reach
from brain.core.entitlement import EntitlementSet
from brain.core.field_policy import FieldPolicy
from brain.gate.context import Channel
from brain.knowledge.visibility import Visibility
from brain.memory.correction import Correction, Demotion, Supersession
from brain.memory.digest import (
    DIGEST_PERIOD,
    Learning,
    Undo,
    WeeklyDigest,
    may_digest,
    memory_item,
    weekly_digest,
)
from brain.memory.signals import Signal
from brain.memory.tiers import Change, Tier
from brain.ops.budgets import BudgetPeriod, BudgetRow
from brain.ops.erasure import (
    Disposition,
    StoreHolding,
    assemble,
    deletion_order,
    disposition_of,
    erasure_targets,
)
from brain.ops.export import ConversationExport, ExportAudit, ExportReason
from brain.ops.jobs import hidden_count_fields
from brain.ops.retention import DataClass, Store
from brain.ops.spend import Actual

# ------------------------------------------------------------------ written-down reasons
#: Why an agent nobody has shown this person is not one they may ask about.
AN_AGENT_SOMEBODY_CANNOT_SEE_IS_NOT_ONE_THEY_MAY_ASK_FOR: Final = (
    "brain.agents.model.A_HIDDEN_AGENT_AND_A_MISSING_AGENT_ARE_ONE_ANSWER says a hidden "
    "agent and one that does not exist produce the same answer, and a request form is the "
    "easiest place to lose that: type an id, get 'you cannot have this one', and the form "
    "has just confirmed the agent exists. So a request is admitted only for an agent "
    "visible_agent_ids already returns, and an id outside that set is refused with the same "
    "sentence as an id nobody ever created. What a person may request is what they can "
    "already see and cannot yet run, which is a gap they are looking at rather than a "
    "catalogue they are guessing against."
)

#: Why a personal agent's ceiling is checked against its builder's own reach.
A_PERSONAL_CEILING_MEANS_NOTHING_UNTIL_THE_AGENT_IS_SHARED: Final = (
    "E_run is the caller's reach intersected with the ceiling, so a ceiling wider than its "
    "builder confers nothing while that builder is the only caller, and refusing one looks "
    "like ceremony. It stops looking like ceremony the moment the agent is handed to "
    "somebody else or promoted, because the ceiling then narrows a wider caller by whatever "
    "was declared rather than by what its author could see. "
    "brain.builder.publish.A_BUILDER_IS_WHERE_A_CEILING_CAN_OUTGROW_ITS_AUTHORS_REACH is the "
    "same argument, and widened_capabilities is its answer, so this calls that rather than "
    "comparing grants here."
)

#: Why a personal memory page asks both questions.
OWNERSHIP_ADMITS_THE_ROW_AND_RECALL_ADMITS_THE_WORDS: Final = (
    "Which memories are this person's is authorship: brain.memory.formation records the "
    "principal who was asking and its own comment says the field answers the audit question "
    "and never permits a recall. Whether the words may be shown is may_recall, which asks "
    "whether whoever is here now still reaches what the memory was formed from. A page that "
    "read ownership as permission would show somebody the text of a memory formed while they "
    "held a grant that has since been revoked, which is the exact disclosure "
    "brain.memory.formation exists to prevent arriving through the one screen where it looks "
    "most reasonable."
)

#: Why the session tier survives an opt-out and the value says so.
OPTING_OUT_CANNOT_STOP_A_CONVERSATION_REMEMBERING_ITSELF: Final = (
    "Tier zero is the session: brain.memory.formation.session_key puts it in a cache keyed "
    "by thread and principal and session_expiry ends it when the conversation does. A "
    "conversation that cannot remember its own previous turn is not a conversation, it is a "
    "sequence of unrelated questions, so an opt-out that claimed to stop tier zero would be "
    "promising something the product cannot do and the person would discover it by being "
    "asked the same question twice. The tiers stopped and the tier kept are both on the "
    "value, derived from Tier's own ordering, so a tier added later is stopped rather than "
    "quietly outside the list."
)

#: Why this module builds a request rather than a deletion.
A_DELETION_REQUEST_IS_ROUTED_AND_A_ROUTE_IS_NOT_A_DELETE: Final = (
    "brain.ops.erasure owns deletion: the order sources before copies, the dispositions that "
    "say which stores a deletion does not reach at all, the refusal under a legal hold and "
    "the certificate. Its executor, StoreEraser, is a protocol nothing implements, which "
    "that module states plainly. A second deletion path built on a member screen would "
    "therefore be the only one, written where the argument for the ordering is not, and it "
    "would produce a screen saying somebody's data had gone. So this returns where a request "
    "goes and what a deletion would not reach, there is no callable parameter an eraser "
    "could arrive through, and nothing here has a completion time or a certificate on it."
)

#: Why a hold is read when the deletion runs and not when it is asked for.
A_HOLD_READ_AT_REQUEST_TIME_IS_A_HOLD_READ_TOO_EARLY: Final = (
    "brain.ops.erasure.erase refuses a held subject outright and names the holds. Checking "
    "again here would be a second evaluation of one fact at the wrong moment: a hold placed "
    "between the request and the run is missed, and the route this surface printed said the "
    "request was clear. The stale copy is the reassuring one, which is the direction that "
    "matters. It would also put the existence of a dispute on a self-service page, where the "
    "person reading it is the subject of it."
)

#: Why a channel that cannot draw a control gets a link instead of a quieter digest.
A_DIGEST_WITH_ITS_CONTROLS_MISSING_READS_AS_A_DIGEST_WITH_NOTHING_TO_UNDO: Final = (
    "The undo button is the whole point of a weekly digest: brain.memory.digest argues that "
    "a week is defensible because a memory formed at the start of one is still above the "
    "recall floor at the end, which only matters if pressing the button changes something. A "
    "surface that cannot render a control therefore gets a link back to the one that can, "
    "and never the same list with the buttons silently absent, because a list of learnings "
    "with nothing beside them reads as a list of things there is nothing to be done about. "
    "brain.console.agent_tabs.RenderProfile makes the same choice about layout, and the "
    "decision is per delivery rather than per row for the same reason it is there: a control "
    "beside one row and not the next says nothing a reader can act on."
)


class MemberError(Exception):
    """A personal surface was asked to act for somebody other than the person it is about.

    Outside `brain.core.errors` for the reason `brain.console.own_things.OwnThingsError` is:
    those five outcomes describe an answer given to somebody who asked a question, and this
    is a refusal to operate a control on a personal screen.
    """


def _assert_own_reach(offered: EntitlementSet, principal_id: str, what: str) -> None:
    """Refuse a reach belonging to somebody other than the person this surface is about.

    The check `brain.knowledge.visibility.approve_promotion` makes about an approver, and it
    is here for the same reason: a caller that passes a name in one argument and a reach in
    another can pass two different people, and the function then answers confidently for
    whichever the renderer believed. It is the kind of mistake that happens once, in a
    handler that had the wrong variable in scope, and it is invisible afterwards because both
    answers are internally consistent.
    """
    if offered.principal_id != principal_id:
        msg = (
            f"the reach offered belongs to {offered.principal_id!r} and {what} is "
            f"{principal_id!r}'s; a personal surface assembled from two people is one "
            "person's page showing another person's rows"
        )
        raise MemberError(msg)


def _assert_own_viewer(viewer: AgentViewer, principal_id: str) -> None:
    """The same check for the audience side, which is a different object and the same fault."""
    if viewer.principal_id != principal_id:
        msg = (
            f"the viewer offered is {viewer.principal_id!r} and this page is "
            f"{principal_id!r}'s; an audience answered for one person and rendered for "
            "another lists agents somebody else can see"
        )
        raise MemberError(msg)


# ------------------------------------------------ what was asked this month (M40.2.1.1)
@dataclass(frozen=True)
class MonthlyActivity:
    """What this person asked in one window, with corrections kept apart (M40.2.1.1).

    Two figures and no third. There is no total, because a total of the two is a number
    somebody divides to get a correction rate, and a rate on one person's month is a
    performance figure assembled out of a home page; and no count of answers, because an
    answer is the system speaking and counting it would double every question.

    The window is carried so the figures can be labelled. Two instants are not a count of
    anything, which is `brain.memory.digest.WeeklyDigest`' argument about the same pair.
    """

    principal_id: str
    covers_from: datetime
    covers_to: datetime
    #: Questions this person asked inside the window.
    questions: int
    #: Corrections they made, which are the questions that went wrong.
    corrections: int


def activity_this_month(
    turns: Iterable[Turn],
    *,
    principal_id: str,
    since: datetime,
    until: datetime,
) -> MonthlyActivity:
    """Questions and corrections for one person over one window (M40.2.1.1).

    Corrections are separated rather than folded in, which is the leaf, and the reason is
    what a correction is: `brain.chat.turns.Correction` is a person saying an answer was
    wrong, recorded as a signal and never as a fact, and a home page that added it to the
    question count would report somebody's worst week as their busiest.

    Narrowed by `brain.console.own_things.own_history`'s predicate through `is_own`, so this
    and a query narrowed by the same scope agree about what personal means.

    The window is half open, `(since, until]`, exactly as `brain.memory.digest.weekly_digest`'
    is: a closed interval puts a turn on the boundary into two consecutive months, and the
    second month reports activity the person already read about.

    Turns from the future fall outside rather than at the top. Clock skew between a channel
    and a reader is ordinary, and a month whose first question has not happened yet is the
    strangest thing to hand somebody on the first.
    """
    counted = [
        one for one in turns if is_own(principal_id, one.principal_id) and since < one.at <= until
    ]
    return MonthlyActivity(
        principal_id=principal_id,
        covers_from=since,
        covers_to=until,
        questions=sum(1 for one in counted if one.kind is TurnKind.QUESTION),
        corrections=sum(1 for one in counted if one.kind is TurnKind.CORRECTION),
    )


# ------------------------------------------------- agents this person can call (M40.2.1.2)
class Provision(enum.StrEnum):
    """Who stands behind an agent this person can call. Two, as M40.2.1.2 asks.

    `PROVIDED` covers a department agent and a company one alike, and that is a decision
    rather than an omission: the split a member cares about on their own home page is
    between what is theirs to change and what somebody else answers for, and a third member
    would put an administrative distinction on a personal screen where it decides nothing.
    """

    #: Somebody else stands behind it. A department's or the company's.
    PROVIDED = "provided"
    #: Theirs. Personal audience, stewarded by them.
    PERSONAL = "personal"


def provision_of(record: AgentRecord) -> Provision:
    """Which side of the split this agent falls on, from its audience level alone.

    **The owner is deliberately not checked here and that is not an oversight.**
    `brain.agents.model.visible_to` admits a personal agent only where the viewer's own row
    satisfies `owner_id = <the audience's owner>`, so by the time a record reaches this
    function through `callable_agents` the owner is already known to be this person, and a
    second comparison would be a branch no input could reach. The level is the whole of the
    distinction; `brain.connectors.manifest.ProjectedEntity` records removing the same
    duplicate for the same reason.
    """
    return (
        Provision.PERSONAL if record.audience.level is Visibility.PERSONAL else Provision.PROVIDED
    )


@dataclass(frozen=True)
class CallableAgent:
    """One agent this person can start, and who stands behind it (M40.2.1.2)."""

    agent_id: str
    provision: Provision


def callable_agents(
    records: Iterable[AgentRecord],
    *,
    principal_id: str,
    viewer: AgentViewer,
) -> tuple[CallableAgent, ...]:
    """The agents this person can call, split by who provides them (M40.2.1.2).

    `brain.agents.model.runnable_agent_ids` decides which, because it is the set
    `brain.gate.select.select_agent` chooses between: visible and enabled. A home page
    listing an agent the selector would not choose is a page offering something that does
    nothing, and the person has no way to find out why.

    Sorted by id, so two readings of an unchanged catalogue are the same list. Returns what
    they can call and says nothing about the rest, per
    `brain.agents.model.A_HIDDEN_AGENT_AND_A_MISSING_AGENT_ARE_ONE_ANSWER`.
    """
    _assert_own_viewer(viewer, principal_id)
    kept = list(records)
    runnable = runnable_agent_ids(kept, viewer)
    return tuple(
        CallableAgent(agent_id=one.agent_id, provision=provision_of(one))
        for one in sorted(kept, key=lambda one: one.agent_id)
        if one.agent_id in runnable
    )


# --------------------------------------------- the personal cap and what went (M40.2.1.3)
@dataclass(frozen=True)
class PersonalCeiling:
    """One of this person's own ceilings and what has gone against it (M40.2.1.3).

    **No department, no company and no share.** Each of those is somebody else's budget
    seen from a personal page, and a share in particular is this figure divided by a wider
    one, which hands the reader the wider one. `member_gaps` reads the fields of this type
    rather than trusting this paragraph.

    `alerts_crossed` is `brain.ops.budgets.Allowance.alerts` carried through rather than
    recomputed, so a person is told they are near the cap on the same fractions the refusal
    path uses. `AN_ALERT_IS_NOT_A_CEILING` is that module's argument for why the two are
    separate numbers, and this is the screen where the earlier one is useful.
    """

    period: BudgetPeriod
    ceiling_minor: int
    spent_minor: int
    headroom_minor: int
    #: The alert fractions already crossed, in the row's own order.
    alerts_crossed: tuple[float, ...]


def personal_budget(
    rows: Iterable[BudgetRow],
    actuals: Sequence[Actual],
    *,
    principal_id: str,
    windows: Mapping[BudgetPeriod, tuple[datetime, datetime]],
) -> tuple[PersonalCeiling, ...]:
    """This person's own ceilings and what they have spent against each (M40.2.1.3).

    `brain.console.own_things.own_allowances` does the join, and it is called rather than
    reimplemented: it already drops a row at any level other than the user's, a row
    belonging to somebody else, and a row whose period nobody supplied a window for. That
    last one matters most and its argument is `A_CEILING_WITH_NO_WINDOW_REPORTS_FULL_HEADROOM`
    in that module: a ceiling paired with no measured spend reads as full headroom on the one
    screen somebody checks before starting something expensive.

    What is added is the shape. An `Allowance` carries a whole `BudgetRow`, which carries the
    author who wrote the ceiling and the reason they gave; those are an administrator's
    decision rendered on a member's page, and the member's question is how much is left.

    Order follows `own_allowances`, which follows the rows, which `brain.ops.budgets.
    user_allowances` returns daily first. That pair is what a person reads.
    """
    return tuple(
        PersonalCeiling(
            period=one.row.period,
            ceiling_minor=one.row.ceiling_minor,
            spent_minor=one.spent_minor,
            headroom_minor=one.headroom_minor,
            alerts_crossed=one.alerts,
        )
        for one in _own_allowances(rows, actuals, principal_id=principal_id, windows=windows)
    )


# ------------------------------------------------------- the agents tab (M40.2.2.1)
@dataclass(frozen=True)
class AgentRow:
    """One agent on this person's own agents tab (M40.2.2.1).

    Source, where it runs and how often this person used it, which is what the leaf names.
    `uses` is this person's own runs and there is no basis field beside it, because there is
    no wider figure on this surface to be told apart from; see the module docstring.
    """

    agent_id: str
    provision: Provision
    #: The channels this person's own run could actually be carried on, in declared order.
    channels: tuple[Channel, ...]
    #: How many times this person ran it inside the window.
    uses: int


def my_agents(
    records: Sequence[AgentRecord],
    actuals: Sequence[Actual],
    *,
    principal_id: str,
    viewer: AgentViewer,
    reach: EntitlementSet,
    capabilities: Sequence[ChannelCapabilities] = (),
    policy: FieldPolicy,
    since: datetime,
    until: datetime,
    now: datetime | None = None,
) -> tuple[AgentRow, ...]:
    """This person's agents, where each runs and how often they used it (M40.2.2.1).

    **The channels are computed at `E_run(caller, agent)` and never at the agent's ceiling**,
    by `brain.console.workspace_capabilities.offered_channels` through `run_reach`, which is
    the console's one route into the intersection. `A_CHANNEL_OFFERED_AT_THE_CEILING_
    DESCRIBES_THE_CEILING` is that module's argument and it holds harder here: a member
    offered a channel their own run would be refused on reads it as the product being broken,
    and the offer is also a statement about how sensitive the agent's widest reach is.

    Usage counts this person's own runs only. There is no basis parameter, so there is no
    argument by which this becomes a list of what a department did through each agent.

    Ordered by uses and then by id, so the agent somebody actually works with is at the top
    and two readings of an unchanged ledger are the same list.
    """
    _assert_own_reach(reach, principal_id, "this page")
    _assert_own_viewer(viewer, principal_id)
    runnable = runnable_agent_ids(records, viewer)
    tally: dict[str, int] = dict.fromkeys(runnable, 0)
    for one in actuals:
        if one.agent_id in tally and one.principal_id == principal_id and since <= one.at <= until:
            tally[one.agent_id] += 1
    rows = [
        AgentRow(
            agent_id=one.agent_id,
            provision=provision_of(one),
            channels=offered_channels(run_reach(reach, one), capabilities, policy, now),
            uses=tally[one.agent_id],
        )
        for one in records
        if one.agent_id in runnable
    ]
    return tuple(sorted(rows, key=lambda one: (-one.uses, one.agent_id)))


# ------------------------------------------- opening one into the workspace (M40.2.2.2)
def open_workspace(
    link: str,
    *,
    principal_id: str,
    reach: EntitlementSet,
    viewer: AgentViewer,
    records: Iterable[AgentRecord],
    populated: Iterable[Tab] = (),
    now: Any = None,
) -> Landing | None:
    """Where an agent link lands for this member, or `None` (M40.2.2.2).

    **The same surface, which means the same function.**
    `brain.console.workspace.resolve` is what the administrator's console uses and it is what
    this calls: a second resolver would be a second answer to which tabs exist, and the
    permissive copy is the one that ships. `A_DEEP_LINK_THAT_REFUSES_DIFFERENTLY_IS_AN_ORACLE`
    is why every failure is the same `None`, and that property survives being called from
    here only because nothing is added between the failure and the caller.

    The bound is this person's own reach and this person's own audience, both checked to
    belong to them before anything is read. `visible_agent_ids` answers the audience question
    because that is the module that owns it, so a personal agent belonging to a colleague is
    absent for somebody holding every capability in the deployment.

    Returns `None` and never a reason. There is no parameter here that could ask for one and
    no second return value that could carry one.
    """
    _assert_own_reach(reach, principal_id, "this workspace")
    _assert_own_viewer(viewer, principal_id)
    return resolve(
        link,
        reach,
        visible_agents=visible_agent_ids(records, viewer),
        populated=populated,
        now=now,
    )


# ------------------------------------------ building one from a template (M40.2.2.3)
def personal_audience(principal_id: str) -> AgentAudience:
    """The audience a member's own agent gets. Personal, owned by them, and no parameter.

    The only audience this module can produce (M40.2.2.4). A level parameter here would be
    the widening path, reachable from a self-service form, and
    `brain.agents.model.AUDIENCE_IS_NOT_AUTHORITY` is what a widened audience quietly
    changes: not what the agent may do, but who may start it. Widening an agent's audience is
    a decision with somebody behind it and this surface is not that decision.

    Refuses a blank or whitespace owner, because `brain.knowledge.visibility.scope_for`
    refuses one loudly and the message it gives names a scope rather than a form field.
    """
    if not principal_id.strip():
        msg = (
            "a personal agent with no owner is one whose audience predicate is the "
            "unrestricted scope, so the narrowest level in the system would publish it"
        )
        raise MemberError(msg)
    return AgentAudience(level=Visibility.PERSONAL, owner_id=principal_id)


def build_personal_agent(
    signed: SignedManifest,
    instance: TemplateInstance,
    *,
    principal_id: str,
    reach: EntitlementSet,
    now: datetime,
) -> EffectiveAgent:
    """Materialise one personal agent from a template, inside its builder's own reach
    (M40.2.2.3, M40.2.2.4).

    `brain.agents.template.materialise` does the work: it checks the pin in three parts,
    revalidates the overlay, and builds a real `AgentRecord` through its own constructor. The
    audience is `personal_audience`'s and is not a parameter, which is the whole of M40.2.2.4
    at this door: there is no argument by which this produces an agent anybody else can see.

    The ceiling check is `brain.builder.publish.widened_capabilities`, which asks what the
    declared ceiling admits that this person's own reach does not, on both axes: a capability
    they do not hold at all, and one they hold in a narrower scope. Anything it returns is
    refused. See `A_PERSONAL_CEILING_MEANS_NOTHING_UNTIL_THE_AGENT_IS_SHARED`, and note that
    nothing here intersects anything: this is a comparison of two declared sets and the run
    reach is computed where a run happens.

    Refuses an instance somebody else installed. `TemplateInstance.created_by` is who set the
    overlay, and building somebody else's instance into an agent owned by you would attribute
    their local edits to your agent with the ownership record still naming them.
    """
    if instance.created_by != principal_id:
        msg = (
            f"{instance.created_by!r} installed {instance.instance_id!r} and "
            f"{principal_id!r} is building it; the overlay's edits would be attributed to "
            "whoever set them and the agent to somebody else"
        )
        raise MemberError(msg)
    _assert_own_reach(reach, principal_id, "this agent")
    built = materialise(signed, instance, audience=personal_audience(principal_id))
    over = widened_capabilities(reach, entitlement_ceiling(built.record), now=now)
    if over:
        msg = (
            f"{instance.instance_id!r} declares a ceiling admitting {list(over)}, which "
            f"{principal_id!r} does not reach. "
            f"{A_PERSONAL_CEILING_MEANS_NOTHING_UNTIL_THE_AGENT_IS_SHARED}"
        )
        raise MemberError(msg)
    return built


# ------------------------------------------------- asking for one you cannot run (M40.2.2.5)
@dataclass(frozen=True)
class AgentRequest:
    """One person asking to be able to run an agent they can already see (M40.2.2.5).

    **No decision, no approver, no granted_at.** Asking is not deciding, and a type with
    nowhere to record an answer cannot be approved by filling in a field; `member_gaps`
    reports one that could.

    Carries the department the request goes to and not the steward's name. The requester can
    already see the agent, so its existence is not the disclosure; who personally answers for
    it is a name to lobby, and the decision belongs in a queue rather than in a corridor.
    """

    agent_id: str
    requested_by: str
    #: The department the request is routed to, from the agent's own audience.
    department: str
    at: datetime

    def __post_init__(self) -> None:
        for name in ("agent_id", "requested_by", "department"):
            if not str(getattr(self, name)).strip():
                msg = (
                    f"a request with no {name} is one nobody receives or one everybody "
                    "does, and a queue cannot tell which"
                )
                raise MemberError(msg)
        if self.at.tzinfo is None:
            msg = (
                f"a request for {self.agent_id!r} is dated with no timezone, so its place in "
                "a queue ordered by how long things have waited is the host's offset out"
            )
            raise MemberError(msg)


def request_agent(
    agent_id: str,
    records: Sequence[AgentRecord],
    *,
    principal_id: str,
    viewer: AgentViewer,
    at: datetime,
) -> AgentRequest:
    """Ask a department for an agent this person can see and cannot run (M40.2.2.5).

    Three refusals, and the first is the one that matters.

    *An agent outside this person's audience.* Refused with the same sentence as an agent
    nobody ever created, because the two are the same answer: see
    `AN_AGENT_SOMEBODY_CANNOT_SEE_IS_NOT_ONE_THEY_MAY_ASK_FOR`. `visible_agent_ids` decides,
    so a request form cannot become the catalogue the agent list refuses to be.

    *An agent they can already run.* A request for something already available is a row in
    somebody's queue that resolves to nothing, and the person who filed it is told a decision
    was made about access they already had.

    *An agent with no department on its audience.* Refused rather than routed to nobody. A
    company-visible agent's access is not one department's to grant, and filing the request
    anyway would put it in a queue that never looks at it, which is worse than being told
    now.
    """
    _assert_own_viewer(viewer, principal_id)
    found = {one.agent_id: one for one in records}
    if agent_id not in visible_agent_ids(records, viewer):
        msg = (
            f"there is no agent {agent_id!r} for {principal_id!r} to request. "
            f"{AN_AGENT_SOMEBODY_CANNOT_SEE_IS_NOT_ONE_THEY_MAY_ASK_FOR}"
        )
        raise MemberError(msg)
    if agent_id in runnable_agent_ids(records, viewer):
        msg = (
            f"{principal_id!r} can already run {agent_id!r}, so this request would be a "
            "decision somebody makes about access that is already there"
        )
        raise MemberError(msg)
    return AgentRequest(
        agent_id=agent_id,
        requested_by=principal_id,
        department=found[agent_id].audience.department,
        at=at,
    )


# ------------------------------------- what the system learnt about me (M40.4.1.1, M40.2.1.4)
@dataclass(frozen=True)
class LearnedPreference:
    """One thing the system learnt about this person, in words, with its evidence.

    The statement is `brain.console.reach_view.readable`'s, which means the reader was
    admitted to it by `may_recall` rather than by owning it; see
    `OWNERSHIP_ADMITS_THE_ROW_AND_RECALL_ADMITS_THE_WORDS`.

    `evidence` is signal kinds and nothing else. No conversation, no message, no instant and
    no principal, per `brain.memory.digest.EVIDENCE_NAMES_WHAT_WAS_NOTICED_AND_NEVER_WHOSE_
    CONVERSATION_IT_WAS`, and `Learning` carries nothing else to put there in any case.

    `control_writes` is what the undo control would produce, which is the "each reversible"
    half of M40.2.1.4 made visible on the row rather than promised in a heading: a
    `Correction` has two members and deliberately no third, so this field cannot express a
    removal.
    """

    memory_id: str
    change: Change
    statement: str
    evidence: tuple[Signal, ...]
    confidence: float
    learned_at: datetime
    control_writes: Correction


@dataclass(frozen=True)
class LearnedAboutMe:
    """Everything the system learnt from this person's own conversations (M40.4.1.1).

    No total and no field that could hold one. The number a person may have is how many rows
    are here, which `learned` derives from the tuple: it counts what was shown and it cannot
    be made to count anything else, because there is nothing else on this value.
    """

    subject_id: str
    items: tuple[LearnedPreference, ...]

    @property
    def learned(self) -> int:
        """How many things are on this page (M40.2.1.4). A count of what was shown."""
        return len(self.items)


def learned_about_me(
    entries: Sequence[tuple[Learning, str]],
    *,
    principal_id: str,
    reader: EntitlementSet,
    now: datetime,
    where: Mapping[str, object] | None = None,
) -> LearnedAboutMe:
    """Every preference learned from this person's conversations, with its evidence
    (M40.4.1.1, M40.2.1.4).

    Each entry is a learning and its statement, the pairing `brain.console.reach_view.
    split_memory` takes, because `Learning` deliberately carries no text and inventing a
    field for it here would put the transcript back on the record that refuses to hold it.

    Three filters, in this order and for three different reasons.

    *Authorship.* `is_own` against `Formation.principal_id`, which is what a person means by
    a memory of theirs, and never a permission.

    *The tier.* `may_digest`, called rather than restated, so the page and the weekly email
    agree about what has actually taken effect. A tier-three learning is a proposal waiting
    for a person and a page headed "what has been learnt about you" listing one would be
    describing something that is not true yet; a session learning is in neither table.

    *Recall.* `readable`, which computes `may_recall` about this reader now. See
    `OWNERSHIP_ADMITS_THE_ROW_AND_RECALL_ADMITS_THE_WORDS`. A row that does not survive it is
    absent, with nothing anywhere saying it was withheld.

    Newest first, ties broken by id, so a page read from the top starts with the thing most
    likely to still be wrong and two readings of an unchanged store match.
    """
    _assert_own_reach(reader, principal_id, "this page")
    rows: list[LearnedPreference] = []
    for learning, statement in entries:
        if not is_own(principal_id, learning.formation.principal_id):
            continue
        if not may_digest(learning):
            continue
        text = readable(learning, statement, reader, now=now, where=where)
        if text is None:
            continue
        row = memory_item(learning, text.seen)
        rows.append(
            LearnedPreference(
                memory_id=row.memory_id,
                change=row.change,
                statement=text.statement,
                evidence=row.evidence,
                confidence=row.confidence,
                learned_at=row.learned_at,
                control_writes=row.control_writes,
            )
        )
    return LearnedAboutMe(
        subject_id=principal_id,
        items=tuple(sorted(rows, key=lambda one: (-one.learned_at.timestamp(), one.memory_id))),
    )


# ------------------------------------------------------ undo, one and all (M40.4.1.2)
def undo_one(
    learning: Learning,
    *,
    principal_id: str,
    at: datetime,
    supersessions: Iterable[Supersession] = (),
    demotions: Iterable[Demotion] = (),
) -> Undo:
    """The undo control beside one row (M40.4.1.2). It writes a mark.

    `brain.console.own_things.delete_own_memory`, called and not reimplemented, so the
    ownership refusal, the idempotence and the choice between a supersession and a demotion
    all stay in the modules that argue for them. `brain.memory.digest.
    UNDO_IS_A_MARK_AND_NEVER_A_REMOVAL` is the argument and it is not restated here, because
    a second statement of it is a second thing to keep in step.
    """
    return delete_own_memory(
        learning,
        principal_id=principal_id,
        at=at,
        supersessions=supersessions,
        demotions=demotions,
    )


def undo_all(
    learnings: Sequence[Learning],
    *,
    principal_id: str,
    at: datetime,
    supersessions: Iterable[Supersession] = (),
    demotions: Iterable[Demotion] = (),
) -> tuple[Undo, ...]:
    """The undo-all control (M40.4.1.2). One mark per row, or none at all.

    **Refuses the whole batch rather than skipping a row**, on two grounds, and both are
    `brain.console.reads.notices_for`' argument: a partial batch is the shape where the
    interesting item is the one that went missing, and the caller who gets a shorter list
    than they expected has no way to tell which.

    *A memory that is not this person's.* The batch was assembled from the wrong list, and
    undoing the rest would leave somebody believing they had cleared their page.

    *The same memory twice.* Every mark is written against the corrections that already
    exist, so two entries for one memory would both see it unmarked and produce two
    corrections, the second of which reverses nothing anybody asked about.
    `brain.memory.digest.undo` is idempotent across calls and cannot be idempotent inside one
    list it never sees.

    Ordinary idempotence is inherited and not reimplemented: a memory already marked, by an
    earlier click or by something else entirely, produces an `Undo` that took no effect and
    the correction that marked it is left exactly as it is.

    Returns one `Undo` per input, in the input's order, so a caller can put a result beside
    the row it came from. Writes nothing; the corrections are returned for whoever owns the
    table.
    """
    seen: set[str] = set()
    for one in learnings:
        if not is_own(principal_id, one.formation.principal_id):
            msg = (
                f"{one.memory_id!r} was formed from somebody else's conversation and this "
                f"batch is {principal_id!r}'s; the whole undo is refused rather than the "
                "rest of it being applied to a list nobody can check"
            )
            raise MemberError(msg)
        if one.memory_id in seen:
            msg = (
                f"{one.memory_id!r} appears twice in one undo, so the second mark would be "
                "written against a memory the first had already marked and would reverse a "
                "correction nobody asked to reverse"
            )
            raise MemberError(msg)
        seen.add(one.memory_id)
    return tuple(
        undo_one(
            one,
            principal_id=principal_id,
            at=at,
            supersessions=supersessions,
            demotions=demotions,
        )
        for one in learnings
    )


# --------------------------------------------- the digest in their own channel (M40.4.1.3)
class DigestForm(enum.StrEnum):
    """How a weekly digest arrives on one surface. Two, and there is no third.

    There is deliberately nothing meaning "controls where the surface allows". A per-item
    decision puts an undo button beside one row and not the next, with nothing on the page
    saying why, and the row without one reads as a learning that cannot be undone. See
    `A_DIGEST_WITH_ITS_CONTROLS_MISSING_READS_AS_A_DIGEST_WITH_NOTHING_TO_UNDO`.
    """

    #: The surface can render an actionable card, so the undo controls travel with the list.
    WITH_CONTROLS = "with_controls"
    #: It cannot, so what travels is a link back to the surface that can.
    LINK_ONLY = "link_only"


@dataclass(frozen=True)
class DigestDelivery:
    """One week of learning, addressed to one surface (M40.4.1.3).

    The digest is `brain.memory.digest.weekly_digest`'s whole and is not rebuilt, so the
    channel cannot change which learnings appear: `may_digest`'s two refusals decide that and
    a delivery decision has no way to reach them.
    """

    digest: WeeklyDigest
    channel: Channel
    form: DigestForm


def digest_for_channel(
    *,
    now: datetime,
    reader: EntitlementSet,
    learnings: Sequence[Learning],
    capabilities: ChannelCapabilities,
    period: Any = DIGEST_PERIOD,
) -> DigestDelivery:
    """This week's digest, in the form this person's own channel can carry (M40.4.1.3).

    Two decisions and only the second is made here. What is in the digest is
    `weekly_digest`'s, at this reader's own reach, through `may_recall` like every other
    disclosure: there is no argument in this signature that could widen it and no shortcut
    for a reader who looks like an administrator.

    Whether the controls travel is `brain.channels.adapter.Feature.CARDS`, asked of the
    surface's own declared capabilities rather than inferred from which channel it is.
    `brain.channels.adapter.Feature` says declaring is done per adapter precisely because
    inferring means guessing, and the wrong guess here sends a list with no buttons to
    somebody who then believes there is nothing to be done about it.

    The classification check is not made here and is not missing. `assert_can_send` is
    called by an adapter's own `send`, by design, so that a check the caller performs cannot
    be the one a later call site forgets; making a second one here would be exactly that
    caller.
    """
    return DigestDelivery(
        digest=weekly_digest(now=now, reader=reader, learnings=learnings, period=period),
        channel=capabilities.channel,
        form=(
            DigestForm.WITH_CONTROLS
            if capabilities.supports(Feature.CARDS)
            else DigestForm.LINK_ONLY
        ),
    )


# ------------------------------------------------------ opting out entirely (M40.4.1.4)
#: The tiers an opt-out stops. Derived from `Tier`'s own ordering rather than written out,
#: exactly as `brain.memory.digest.DIGEST_TIERS` is: a tier added above the gate is stopped
#: by construction rather than left outside a list somebody has to remember to edit.
STOPPED_BY_OPT_OUT: Final[frozenset[Tier]] = frozenset(tier for tier in Tier if tier > Tier.SESSION)

#: The tiers it cannot stop. See `OPTING_OUT_CANNOT_STOP_A_CONVERSATION_REMEMBERING_ITSELF`.
KEPT_THROUGH_OPT_OUT: Final[frozenset[Tier]] = frozenset(
    tier for tier in Tier if tier <= Tier.SESSION
)

#: What opting out costs, in the words the person is owed. Held as a constant so the sentence
#: a member reads is reviewable in one place rather than assembled by a renderer, which is
#: `brain.knowledge.item.BADGE_TEXT`'s argument about its four sentences.
THE_COST_OF_OPTING_OUT: Final = (
    "Answers stop improving from your corrections: a preference you state will be honoured "
    "for the rest of the conversation and forgotten afterwards, and the same explanation "
    "will be needed again next week. Nothing already learnt is removed by this, because "
    "stopping and erasing are different requests; ask for a deletion if you want what is "
    "there to go. Within one conversation the system still remembers what you have just "
    "said, which is how a conversation works and is not something this switch can change."
)


@dataclass(frozen=True)
class LearningOptOut:
    """One person switching off personal learning, and what that costs them (M40.4.1.4).

    Carries the tiers stopped and the tier kept rather than a bare flag, because a flag is
    read as "off" and this is not off: tier zero survives, and a person who was told
    otherwise finds out when the assistant remembers the sentence before. The two sets are
    checked to partition `Tier` at construction, so an opt-out that quietly kept a tier
    cannot be built.
    """

    principal_id: str
    at: datetime
    stops: frozenset[Tier]
    keeps: frozenset[Tier]
    cost: str

    def __post_init__(self) -> None:
        if not self.principal_id.strip():
            msg = "an opt-out belonging to nobody switches learning off for everybody"
            raise MemberError(msg)
        if self.at.tzinfo is None:
            msg = (
                "an opt-out dated with no timezone takes effect at the host's offset from "
                "UTC, so a learning formed in the gap is kept or dropped by the machine"
            )
            raise MemberError(msg)
        if not self.cost.strip():
            msg = (
                "an opt-out with no stated cost is a switch somebody flips without being "
                "told what stops working, and the leaf asks for the cost stated honestly"
            )
            raise MemberError(msg)
        if self.stops | self.keeps != frozenset(Tier) or self.stops & self.keeps:
            msg = (
                f"this opt-out stops {sorted(int(one) for one in self.stops)} and keeps "
                f"{sorted(int(one) for one in self.keeps)}, which is not every tier exactly "
                "once; a tier in neither is one nobody decided about and it keeps running"
            )
            raise MemberError(msg)


def opt_out(*, principal_id: str, at: datetime) -> LearningOptOut:
    """Switch off personal learning for this person, with the cost stated (M40.4.1.4).

    Stops every tier above the session and says so; keeps tier zero and says that too. See
    `OPTING_OUT_CANNOT_STOP_A_CONVERSATION_REMEMBERING_ITSELF`.

    **Removes nothing.** What has already been learnt stays where it is, because stopping and
    erasing are different requests with different routes: `undo_all` marks a page's worth and
    `request_deletion` routes the rest. An opt-out that also cleared the record would be a
    deletion performed by a toggle, with no certificate and no route through
    `brain.ops.erasure`.

    There is no parameter naming a tier. A per-tier opt-out is the same argument
    `brain.console.reach_view` records rejecting about a per-tier learning freeze: the person
    reaching for the switch is the one least placed to work out which tiers matter, and a
    switch that stops some of it reads as a switch that stopped it.
    """
    return LearningOptOut(
        principal_id=principal_id,
        at=at,
        stops=STOPPED_BY_OPT_OUT,
        keeps=KEPT_THROUGH_OPT_OUT,
        cost=THE_COST_OF_OPTING_OUT,
    )


# ------------------------------------------------ what is held about me (M40.4.2.1)
@dataclass(frozen=True)
class StoredThing:
    """What one store holds about this person, and what a deletion would do to it.

    The holding is `brain.ops.erasure.StoreHolding`'s own, and the disposition beside it is
    the field this type exists for: a page saying "this is everything we hold" beside a
    delete control has to say, on the same rows, which of them a deletion does not reach.
    Otherwise the two controls together make a promise neither of them makes alone.
    """

    store: Store
    data_class: DataClass
    #: How many items this store reported. Zero is a real answer; see `reached`.
    items: int
    #: False when the store could not be searched, which is not the same as empty.
    reached: bool
    #: What the store holds, in `brain.ops.retention.StoreFacts`' own plain language.
    holds: str
    #: What a deletion does here: erase, purge, rotate out, or keep deliberately.
    disposition: Disposition

    def line(self) -> str:
        """One sentence a person reads. The holding's own wording, plus what deletion does.

        `StoreHolding.line` is reused rather than reworded, so the subject access request an
        administrator assembles and the page the subject reads say the same thing about the
        same store. What is appended is the disposition, which that line does not carry
        because a subject access request is not offering a delete button.
        """
        holding = StoreHolding(
            store=self.store,
            data_class=self.data_class,
            items=self.items,
            reached=self.reached,
            holds=self.holds,
        )
        if not self.reached:
            return holding.line()
        return f"{holding.line()} deletion here: {self.disposition.value}"


@dataclass(frozen=True)
class StoredAboutMe:
    """Everything held about this person, store by store, in plain language (M40.4.2.1).

    Covers every member of `brain.ops.retention.Store` because `brain.ops.erasure.assemble`
    builds it by iterating the enum. There is no second coverage check here and that is
    deliberate rather than an omission: `SubjectAccess` refuses an incomplete set at
    construction, so a check here would be reporting a state that cannot reach it, which is
    the duplicate `brain.connectors.manifest.ProjectedEntity` records having removed.
    """

    subject_id: str
    at: datetime
    things: tuple[StoredThing, ...]

    @property
    def complete(self) -> bool:
        """Whether every store was actually searched. Not whether anything was found."""
        return all(one.reached for one in self.things)

    def lines(self) -> tuple[str, ...]:
        """The page, one line per store, with an honest last line when one was missed."""
        body = tuple(one.line() for one in self.things)
        if self.complete:
            return body
        names = ", ".join(one.store.value for one in self.things if not one.reached)
        return (*body, f"incomplete: {names} could not be searched")


def what_is_stored(
    *,
    subject_id: str,
    at: datetime,
    found: Mapping[Store, int],
    unreachable: Iterable[Store] = (),
) -> StoredAboutMe:
    """What the system holds about this person and where (M40.4.2.1).

    `brain.ops.erasure.assemble` does the assembly, iterating `Store` rather than the
    caller's mapping, which is `A_STORE_LEFT_OUT_OF_A_SUBJECT_ACCESS_REQUEST_IS_A_LIE`: a
    document about the stores somebody remembered arrives looking complete. Every refusal in
    that path stays there, including the one about a store reporting items it could not
    reach.

    What is added is the disposition per store, so this page can sit beside `request_deletion`
    without the pair implying that asking will empty all of it.

    Refuses a subject that is whitespace. `SubjectAccess` refuses an empty one and a string
    of spaces is what arrives from a form: it would produce a complete-looking document about
    a person whose id is a space, and every count in it would be nought.
    """
    if not subject_id.strip():
        msg = (
            "a subject access page with a blank subject is a complete-looking document "
            "about nobody, and every figure on it reads as an honest zero"
        )
        raise MemberError(msg)
    gathered = assemble(subject_id=subject_id, at=at, found=found, unreachable=unreachable)
    return StoredAboutMe(
        subject_id=gathered.subject_id,
        at=gathered.at,
        things=tuple(
            StoredThing(
                store=one.store,
                data_class=one.data_class,
                items=one.items,
                reached=one.reached,
                holds=one.holds,
                disposition=disposition_of(one.store),
            )
            for one in gathered.holdings
        ),
    )


# ------------------------------------------------- my history, and taking it (M40.4.2.2)
#: Why a person exporting their own conversation is a subject access request.
#:
#: `brain.ops.export.ExportReason` says the member is there because a subject access request
#: still has to leave the building and is a different act from an eDiscovery collection. This
#: is the self-service version of the same act, and recording it as anything else would file
#: a person reading their own transcript beside an investigation.
MY_EXPORT_REASON: Final = ExportReason.SUBJECT_ACCESS_REQUEST

#: The one store a conversation export draws from. Named rather than passed, because a member
#: control that took a store list would be `BulkExportRequest` with a friendlier name on it.
MY_EXPORT_STORES: Final[tuple[Store, ...]] = (Store.CONVERSATION,)


def export_my_history(
    turns: Iterable[Turn],
    *,
    principal_id: str,
    conversation_id: str,
    at: datetime,
    export_id: str,
    reason_reference: str,
) -> tuple[ConversationExport, ExportAudit]:
    """This person's own conversation, and the row that records them taking it (M40.4.2.2).

    The export is `brain.console.own_things.export_own_history`, which builds it from the
    narrowed turns rather than from the input and files them under the same principal the
    narrowing used. Nothing about that is repeated here.

    **The audit row is the addition and it is the point.** An export is a copy of a
    conversation leaving the system, and the difference between a person reading their own
    transcript and an administrator taking it on their behalf is entirely in who is recorded
    as having asked. So `requested_by` and the single subject are both this person, from one
    argument, and there is no parameter by which they could differ; `all_subjects` is false
    and there is no argument that could set it.

    `reason_reference` is required and non-blank for the reason `BulkExportRequest` requires
    one: it is what somebody reviewing this in a year reads instead of guessing. For a
    self-service export it is the request the person made, and a blank one is refused rather
    than filled in with a default, because a default reference is one nobody wrote.

    The count on the row is what actually left, taken off the export rather than off the
    input, so a row cannot report more turns than the narrowing produced.
    """
    if not reason_reference.strip():
        msg = (
            f"an export by {principal_id!r} names no written request, so the row recording "
            "it says a copy of a conversation left the system and nothing about why"
        )
        raise MemberError(msg)
    taken = export_own_history(
        turns, principal_id=principal_id, conversation_id=conversation_id, at=at
    )
    return taken, ExportAudit(
        export_id=export_id,
        at=at,
        requested_by=principal_id,
        reason=MY_EXPORT_REASON,
        reason_reference=reason_reference,
        stores=MY_EXPORT_STORES,
        subjects=(principal_id,),
        all_subjects=False,
        items=len(taken.turns),
    )


# --------------------------------------------------- asking for a deletion (M40.4.2.3)
@dataclass(frozen=True)
class DeletionRequest:
    """One person asking for their data to be removed (M40.4.2.3).

    **No completion, no certificate, no eraser and no count of what went.** Every one of
    those describes a deletion that happened, and this is a request; `brain.ops.erasure.
    Deletion` and `Certificate` are the shapes for the other end and they are built by that
    module after something actually ran. `member_gaps` reads the fields of this type rather
    than trusting the paragraph. See `A_DELETION_REQUEST_IS_ROUTED_AND_A_ROUTE_IS_NOT_A_DELETE`.
    """

    subject_id: str
    requested_at: datetime

    def __post_init__(self) -> None:
        if not self.subject_id.strip():
            msg = (
                "a deletion request with no subject is a request to delete everybody, and a "
                "form supplies a string of spaces rather than an empty one"
            )
            raise MemberError(msg)
        if self.requested_at.tzinfo is None:
            msg = (
                "a deletion request dated with no timezone orders wrongly against the holds "
                "and the backups it will be compared with"
            )
            raise MemberError(msg)


@dataclass(frozen=True)
class DeletionRoute:
    """Where one deletion request goes and what it would not reach (M40.4.2.3).

    Four tuples over `brain.ops.retention.Store` and deliberately no date. The backup horizon
    is measured from when a deletion completed, because a backup taken between the request
    and the completion still holds the data, so a date computed here would be earlier than
    the truth: the direction that makes a document wrong. It appears on the certificate,
    which is `brain.ops.erasure.certify`'s to issue.

    The four tuples partition every store, checked at construction, so a store added to the
    system without a disposition cannot fall out of this page silently.
    """

    request: DeletionRequest
    #: Every store, sources before the copies made from them.
    order: tuple[Store, ...]
    #: The stores a deletion actually reaches, in the order it must reach them.
    reaches: tuple[Store, ...]
    #: Stores a deletion does not reach. Time removes the data from these.
    rotates_out: tuple[Store, ...]
    #: Stores kept deliberately, where the reason outranks the request.
    retained: tuple[Store, ...]

    def __post_init__(self) -> None:
        covered = set(self.order)
        if covered != set(Store):
            missing = sorted(one.value for one in set(Store) - covered)
            msg = (
                f"a route silent about {missing} tells somebody where their request goes and "
                "leaves out a store it would either empty or deliberately keep"
            )
            raise MemberError(msg)
        parts = (*self.reaches, *self.rotates_out, *self.retained)
        if sorted(parts) != sorted(self.order):
            msg = (
                "the stores a deletion reaches, the ones that rotate out and the ones kept "
                "do not add up to every store exactly once, so a store is described twice "
                "or not at all on a page about what will happen"
            )
            raise MemberError(msg)


def request_deletion(*, subject_id: str, at: datetime) -> DeletionRequest:
    """Record that this person has asked for their data to be removed (M40.4.2.3).

    Builds a request and does nothing else. There is no parameter here a `StoreEraser` could
    arrive through, no callable of any kind, and nothing returned that could be executed. See
    `A_DELETION_REQUEST_IS_ROUTED_AND_A_ROUTE_IS_NOT_A_DELETE`.

    No legal hold is read. `brain.ops.erasure.erase` refuses a held subject and that is where
    the check belongs; see `A_HOLD_READ_AT_REQUEST_TIME_IS_A_HOLD_READ_TOO_EARLY`.
    """
    return DeletionRequest(subject_id=subject_id, requested_at=at)


def route(one: DeletionRequest) -> DeletionRoute:
    """Where this request goes, and what a deletion would not reach (M40.4.2.3).

    Every tuple is `brain.ops.erasure`'s own answer: `deletion_order` for the sequence,
    `erasure_targets` for what is actually reached, and `disposition_of` for the two kinds of
    store a deletion never touches. Nothing is written out here, because a list of stores in
    this file is a list that stops being right the day somebody adds one, and the failure has
    no symptom: the page arrives complete.

    Reports and performs nothing. The request goes to the retention policy, which decides the
    order and the windows, and to whoever implements `StoreEraser`, which nothing does.
    """
    return DeletionRoute(
        request=one,
        order=deletion_order(),
        reaches=erasure_targets(),
        rotates_out=tuple(
            store for store in deletion_order() if disposition_of(store) is Disposition.ROTATES_OUT
        ),
        retained=tuple(
            store for store in deletion_order() if disposition_of(store) is Disposition.RETAINED
        ),
    )


# ------------------------------------------------------------------------- the diagnostic
#: The types a member is handed. Listed rather than discovered, following
#: `brain.console.workspace.WORKSPACE_SURFACE`: a type added here and not to this tuple is
#: one the checks below never see.
MEMBER_SURFACE: Final[tuple[type, ...]] = (
    MonthlyActivity,
    CallableAgent,
    PersonalCeiling,
    AgentRow,
    AgentRequest,
    LearnedPreference,
    LearnedAboutMe,
    DigestDelivery,
    LearningOptOut,
    StoredThing,
    StoredAboutMe,
    DeletionRequest,
    DeletionRoute,
)

#: The functions narrowed by a principal. Handed to `brain.console.own_things.own_gaps`,
#: which is the check that the argument making a surface personal is keyword-only, has no
#: default, and has no neighbour that could mean everybody. Reused rather than restated: a
#: second copy of that check is a second place for the list of dangerous names to fall behind.
PERSONAL_CALLS: Final[tuple[Callable[..., Any], ...]] = (
    activity_this_month,
    callable_agents,
    personal_budget,
    my_agents,
    open_workspace,
    build_personal_agent,
    request_agent,
    learned_about_me,
    undo_one,
    undo_all,
    export_my_history,
    opt_out,
)

#: Field names that would put somebody else's budget on a personal one.
NAMES_THAT_WOULD_BE_ANOTHER_BUDGET: Final[frozenset[str]] = frozenset(
    {"company", "company_minor", "department", "department_minor", "of_department", "share"}
)

#: Field names that would turn a request into the thing it is asking for.
NAMES_THAT_WOULD_BE_A_DELETION: Final[frozenset[str]] = frozenset(
    {"certificate", "certificate_id", "completed_at", "erased", "eraser", "removed"}
)

#: Field names that would let a request answer itself.
NAMES_THAT_WOULD_BE_A_DECISION: Final[frozenset[str]] = frozenset(
    {"approved", "approved_at", "approver", "approver_id", "decided_at", "decision", "granted"}
)

#: Parameter names by which something that removes data could reach the request path.
NAMES_THAT_WOULD_BE_AN_ERASER: Final[frozenset[str]] = frozenset(
    {"eraser", "execute", "executor", "perform", "purge", "remove", "sweeper"}
)


def member_gaps(
    *,
    surface: Sequence[type] = MEMBER_SURFACE,
    personal: Sequence[Callable[..., Any]] = PERSONAL_CALLS,
    budget_type: type = PersonalCeiling,
    request_types: Sequence[type] = (DeletionRequest, DeletionRoute),
    deciding_types: Sequence[type] = (AgentRequest,),
    routing: Sequence[Callable[..., Any]] = (request_deletion, route),
    opt: Callable[..., Any] = opt_out,
) -> tuple[str, ...]:
    """Everything about this surface that would answer for somebody else or act on them.

    Takes its inputs rather than reading the module's own constants, and a mutation is the
    reason `brain.console.own_things.own_gaps` gives about itself: a diagnostic that can only
    run against the healthy tree has nothing to report, so switching off any of its refusals
    changes nothing observable and every one of them survives. Calling it with no arguments
    is the deployment check and calling it with a constructed type is the test.

    The first check is `own_gaps` over this module's own functions rather than a second
    implementation of it, because the list of parameter names that would mean everybody is
    the part most likely to grow, and two copies of it means the new name is added to one.
    """
    gaps: list[str] = list(own_gaps(personal))

    gaps.extend(
        f"{found} would tell a reader how much they were not shown"
        for found in hidden_count_fields(surface)
    )
    gaps.extend(
        f"{budget_type.__name__}.{name} puts a budget that is not this person's on their own "
        "page, and a share of a wider one hands them the wider one"
        for name in getattr(budget_type, "__dataclass_fields__", {})
        if name in NAMES_THAT_WOULD_BE_ANOTHER_BUDGET
    )
    for asking in request_types:
        gaps.extend(
            f"{asking.__name__}.{name} describes a deletion that happened, on a value that "
            f"is a request for one. {A_DELETION_REQUEST_IS_ROUTED_AND_A_ROUTE_IS_NOT_A_DELETE}"
            for name in getattr(asking, "__dataclass_fields__", {})
            if name in NAMES_THAT_WOULD_BE_A_DELETION
        )
    for deciding in deciding_types:
        gaps.extend(
            f"{deciding.__name__}.{name} would let a request record its own answer, so "
            "asking and deciding would be one act by one person"
            for name in getattr(deciding, "__dataclass_fields__", {})
            if name in NAMES_THAT_WOULD_BE_A_DECISION
        )
    for path in routing:
        taken = set(inspect.signature(path).parameters)
        gaps.extend(
            f"{getattr(path, '__name__', 'the request path')} takes {name}, so the surface "
            "that routes a deletion request could carry it out. "
            f"{A_DELETION_REQUEST_IS_ROUTED_AND_A_ROUTE_IS_NOT_A_DELETE}"
            for name in sorted(taken & NAMES_THAT_WOULD_BE_AN_ERASER)
        )

    if "tier" in set(inspect.signature(opt).parameters):
        gaps.append(
            f"{getattr(opt, '__name__', 'the opt-out')} takes a tier, so switching personal "
            "learning off is a decision about which tiers matter, made by the person least "
            "placed to make it at the moment they reach for the switch"
        )

    return tuple(gaps)


def member_notes() -> tuple[str, ...]:
    """The two M40 leaves this module decides it cannot honestly build.

    Separate from `member_gaps` for the reason `brain.console.agent_output.
    retention_enforcement_gaps` is separate from `artifact_gaps`: that one is a deployment
    check and a check that is red on the day it lands is a check somebody switches off. This
    one is red today and is meant to be.

    Both findings are about a missing field rather than a missing screen, which is why
    neither is worked around here: inventing either would put a value on a record whose
    absence is argued for somewhere else.
    """
    return (
        "recent threads across channels cannot be assembled: brain.chat.turns.Turn carries a "
        "principal, an instant and an agent id, and no thread id and no channel, so there is "
        "nothing to group a thread by and nothing saying which surface a turn arrived on; "
        "brain.tables.chat.ConversationRow is declared and nothing in src queries it",
        "which agents read a person's record cannot be answered from the ledger: "
        "brain.audit.ledger.AuditAction is closed and pinned by an invariant test, none of "
        "its members is a read, SUBJECT_KINDS has no member for a personnel record, and an "
        "ordinary entitled read is written to the trace rather than to the ledger",
    )
