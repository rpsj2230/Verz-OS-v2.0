"""Enable, disable, archive, handing an agent on, and showing it to the whole company.

Three rules carry the weight here and all three fail quietly.

**Archive has no inverse.** The refusals in `enable` and `disable` are the enforcement, and
`test_no_function_here_returns_an_archived_agent_to_service` is what stops a later
`unarchive` being added beside them without anybody noticing that the distinction between
the two off states has gone.

**A transfer moves the steward and nothing else.** It is one of two operations that
legitimately change an audience, so it is also an easy place to change a ceiling by accident,
and nothing about a wrongly widened agent announces itself.

**A publication widens who is told and never what is reached.** The capability it takes is
asserted by refusing the two capabilities it might plausibly have been, rather than by
comparing a constant with its own value, and the ceiling is compared either side of the
change. The publication tests claim no leaf: the transition is what was missing, and
`brain.console.global_surfaces` is where M33.1.2.1 is answered now that it exists.

Task ids: M13.1.4, M13.1.5
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from brain.agents import lifecycle
from brain.agents.lifecycle import (
    AGENT_PUBLICATION_CAPABILITY,
    PUBLICATION_LEVEL,
    agents_needing_transfer,
    archive,
    disable,
    enable,
    publish,
    transfer_ownership,
)
from brain.agents.model import (
    AgentAudience,
    AgentAuthority,
    AgentError,
    AgentRecord,
    AgentState,
    AgentViewer,
    entitlement_ceiling,
    runnable_agent_ids,
    tool_ceiling,
    visible_agent_ids,
    visible_to,
)
from brain.console.scoped_authority import REACH_AUTHORITY
from brain.console.screens import screen
from brain.core.department import department_scope
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Scope
from brain.knowledge.visibility import PROMOTION_CAPABILITY, Visibility

NOW = datetime(2026, 9, 6, 9, 0, tzinfo=UTC)
LATER = NOW + timedelta(days=1)

LEAVER = "u_wei_ling"
SUCCESSOR = "u_priya"
WEB = "web"

TRIAGE = "support_triage"
CHASER = "renewal_chaser"


def _authority() -> AgentAuthority:
    return AgentAuthority(
        scope=department_scope(WEB),
        capabilities=(Capability(value="read:client.name"),),
        allowed_tools=frozenset({"client.read_summary"}),
    )


def _record(
    *, agent_id: str = TRIAGE, audience: AgentAudience | None = None, **overrides: object
) -> AgentRecord:
    fields: dict[str, object] = {
        "agent_id": agent_id,
        "display_name": "Support triage",
        "persona": "Answers support questions in the house voice.",
        "audience": audience or AgentAudience(level=Visibility.PERSONAL, owner_id=LEAVER),
        "authority": _authority(),
        "created_by": LEAVER,
    }
    fields.update(overrides)
    return AgentRecord.model_validate(fields)


def _principal(principal_id: str, *, not_after: datetime | None = None) -> Principal:
    return Principal(
        id=principal_id,
        kind=PrincipalKind.HUMAN,
        employment=Employment.CONTRACTOR if not_after else Employment.STAFF,
        display_name="Somebody",
        not_after=not_after,
    )


def _caller(principal_id: str = LEAVER) -> EntitlementSet:
    return EntitlementSet(
        principal_id=principal_id,
        grants=(
            Grant(capability=Capability(value="read:client.name"), scope=Scope.unrestricted()),
        ),
    )


def _viewer(principal_id: str, *departments: str) -> AgentViewer:
    return AgentViewer(principal_id=principal_id, departments=frozenset(departments))


def _publisher(
    *capabilities: Capability,
    principal_id: str = SUCCESSOR,
    not_after: datetime | None = None,
) -> EntitlementSet:
    """Somebody with exactly the capabilities named, company-wide.

    Defaults to the publication capability so that the refusal tests can each remove one
    thing, rather than each assembling a whole entitlement and differing in two ways.
    """
    held = capabilities or (AGENT_PUBLICATION_CAPABILITY,)
    return EntitlementSet(
        principal_id=principal_id,
        grants=tuple(Grant(capability=c, scope=Scope.unrestricted()) for c in held),
        not_after=not_after,
    )


# ---------------------------------------------------------------- the three states (M13.1.4)
def test_disabling_an_agent_stops_it_being_selected() -> None:
    """The whole point of the control. A disable that left the agent selectable would be a
    switch with no effect, and the person who used it would find out from an answer they
    thought they had stopped."""
    off = disable(_record(), now=NOW)
    assert off.state is AgentState.DISABLED
    assert off.disabled_at == NOW
    assert runnable_agent_ids([off], _viewer(LEAVER)) == frozenset()


def test_enabling_a_disabled_agent_brings_it_back() -> None:
    """The sibling every refusal needs. A lifecycle tested only by what it stops is satisfied
    by one that stops everything, and an agent nobody can re-enable is one somebody rebuilds
    from scratch with a ceiling nobody reviewed."""
    record = _record()
    back = enable(disable(record, now=NOW))
    assert back.disabled_at is None
    assert back.state is AgentState.ENABLED
    assert runnable_agent_ids([back], _viewer(LEAVER)) == frozenset({TRIAGE})


def test_disabling_twice_keeps_the_date_of_the_first_decision() -> None:
    """The first disabling is the one somebody decided. Overwriting it on a retry moves the
    date of a decision to the date of a duplicate request, and the moved date is the one an
    incident review reads when it asks when the agent stopped answering."""
    twice = disable(disable(_record(), now=NOW), now=LATER)
    assert twice.disabled_at == NOW


def test_enabling_an_already_enabled_agent_changes_nothing() -> None:
    """Idempotent on purpose: a retry after a timeout must not fail, and there is nothing to
    refuse because the caller asked for the state the record is already in."""
    record = _record()
    assert enable(record) is record


def test_archiving_retires_an_agent_without_removing_the_row() -> None:
    """The ledger refers to agents by id, so a run recorded against a row that no longer
    exists is a trace nobody can read. An archived agent keeps its persona and its ceiling and
    is selectable by nobody."""
    gone = archive(_record(), now=NOW)
    assert gone.state is AgentState.ARCHIVED
    assert gone.archived_at == NOW
    assert gone.persona == _record().persona
    assert runnable_agent_ids([gone], _viewer(LEAVER)) == frozenset()


def test_an_archived_agent_cannot_be_enabled() -> None:
    """`ARCHIVE_IS_TERMINAL`. Refused rather than quietly doing nothing: a no-op would leave
    the caller believing the agent is available again, and the next thing they do is wonder
    why it never answers."""
    with pytest.raises(AgentError, match="cannot be enabled"):
        enable(archive(_record(), now=NOW))


def test_an_archived_agent_cannot_be_disabled() -> None:
    """The same rule from the other side. Without it, `disable` on an archived record returns
    a record and the caller concludes archive and disable are interchangeable, which is
    exactly the collapse that makes two controls into one."""
    with pytest.raises(AgentError, match="cannot be disabled"):
        disable(archive(_record(), now=NOW), now=LATER)


def test_archiving_an_already_archived_agent_keeps_the_first_date() -> None:
    """Idempotent, like `disable`, and for the same reason. It does not raise: the record is
    in the state that was asked for, and the refusals above are about undoing this one."""
    twice = archive(archive(_record(), now=NOW), now=LATER)
    assert twice.archived_at == NOW


def test_an_agent_archived_after_being_disabled_reads_as_archived() -> None:
    """Both columns can be set at once, legitimately, and the precedence has to be stated
    rather than implied. Reading such a record as merely disabled would offer an archived
    agent to `enable`, which is the one thing that must not work."""
    both = archive(disable(_record(), now=NOW), now=LATER)
    assert both.disabled_at == NOW
    assert both.archived_at == LATER
    assert both.state is AgentState.ARCHIVED


def test_a_state_change_never_touches_the_ceiling() -> None:
    """Disabling is not a narrowing and enabling is not a widening. The alternative design,
    emptying the ceiling on disable and restoring it on enable, is a data migration disguised
    as a toggle, and the restore is where a ceiling comes back wrong.

    Delete this and a lifecycle function is free to acquire an argument that changes reach."""
    record = _record()
    for changed in (disable(record, now=NOW), enable(record), archive(record, now=NOW)):
        assert changed.authority == record.authority
        assert tool_ceiling(changed) == tool_ceiling(record)
        assert entitlement_ceiling(changed).ent_hash() == entitlement_ceiling(record).ent_hash()


def test_a_naive_timestamp_cannot_be_written_by_a_state_change() -> None:
    """The reason these functions rebuild the record rather than calling `model_copy`.

    `model_copy(update=...)` skips validation entirely, so the one path that ever writes
    `disabled_at` would be the one path that could write a naive datetime, and the validator
    refusing them would be dead code that still passes its own test."""
    with pytest.raises(ValueError, match="timezone-aware"):
        disable(_record(), now=datetime(2026, 9, 6, 9, 0))


#: What the generic call below can supply. Anything a function here asks for that is not in
#: this pool leaves it unexercised, which the test then says out loud.
def _argument_pool(archived: AgentRecord) -> dict[str, Any]:
    return {
        "record": archived,
        "records": [archived],
        "now": LATER,
        "to_owner": _principal(SUCCESSOR),
        "departing": frozenset({LEAVER}),
        "publisher": _publisher(),
    }


def test_no_function_here_returns_an_archived_agent_to_service() -> None:
    """`ARCHIVE_IS_TERMINAL` asserted against the module's whole surface rather than against
    the two functions that happen to exist today.

    The refusals in `enable` and `disable` are checked above one at a time. This asks the
    question those cannot: whether anything in this module, including something added later,
    hands back a record that is no longer archived. An `unarchive` written next to them would
    read as symmetry and would pass every other test in this file.

    The count is asserted so this cannot pass by exercising nothing, which is the failure
    `brain.ops.sweeps.sweep_traceability` had for its whole life."""
    archived = archive(_record(), now=NOW)
    pool = _argument_pool(archived)
    exercised = 0
    for name, function in inspect.getmembers(lifecycle, inspect.isfunction):
        if name.startswith("_") or function.__module__ != lifecycle.__name__:
            continue
        parameters = inspect.signature(function).parameters
        if not set(parameters) <= set(pool):
            continue
        exercised += 1
        try:
            result = function(**{p: pool[p] for p in parameters})
        except AgentError:
            continue
        if isinstance(result, AgentRecord):
            assert result.state is AgentState.ARCHIVED, f"{name} revived an archived agent"
    assert exercised >= 4, f"only {exercised} function(s) were reachable with these arguments"


# ------------------------------------------------------------- ownership transfer (M13.1.5)
def test_a_transfer_moves_the_steward_and_leaves_the_reach_alone() -> None:
    """The rule in `A_TRANSFER_MOVES_THE_STEWARD_AND_NOT_THE_REACH`, and the M13.1.3 property
    at the one moment it is most likely to break.

    Ownership is not a grant. An agent handed to somebody with wider access does not thereby
    reach more, because a run's reach is its caller's entitlement intersected with the
    agent's ceiling and neither side of that mentions the owner. Compared on `ent_hash` and
    on the ceiling object, so a change to any part of the authority fails here."""
    record = _record()
    moved = transfer_ownership(record, to_owner=_principal(SUCCESSOR), now=NOW)
    assert moved.audience.owner_id == SUCCESSOR
    assert moved.authority == record.authority
    assert tool_ceiling(moved) == tool_ceiling(record)
    caller = _caller()
    assert (
        caller.intersect(entitlement_ceiling(moved)).ent_hash()
        == caller.intersect(entitlement_ceiling(record)).ent_hash()
    )


def test_transferring_a_personal_agent_moves_who_can_see_it() -> None:
    """The one thing a transfer does change, and the reason it is worth doing: at the personal
    level the steward is the audience, so the agent follows its new owner and stops following
    the person who left.

    Delete this and a transfer that updated some other column would pass every other test
    while leaving a departed employee's agents visible to nobody at all."""
    record = _record()
    moved = transfer_ownership(record, to_owner=_principal(SUCCESSOR), now=NOW)
    assert visible_to(moved.audience, _viewer(SUCCESSOR))
    assert not visible_to(moved.audience, _viewer(LEAVER))


