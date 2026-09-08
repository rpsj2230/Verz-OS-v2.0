"""Turning an agent off, retiring it for good, handing it on, and showing it to everybody.

Three states, one move between people and one widening of who may see it, and every one of
them is a decision a person made about a record rather than a fact about a clock. Nothing
here reads the time; `now` is a parameter, for the reason `brain.gate.provenance` gives,
because a rule about dates that reads the clock itself cannot be tested at its own boundary.

**Disable is reversible and archive is not, and that difference is the only reason there
are two.** A reversible archive is a disable with a longer name: the two controls collapse
into one with two spellings, and a console showing both would be offering a choice that
makes no difference. Archiving says the agent is finished, and something finished that can
come back is something nobody can say the state of. Bringing one back is creating an agent,
with a new record, a new persona review and a new ceiling somebody signed off, which is
exactly the work that should not be skippable by clearing a column.

**A state change never touches the ceiling.** Disabling an agent does not narrow what it may
reach and enabling it does not widen anything, because neither function is given an
`AgentAuthority` to change. Reach is decided per run, by intersecting the caller's
entitlement with the agent's ceiling, and a disabled agent simply never gets that far:
`runnable_agent_ids` leaves it out, so `brain.gate.select.select_agent` cannot choose it.
That is one enforcement point rather than two, and the alternative, emptying the ceiling on
disable and restoring it on enable, is a data migration disguised as a toggle.

**Ownership transfer moves the steward and nothing else (M13.1.5).** When somebody leaves,
their agents need a person who answers for them, and that is all a transfer is. It does not
move authority: an agent handed to a Super Admin does not thereby reach more, because
`E_run` is computed against the caller of each run and not against whoever owns the record.
It does move audience, but only where the audience *is* the owner: a personal agent becomes
visible to its new steward and invisible to the person who left, which is the point of
transferring it, and a department agent's audience does not move at all.

`transfer_ownership` takes a `Principal` rather than an id, because the check that matters
is whether the new steward is still there, and `Principal.is_active` is where that already
lives. An id would mean re-deriving it from a lookup the caller may not have made, and the
failure that produces is silent: a leaver's agents handed to a second leaver on the same
offboarding run, with every record looking correct.

****Publishing is the audience widening, and until now nothing anywhere performed one.** An
agent is global when its `AgentAudience.level` is `Visibility.COMPANY`, so
`brain.console.global_surfaces` could retire a global agent and could not create one, and it
said so rather than writing an agent state change in a rendering module. `publish` is that
transition, here, beside the other three.

**A publication widens who is told and never what is reached, which is why it does not take
what a grant takes.** `brain.console.scoped_authority.may_grant` asks two questions and both
are about reach: the authority to write grants at all, held over the scope being written, and
the capability being written, held over that same scope. The second one is what a grant needs
and a publication must not have. `E_run(caller, agent) = E(caller) ∩ agent_ceiling` has no
term for the audience, so a published agent hands nobody a row they could not already reach,
and requiring the publisher to hold the agent's own ceiling would be reading authority in
order to decide audience: the conflation `brain.agents.model.AUDIENCE_IS_NOT_AUTHORITY`
exists to refuse, arriving in the direction that looks safe. It would also refuse the person
the leaf names. A Super Admin deliberately not granted Finance's data could not publish
Finance's agent, while publishing it would still let them read nothing, because their own run
is intersected down to their own set.

What a publication does widen is `A_HIDDEN_AGENT_AND_A_MISSING_AGENT_ARE_ONE_ANSWER`, and it
suspends it on purpose for one record: an agent outside somebody's audience and an agent that
does not exist are the same answer until this function turns absence into presence for all of
them at once. So the capability is named for that act and for this object, and the gate is the
second pair of eyes rather than a reach test. See
`A_PUBLICATION_WIDENS_WHO_IS_TOLD_AND_NEVER_WHAT_IS_REACHED`.

**Rejected: reusing `brain.knowledge.visibility.PROMOTION_CAPABILITY`.** The levels are that
module's and `brain.agents.model` argues at length for not writing a second enum, so reusing
its capability looks like the same economy. It is not. `approve:knowledge.visibility` is a
noun about documents, and somebody granted it so a team lead may publish a handbook has not
been asked whether they may put an agent in front of 126 people. That is
`brain.ops.outbox`'s argument about `admin:webhooks` and `admin:webhook_subscriber`: a
capability whose name does not match what it governs is checked by whoever reads the name.
The width comparison is still that module's, because `is_wider` is the one implementation of
which way the three levels run.

**Rejected: an `unpublish`, or any narrowing of audience.** Narrowing takes an agent away
from people who are using it, which is a different decision with different consequences from
never having shown it to them, and `PromotionProposal` already refuses a narrowing down the
widening path for the same reason. The retire half of M33.1.2.1 is `archive`, which stops the
agent for everybody rather than returning it to a smaller audience, and a general audience
narrowing needs its own argument and its own leaf.

`agents_needing_transfer` is the one listing in this package not filtered by audience,
and that is its whole purpose.** A personal agent whose owner has gone is reachable by
nobody: `visible_agent_ids` correctly returns nothing for it, for every viewer, for ever.
Finding those rows therefore cannot be an audience question. It is keyed by the ids the
caller named, never by a scan of who owns what, which is the rule
`brain.core.department.plan_cross_department` states about the department list it is handed:
a function that took the estate and reported every owner would be an org chart with agent
counts on it.

Task ids: M13.1.4, M13.1.5
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Final

from brain.agents.model import AgentAudience, AgentError, AgentRecord, AgentState
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.principal import Principal
from brain.knowledge.visibility import Visibility, is_wider

#: Why archive has no inverse, stated where a reader meets it.
ARCHIVE_IS_TERMINAL: Final = (
    "Archiving an agent is a decision that it is finished, and there is no function here "
    "that undoes it. Enable and disable refuse an archived record rather than quietly "
    "doing nothing, so a caller that believes it brought an agent back is told otherwise. "
    "A reversible archive is a disable with a longer name, and two controls that differ "
    "only in wording are one control somebody will use interchangeably."
)

#: Why a publication takes an agreement rather than the reach test a grant takes.
A_PUBLICATION_WIDENS_WHO_IS_TOLD_AND_NEVER_WHAT_IS_REACHED: Final = (
    "Publishing an agent moves its audience to the company and moves nobody's reach at all: "
    "a run through it is still the caller's entitlement intersected with the agent's "
    "ceiling, and neither side of that intersection mentions who may see the agent. So the "
    "two questions brain.console.scoped_authority.may_grant asks about a grant are the wrong "
    "questions here, and the second of them is actively wrong: requiring the publisher to "
    "hold every capability in the ceiling would let authority decide audience, which is the "
    "conflation the agent model exists to refuse, and it would refuse a Super Admin "
    "publishing a department's agent while protecting nothing, because publishing it lets "
    "them read none of it. What the act does widen is who is told the agent exists, so it "
    "takes a capability named for that and a second person to perform it."
)

#: Why the person answering for an agent is not the person who may publish it.
A_GATE_ONE_PERSON_PASSES_ALONE_IS_NOT_A_GATE: Final = (
    "brain.knowledge.visibility.approve_promotion refuses an approver who is the proposer, "
    "and brain.builder.publish refuses the author as one of a publish's approvers. This is "
    "the same refusal at the audience axis, and the steward is exactly the person it has to "
    "name: the persona is text they wrote, they are the one reader who cannot come to it "
    "fresh, and they are the one person with a reason to want it in front of everybody. The "
    "way past it is another person, which is the whole content of the rule, and not a "
    "second function with a friendlier name."
)

#: Why a transfer is safe to perform without re-approving anything.
A_TRANSFER_MOVES_THE_STEWARD_AND_NOT_THE_REACH: Final = (
    "Ownership names who answers for an agent. It is not a grant, it is not a ceiling and "
    "it is not an entitlement: a run's reach is its caller's entitlement intersected with "
    "the agent's ceiling, and neither side of that mentions the owner. So handing an agent "
    "to somebody with wider access does not widen the agent, and handing it to somebody "
    "with narrower access does not narrow it. What a transfer does change is the audience "
    "of a personal agent, because at that level the steward is the audience."
)

#: The capability that decides whether an agent may be shown to the whole company.
#:
#: Named in the module that performs the transition, which is what
#: `brain.console.scoped_authority` and `brain.console.global_surfaces` both refuse to do
#: from the rendering layer: a capability invented where a screen is drawn is one the
#: administrator reviewing grants never meets. The noun is `agent`, the same noun the
#: `agents` screen reads under, so the act and the screen govern one object; the verb is
#: `approve`, because a publication is somebody agreeing to a widening rather than reading
#: one. `brain.ops.halt.HALT_CAPABILITY` and `brain.ops.outbox.MANAGE_SUBSCRIBERS` are named
#: the same way and in the same position.
AGENT_PUBLICATION_CAPABILITY: Final = Capability(value="approve:agent.visibility")

#: The one level `publish` moves an agent to.
#:
#: A constant rather than a parameter, and the absence of the parameter is the guarantee:
#: there is no argument to this module's publication path that could name a narrower level,
#: so nothing here can take an agent away from people who can currently see it.
PUBLICATION_LEVEL: Final = Visibility.COMPANY


def _revalidated(record: AgentRecord, **changes: object) -> AgentRecord:
    """A copy of a record with the changes applied and every validator run again.

    `model_copy(update=...)` is the obvious way to write this and is wrong here: it skips
    validation entirely, so a naive `disabled_at` would be stored by the one path that ever
    writes that column, and the validator refusing naive timestamps would be dead code that
    still passes its own test.
    """
    fields = {name: getattr(record, name) for name in type(record).model_fields}
    return AgentRecord.model_validate({**fields, **changes})


def _refuse_if_archived(record: AgentRecord, verb: str) -> None:
    """Archived is terminal, and saying so beats doing nothing quietly.

    A no-op return would leave the caller believing the agent is available again, and the
    next thing they do is wonder why it never answers.
    """
    if record.state is AgentState.ARCHIVED:
        msg = (
            f"{record.agent_id!r} was archived on {record.archived_at} and cannot be "
            f"{verb}; an archived agent is finished, and bringing one back is creating one"
        )
        raise AgentError(msg)


def enable(record: AgentRecord) -> AgentRecord:
    """Make an agent selectable again (M13.1.4).

    Takes no `now`, because enabling clears a timestamp rather than writing one. When it
    happened belongs in `obs.audit_entry`, which records who did it as well; a
    `re_enabled_at` column here would be a second, partial history that nothing reads and
    that disagrees with the ledger the first time one of the two writes fails.

    Enabling an already enabled agent returns the same record rather than raising. A retry
    after a timeout must not fail, and there is nothing to refuse: the caller asked for a
    state the record is already in.
    """
    _refuse_if_archived(record, "enabled")
    if record.disabled_at is None:
        return record
    return _revalidated(record, disabled_at=None)


def disable(record: AgentRecord, *, now: datetime) -> AgentRecord:
    """Stop an agent being selected, reversibly (M13.1.4).

    Disabling an already disabled agent keeps the original timestamp. The first disabling is
    the one somebody decided; overwriting it on a retry would move the date of a decision to
    the date of a duplicate request, and the moved date is the one an incident review reads.
    """
    _refuse_if_archived(record, "disabled")
    if record.disabled_at is not None:
        return record
    return _revalidated(record, disabled_at=now)


def archive(record: AgentRecord, *, now: datetime) -> AgentRecord:
    """Retire an agent for good (M13.1.4).

    The row stays. Nothing here deletes an agent, because the ledger refers to it by id and
    a run recorded against a row that no longer exists is a trace nobody can read. An
    archived agent keeps its persona, its ceiling and its history, and is selectable by
    nobody: `AgentRecord.is_selectable` is false, so `runnable_agent_ids` leaves it out.

    Archiving an already archived agent keeps the first timestamp, for the reason `disable`
    gives. It does not raise: the record is in the state that was asked for, and the
    refusals in `enable` and `disable` are about a state change that would undo this one.
    """
    if record.state is AgentState.ARCHIVED:
        return record
    return _revalidated(record, archived_at=now)


def publish(record: AgentRecord, *, publisher: EntitlementSet, now: datetime) -> AgentRecord:
    """Show an agent to the whole company. The transition M33.1.2.1 had no function for.

    Three refusals and one no-op, and the argument for each is in the module docstring.

    **The agent is not archived.** Archived is terminal, so publishing one would put a thing
    nobody can start in front of everybody, and `enable` already refuses to bring it back.

    **The publisher is not the steward.** See `A_GATE_ONE_PERSON_PASSES_ALONE_IS_NOT_A_GATE`.

    **The publisher holds `AGENT_PUBLICATION_CAPABILITY`.** Absence of a grant is why this
    refuses; nothing subtracts, because there is no deny list anywhere in this system. It is
    deliberately not the pair `brain.console.scoped_authority.may_grant` asks for, and not
    `brain.knowledge.visibility.PROMOTION_CAPABILITY`. See
    `A_PUBLICATION_WIDENS_WHO_IS_TOLD_AND_NEVER_WHAT_IS_REACHED`.

    Publishing an already published agent returns the same record rather than raising, for
    the reason `enable` gives: a retry after a timeout must not fail, and there is nothing to
    refuse. The comparison is `brain.knowledge.visibility.is_wider` rather than an equality
    test, so which way the three levels run is decided in the one place that decides it.

    **There is no argument here that names a person, and that is why the entitlement is the
    only thing passed in.** `approve_promotion` takes an approver id beside an entitlement
    and has to check the two agree, because a handler with the wrong variable in scope
    approves on behalf of somebody never asked. Reading the publisher off
    `EntitlementSet.principal_id` means that mismatch cannot be written.

    **Says nothing about the lifecycle beyond the terminal state.** A disabled agent can be
    published, and it is invisible to `runnable_agent_ids` until somebody enables it. Making
    the order of two independent decisions load-bearing is the coupling this module refuses
    in the other direction when it keeps a state change away from the ceiling.

    The department is dropped, because `AgentAudience` refuses to carry one at any level but
    its own: a department on a company row reads as an audience and applies to nothing.
    That refusal is the reason this transition cannot be written anywhere else without
    somebody working around a validation error by keeping the field.
    """
    _refuse_if_archived(record, "published")
    if publisher.principal_id == record.audience.owner_id:
        msg = (
            f"{publisher.principal_id!r} answers for {record.agent_id!r} and cannot publish "
            f"it. {A_GATE_ONE_PERSON_PASSES_ALONE_IS_NOT_A_GATE}"
        )
        raise AgentError(msg)
    if not publisher.holds(AGENT_PUBLICATION_CAPABILITY, now):
        msg = (
            f"{publisher.principal_id!r} does not hold "
            f"{AGENT_PUBLICATION_CAPABILITY.value} and cannot publish {record.agent_id!r}; "
            "nobody has granted them the path that tells the whole company an agent exists"
        )
        raise AgentError(msg)
    if not is_wider(PUBLICATION_LEVEL, record.audience.level):
        return record
    # Built rather than copied, for the reason `transfer_ownership` gives below: pydantic
    # does not revalidate a model instance handed to a model field, so an audience that
    # kept its department would slip past both this constructor and the record's rebuild.
    published = AgentAudience(
        level=PUBLICATION_LEVEL,
        owner_id=record.audience.owner_id,
        department="",
    )
    return _revalidated(record, audience=published)


def transfer_ownership(record: AgentRecord, *, to_owner: Principal, now: datetime) -> AgentRecord:
    """Hand an agent to a new steward (M13.1.5).

    Three refusals, and each one is a way an offboarding run silently does nothing useful.

    **The new steward is somebody else.** A transfer to the current owner writes a record of
    a decision nobody made, and on a leaver's estate it would report success for exactly the
    agents that still have no live owner.

    **The new steward is still here.** `Principal.is_active` is the existing check and it is
    asked with the caller's `now`. Without it, an offboarding that runs down a list hands one
    leaver's agents to another leaver, and both sets of rows look correctly owned.

    **The agent is not archived.** An archived agent cannot be seen, started or brought back,
    so there is nothing for a steward to answer for. Transferring one would put a decision in
    the record that changes nothing observable, and `agents_needing_transfer` leaves archived
    rows out for the same reason.

    What comes back differs from what went in by one field. `created_by` does not move: it is
    the record of who built the agent, which is what an audit asks, and the steward is what
    everybody else asks. The authority is passed through untouched, and there is no argument
    here that could change it.
    """
    if record.state is AgentState.ARCHIVED:
        msg = (
            f"{record.agent_id!r} is archived and has no steward to transfer; "
            "an archived agent is answerable for nothing"
        )
        raise AgentError(msg)
    if to_owner.id == record.audience.owner_id:
        msg = (
            f"{record.agent_id!r} already belongs to {to_owner.id!r}; a transfer to the "
            "current owner records a decision nobody made and leaves the agent unowned "
            "when the owner is the person leaving"
        )
        raise AgentError(msg)
    if not to_owner.is_active(now):
        msg = (
            f"{to_owner.id!r} is not active at {now.isoformat()} and cannot take "
            f"{record.agent_id!r}; handing a leaver's agents to another leaver leaves rows "
            "that look owned and are not"
        )
        raise AgentError(msg)
    # Built rather than copied with an update, and the reason is stronger than the one
    # `_revalidated` gives: pydantic does not revalidate a model instance handed to a model
    # field, so an audience produced by `model_copy` would slip past this constructor's
    # checks and past the record's rebuild as well, which is every check there is.
    moved = AgentAudience(
        level=record.audience.level,
        owner_id=to_owner.id,
        department=record.audience.department,
    )
    return _revalidated(record, audience=moved)


def agents_needing_transfer(
    records: Iterable[AgentRecord], *, departing: frozenset[str]
) -> tuple[str, ...]:
    """The ids of live agents whose steward is on the way out (M13.1.5).

    `departing` is who the caller asked about, never a set this function derives. Reading
    every owner off the estate and reporting the ones who have left would be a different
    function with a different risk: an inventory of who owns what, produced by anybody who
    can call it.

    Archived agents are left out. They are answerable for nothing and `transfer_ownership`
    refuses them, so listing them would produce a queue of work that cannot be done.

    Sorted, so an offboarding runbook processes the same list in the same order twice, and
    returned as ids alone. There is no count of anything omitted.
    """
    return tuple(
        sorted(
            r.agent_id
            for r in records
            if r.state is not AgentState.ARCHIVED and r.audience.owner_id in departing
        )
    )