def test_transferring_a_department_agent_does_not_move_who_can_see_it() -> None:
    """The level is what decides the audience, and only the personal level names a person. A
    department agent handed to a new steward stays visible to the same department, so a
    transfer cannot quietly narrow a team's tooling to whoever happens to own it."""
    record = _record(
        audience=AgentAudience(level=Visibility.DEPARTMENT, owner_id=LEAVER, department=WEB)
    )
    moved = transfer_ownership(record, to_owner=_principal(SUCCESSOR), now=NOW)
    everyone_in_web = _viewer("u_someone_else", WEB)
    assert visible_to(record.audience, everyone_in_web)
    assert visible_to(moved.audience, everyone_in_web)


def test_the_creator_is_not_moved_by_a_transfer() -> None:
    """`created_by` is history and `owner_id` is the current answer. Overwriting the first
    with the second loses who built the thing, which is what an audit asks after an agent
    does something surprising, and there is no other record of it."""
    moved = transfer_ownership(_record(), to_owner=_principal(SUCCESSOR), now=NOW)
    assert moved.created_by == LEAVER
    assert moved.audience.owner_id == SUCCESSOR


def test_a_transfer_to_the_current_owner_is_refused() -> None:
    """It records a decision nobody made, and on an offboarding run it would report success
    for exactly the agents that still have no live steward: the list is walked, every call
    returns a record, and nothing has moved."""
    with pytest.raises(AgentError, match="already belongs to"):
        transfer_ownership(_record(), to_owner=_principal(LEAVER), now=NOW)


def test_a_transfer_to_somebody_who_has_also_left_is_refused() -> None:
    """`Principal.is_active` is asked with the caller's `now`, which is why the new steward is
    passed as a principal and not as an id. Without this, an offboarding that walks a list
    hands one leaver's agents to another leaver and both sets of rows look correctly owned."""
    gone = _principal(SUCCESSOR, not_after=NOW - timedelta(days=1))
    with pytest.raises(AgentError, match="is not active"):
        transfer_ownership(_record(), to_owner=gone, now=NOW)


def test_a_transfer_to_somebody_whose_engagement_ends_later_is_allowed() -> None:
    """The sibling of the refusal above. A contractor with a future end date is here today,
    and refusing them would leave the agents of everybody who leaves with only permanent staff
    to go to, which on this estate is a queue that does not clear."""
    still_here = _principal(SUCCESSOR, not_after=NOW + timedelta(days=30))
    moved = transfer_ownership(_record(), to_owner=still_here, now=NOW)
    assert moved.audience.owner_id == SUCCESSOR


def test_an_archived_agent_cannot_be_transferred() -> None:
    """It is answerable for nothing: not visible, not selectable, not revivable. A transfer
    would put a decision in the record that changes nothing observable, and
    `agents_needing_transfer` leaves archived rows out for the same reason, so the pair stays
    coherent."""
    with pytest.raises(AgentError, match="has no steward to transfer"):
        transfer_ownership(archive(_record(), now=NOW), to_owner=_principal(SUCCESSOR), now=LATER)


def test_a_transfer_leaves_the_record_it_was_given_untouched() -> None:
    """Frozen records, so the before and the after are both holdable. A transfer that mutated
    in place would leave the caller unable to show what changed, which is the one thing an
    ownership change has to be able to show."""
    record = _record()
    transfer_ownership(record, to_owner=_principal(SUCCESSOR), now=NOW)
    assert record.audience.owner_id == LEAVER


# --------------------------------------------------------- finding the work (M13.1.5)
def test_the_agents_a_leaver_owns_are_findable_when_nobody_can_see_them() -> None:
    """The reason this listing is not filtered by audience.

    A personal agent whose steward has gone is reachable by no viewer at all: `visible_to`
    correctly answers no for everybody, for ever. If finding those rows were an audience
    question, the agents that most need a new owner would be the ones nothing could list."""
    orphan = _record()
    assert visible_agent_ids([orphan], _viewer(SUCCESSOR)) == frozenset()
    assert agents_needing_transfer([orphan], departing=frozenset({LEAVER})) == (TRIAGE,)


def test_it_names_only_the_people_it_was_asked_about() -> None:
    """`departing` is what the caller named, never a set this function derives. A version that
    read every owner and worked out who had left would be an inventory of who owns what,
    produced by anybody who can call it, which is the same refusal
    `plan_cross_department` makes about the department list it is handed."""
    theirs = _record(agent_id=TRIAGE)
    somebody_else_s = _record(
        agent_id=CHASER,
        audience=AgentAudience(level=Visibility.PERSONAL, owner_id=SUCCESSOR),
    )
    assert agents_needing_transfer([theirs, somebody_else_s], departing=frozenset({LEAVER})) == (
        TRIAGE,
    )


def test_it_leaves_out_agents_that_are_already_archived() -> None:
    """They are answerable for nothing and `transfer_ownership` refuses them, so listing them
    would produce a queue of work that cannot be done, and a runbook that cannot be completed
    is one somebody stops running."""
    live = _record(agent_id=TRIAGE)
    retired = archive(_record(agent_id=CHASER), now=NOW)
    assert agents_needing_transfer([live, retired], departing=frozenset({LEAVER})) == (TRIAGE,)


def test_it_still_names_an_agent_somebody_disabled_on_their_way_out() -> None:
    """Disabled is not finished. An agent switched off during a handover still needs somebody
    who answers for it, and excluding it would leave the estate holding agents that can be
    re-enabled by a person who no longer works here."""
    off = disable(_record(), now=NOW)
    assert agents_needing_transfer([off], departing=frozenset({LEAVER})) == (TRIAGE,)


def test_the_queue_is_ordered_the_same_way_twice() -> None:
    """An offboarding runbook processes the same list in the same order on a re-run, so a
    partially completed handover can be resumed by reading down the list rather than by
    working out which half was done."""
    records = [
        _record(agent_id=CHASER),
        _record(agent_id=TRIAGE),
    ]
    assert agents_needing_transfer(records, departing=frozenset({LEAVER})) == (CHASER, TRIAGE)
    assert agents_needing_transfer(list(reversed(records)), departing=frozenset({LEAVER})) == (
        CHASER,
        TRIAGE,
    )


# --------------------------------------------------------------- publication (M33.1.2.1)
def _department_agent() -> AgentRecord:
    return _record(
        audience=AgentAudience(level=Visibility.DEPARTMENT, owner_id=LEAVER, department=WEB)
    )


def test_publishing_an_agent_shows_it_to_somebody_who_could_not_see_it() -> None:
    """The positive case, and the whole reason the function exists.

    A guard tested only by its refusals is satisfied by a function that refuses everything,
    and this one has three refusals. Delete this and `publish` could raise on every input
    while every other test in this section still passed."""
    outsider = _viewer("u_outsider")
    agent = _department_agent()
    assert not visible_to(agent.audience, outsider)

    published = publish(agent, publisher=_publisher(), now=NOW)

    assert published.audience.level is PUBLICATION_LEVEL
    assert visible_to(published.audience, outsider)
    assert runnable_agent_ids([published], outsider) == frozenset({TRIAGE})


def test_publishing_a_department_agent_drops_the_department_it_came_from() -> None:
    """`AgentAudience` refuses a department at any level but its own, so a publication that
    carried one through would raise inside the constructor.

    That refusal is why this transition cannot live in a console module: the obvious way past
    a validation error is to keep the field, and a department on a company row reads as an
    audience while applying to nothing. Delete this and the drop becomes incidental."""
    published = publish(_department_agent(), publisher=_publisher(), now=NOW)
    assert published.audience.department == ""
    assert published.audience.owner_id == LEAVER


def test_a_publication_does_not_widen_what_the_agent_may_reach() -> None:
    """`AUDIENCE_IS_NOT_AUTHORITY` at the one moment the audience deliberately moves.

    An agent published to everybody that came to reach more would turn a visibility change
    made in a console into a grant nobody wrote. Delete this and `publish` is free to acquire
    an argument that touches the ceiling, which is what the sibling test above says about the
    three state changes."""
    agent = _department_agent()
    published = publish(agent, publisher=_publisher(), now=NOW)
    assert published.authority == agent.authority
    assert tool_ceiling(published) == tool_ceiling(agent)
    assert entitlement_ceiling(published).ent_hash() == entitlement_ceiling(agent).ent_hash()


def test_the_steward_cannot_publish_their_own_agent() -> None:
    """`A_GATE_ONE_PERSON_PASSES_ALONE_IS_NOT_A_GATE`, and the steward is the person it names.

    The persona is text they wrote and they are the one reader who cannot come to it fresh.
    Delete this and the one person with a reason to want an agent in front of everybody is
    also the person who can put it there, with the record reading as a correct publication."""
    with pytest.raises(AgentError, match="answers for"):
        publish(_department_agent(), publisher=_publisher(principal_id=LEAVER), now=NOW)


def test_somebody_holding_nothing_cannot_publish_an_agent() -> None:
    """Absence of a grant is why this refuses; nothing subtracts, because there is no deny
    list anywhere in this system.

    Delete this and the capability constant is decoration: every caller passes."""
    nobody = EntitlementSet(principal_id=SUCCESSOR)
    with pytest.raises(AgentError, match=AGENT_PUBLICATION_CAPABILITY.value):
        publish(_department_agent(), publisher=nobody, now=NOW)


def test_the_authority_to_write_grants_does_not_publish_an_agent() -> None:
    """`brain.console.scoped_authority.REACH_AUTHORITY` is what a widening *grant* takes, and
    a publication is not one: `E_run` has no term for the audience, so a published agent
    hands nobody a row.

    Asserted as behaviour rather than as a string comparison, so repointing
    `AGENT_PUBLICATION_CAPABILITY` at `approve:grant` fails here rather than passing a test
    that compares the constant against itself."""
    with pytest.raises(AgentError, match=AGENT_PUBLICATION_CAPABILITY.value):
        publish(_department_agent(), publisher=_publisher(REACH_AUTHORITY), now=NOW)


def test_the_knowledge_promotion_capability_does_not_publish_an_agent() -> None:
    """The rejected reuse, asserted rather than argued.

    The levels are `brain.knowledge.visibility`'s and the capability is not: somebody granted
    `approve:knowledge.visibility` so a team lead may publish a handbook has not been asked
    whether they may put an agent in front of the whole company. Delete this and the two can
    be collapsed by an edit to one line, with every other test here still green."""
    with pytest.raises(AgentError, match=AGENT_PUBLICATION_CAPABILITY.value):
        publish(_department_agent(), publisher=_publisher(PROMOTION_CAPABILITY), now=NOW)


def test_the_publication_capability_governs_the_object_the_agents_screen_reads() -> None:
    """The capability is pinned against something outside itself, which is what stops a
    constant being compared with its own value.

    Its noun is the `agents` screen's own noun, so the act and the screen govern one object;
    its verb is not that screen's, because reading a list of agents and agreeing to show one
    to everybody are different decisions. `brain.console.scoped_authority.authority_gaps`
    pins its two capabilities against their screens the same way and for the same reason."""
    reading = screen("agents").read.requires
    assert AGENT_PUBLICATION_CAPABILITY.noun == reading.noun
    assert AGENT_PUBLICATION_CAPABILITY.verb == "approve"
    assert reading != AGENT_PUBLICATION_CAPABILITY
    assert AGENT_PUBLICATION_CAPABILITY != PROMOTION_CAPABILITY


def test_publishing_an_already_published_agent_changes_nothing() -> None:
    """A retry after a timeout must not fail, which is the argument `enable` makes about
    being asked for a state the record is already in.

    Identity rather than equality, deliberately: a rebuilt record compares equal to the one
    that went in, so an equality assertion would pass for an implementation that rewrote the
    audience on every call and would not notice `is_wider` being replaced by a constant."""
    already = publish(_department_agent(), publisher=_publisher(), now=NOW)
    assert publish(already, publisher=_publisher(), now=NOW) is already


def test_an_archived_agent_cannot_be_published() -> None:
    """`ARCHIVE_IS_TERMINAL` at the audience axis. Publishing a retired agent would put a
    thing nobody can start in front of everybody, and the person who finds it has no way to
    tell it from an agent that is simply not answering."""
    retired = archive(_department_agent(), now=NOW)
    with pytest.raises(AgentError, match="cannot be published"):
        publish(retired, publisher=_publisher(), now=LATER)


def test_a_publisher_whose_own_grant_has_expired_cannot_publish() -> None:
    """`now` is passed to `holds` rather than left to default to the wall clock.

    An expired principal holds nothing whatever the grant table still says, and a publication
    is the widest single act in this module. Delete this and the time argument can be dropped
    from the capability check, which reads as a simplification and makes every refusal depend
    on when the process happens to be running rather than on the decision's own instant."""
    expired = _publisher(not_after=NOW - timedelta(hours=1))
    with pytest.raises(AgentError, match=AGENT_PUBLICATION_CAPABILITY.value):
        publish(_department_agent(), publisher=expired, now=NOW)

    still_here = _publisher(not_after=NOW + timedelta(hours=1))
    published = publish(_department_agent(), publisher=still_here, now=NOW)
    assert published.audience.level is PUBLICATION_LEVEL


def test_nothing_in_the_publication_path_can_name_a_narrower_level() -> None:
    """`PUBLICATION_LEVEL` is a constant and not a parameter, and the absence of the parameter
    is the guarantee rather than the constant.

    Narrowing an audience takes an agent away from people using it, which is a different
    decision with different consequences from never having shown it to them. Delete this and
    a `level` argument can be added to `publish`, at which point the one function that widens
    is also the one function that narrows and nothing in the module says so."""
    parameters = inspect.signature(publish).parameters
    assert "level" not in parameters
    assert not [
        name
        for name, p in parameters.items()
        if p.annotation in {Visibility, "Visibility", AgentAudience, "AgentAudience"}
    ]
    assert PUBLICATION_LEVEL is Visibility.COMPANY
