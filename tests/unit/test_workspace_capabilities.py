"""The capabilities tab held to the rules that stop it becoming an inventory of the install.

Every row on this tab is a list of things that exist, which is the shape a permission model
leaks through most quietly. A connector row lists the sources installed here. A field list
names columns in somebody's source system. A knowledge preview counts documents. A channel row
says which surfaces this deployment can reach. Each is useful, each reads as documentation, and
each is a disclosure computed from the wrong reach the moment somebody writes it against the
agent instead of against the person looking.

The eight leaves claimed here are the ones where that distinction is the whole content. The
overflow count beside a connector row counts what is off the end of the row and never what is
out of reach (M39.2.1.1); the fields a connector projects are the ones this run would actually
return (M39.2.1.3); a connector the agent asked for is shown as requested only where an
attached one would have been (M39.2.1.4); health is the connector page's own answer and an
unprobed source has none (M39.2.1.5); a skill is attached from the approved library through a
path with no parameter a repository fits in (M39.2.2.2); a knowledge scope is a predicate with
nowhere to put a document list (M39.2.3.1); the preview counts the reader's own matching items
(M39.2.3.3); and a channel is offered only where this run could carry what it reaches
(M39.2.4.2).

Real `EntitlementSet`s, a real `FieldPolicy`, a real `ProjectedEntity`, real `KnowledgeItem`s
and a real `ImportedSkill` throughout, because every one of these rules is about how two real
modules meet.

Task ids: M39.2.1.1, M39.2.1.3, M39.2.1.4, M39.2.1.5, M39.2.2.2, M39.2.3.1, M39.2.3.3, M39.2.4.2
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from dataclasses import fields as dataclass_fields
from datetime import UTC, datetime

import pytest

from brain.agents.model import AgentAudience, AgentAuthority, AgentRecord, entitlement_ceiling
from brain.channels.adapter import ChannelCapabilities
from brain.connectors.contract import ConnectorHealth, HealthState
from brain.connectors.manifest import (
    ChangeSignal,
    FieldShape,
    HotUse,
    ProjectedEntity,
    ProjectedField,
)
from brain.console import workspace_capabilities as capabilities_module
from brain.console.workspace import Part, intersections_in
from brain.console.workspace_capabilities import (
    CAPABILITIES_SURFACE,
    ICONS_ON_THE_ROW,
    NAMES_THAT_WOULD_BE_A_REPOSITORY,
    PREDICATE_FIELDS,
    CapabilitiesError,
    ConnectorRow,
    ConnectorStrip,
    KnowledgeScope,
    Presence,
    attach_skill,
    capabilities_gaps,
    connector_rows,
    connector_strip,
    highest_classification,
    item_row,
    matching,
    offered_channels,
    preview_count,
    projected_for,
    run_reach,
)
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.field_policy import Classification, FieldPolicy, policy_from_rows
from brain.core.scope import Clause, Op, Scope
from brain.gate.context import Channel
from brain.knowledge.item import KnowledgeItem, KnowledgeState
from brain.knowledge.visibility import KnowledgeVisibility, Visibility
from brain.tools.skills import ImportedSkill, Skill, SkillError, SkillSource, SourceKind

AGENT = "support_triage"
READER = "p_reader"
NOW = datetime(2026, 1, 16, 12, 0, tzinfo=UTC)

#: A real policy, so a classification and a required capability are the same pair the
#: redactor reads. Two restricted fields, so a reach can hold one classification and not the
#: next, and one field left unclassified on purpose.
POLICY: FieldPolicy = policy_from_rows(
    [
        ("client", "id", "read:client.name", Classification.INTERNAL),
        ("client", "display_name", "read:client.name", Classification.INTERNAL),
        ("client", "status", "read:client.status", Classification.CONFIDENTIAL),
        ("client", "contract_value", "read:client.contract_value", Classification.RESTRICTED),
        ("ticket", "internal_note", "read:ticket.internal_note", Classification.CONFIDENTIAL),
    ]
)

#: The shape each projected field is declared with. Real shapes, because `ProjectedEntity`
#: enforces the tier table: a second label on one entity is refused, and so is a field on the
#: permanent denylist. A projection built to suit a test would not be a projection.
SHAPES: dict[str, tuple[FieldShape, HotUse]] = {
    "id": (FieldShape.IDENTIFIER, HotUse.IDENTIFY),
    "status": (FieldShape.STATUS, HotUse.FILTER),
    "display_name": (FieldShape.LABEL, HotUse.SORT),
    "lifecycle": (FieldShape.STATUS, HotUse.FILTER),
}


def holding(*capabilities: str) -> EntitlementSet:
    """A caller holding these capabilities company-wide."""
    return EntitlementSet(
        principal_id=READER,
        grants=tuple(
            Grant(capability=Capability(value=one), scope=Scope(clauses=())) for one in capabilities
        ),
    )


def a_record(*capabilities: str) -> AgentRecord:
    """One real agent whose ceiling admits exactly these capabilities."""
    return AgentRecord(
        agent_id=AGENT,
        display_name="Support triage",
        persona="Answers support questions in the house voice.",
        audience=AgentAudience(level=Visibility.PERSONAL, owner_id=READER),
        authority=AgentAuthority(capabilities=tuple(Capability(value=one) for one in capabilities)),
        created_by=READER,
    )


def a_projection(*names: str) -> ProjectedEntity:
    """One real projection of the client entity, declaring the fields named, in that order."""
    return ProjectedEntity(
        entity="client",
        fields=tuple(
            ProjectedField(name=one, shape=SHAPES[one][0], uses=(SHAPES[one][1],)) for one in names
        ),
        change_signal=ChangeSignal.UPDATED_SINCE,
        visibility=Scope.department("maintenance"),
    )


def a_probe(source: str, state: HealthState) -> ConnectorHealth:
    return ConnectorHealth(connector=source, state=state, checked_at=NOW)


def an_item(
    item_id: str,
    *,
    owner: str = READER,
    department: str = "web",
    state: KnowledgeState = KnowledgeState.PUBLISHED,
) -> KnowledgeItem:
    """One real knowledge item, published into a department."""
    return KnowledgeItem(
        item_id=item_id,
        content="the house standard says two spaces",
        visibility=KnowledgeVisibility.of_department(department, owner_id=owner),
        owner_id=owner,
        state=state,
        verified_by="p_admin",
        verified_at=NOW,
    )


def a_skill(*, approved: bool) -> ImportedSkill:
    """One real imported skill, approved by a named person or not reviewed at all."""
    skill = Skill(
        name="triage",
        description="Use when a ticket needs sorting into a queue.",
        version="1.2.3",
        body="Read the ticket, then choose the queue.",
    )
    imported = ImportedSkill(
        skill=skill,
        source=SkillSource(kind=SourceKind.UPLOAD, location="triage.zip", content_digest="a" * 64),
    )
    return imported.approved_by("p_admin", NOW) if approved else imported


def a_channel(channel: Channel, carries: Classification) -> ChannelCapabilities:
    return ChannelCapabilities(channel=channel, max_classification=carries)


# --- the tab is read at the intersection and computes none of it -----------------------------


def test_a_capabilities_row_is_read_at_the_run_reach_and_never_at_the_agents_ceiling() -> None:
    """`E_run(caller, agent) = E(caller) intersect agent_ceiling`, and every row on this tab
    is computed from it. Two people opening one agent see different rows, and neither sees
    anything the ceiling excludes.

    Both directions are asserted, because a reach that took the union rather than the
    intersection would pass a test that only checked the caller narrowed the agent.

    Delete this and `run_reach` can return the ceiling, and an agent published to a department
    hands its whole ceiling to everybody in it."""
    record = a_record("read:client.name", "read:client.contract_value")

    wide = run_reach(holding("read:client.name", "read:client.contract_value"), record)
    narrow = run_reach(holding("read:client.name"), record)
    outside = run_reach(holding("read:ticket.internal_note"), record)

    assert wide.holds(Capability(value="read:client.contract_value"))
    assert not narrow.holds(Capability(value="read:client.contract_value"))
    assert narrow.holds(Capability(value="read:client.name"))
    assert outside.grants == ()
    assert wide.principal_id == READER
    assert entitlement_ceiling(record).principal_id != READER


def test_this_tab_intersects_no_entitlement_sets_of_its_own() -> None:
    """The invariant's structural half, the same check `brain.console.workspace` makes of
    itself. `run_reach` calls `brain.console.reads.audience`, which is the console's one call
    into `EntitlementSet.intersect`; a second arithmetic here would be a third copy of the
    platform's central rule.

    Delete this and a helper on this tab starts narrowing a reach, and the copy that is
    subtly wrong is the one behind the page listing what an agent can reach."""
    assert intersections_in(inspect.getsource(capabilities_module)) == ()


# --- connectors: requested only where attached would have been (M39.2.1.4) -------------------


def test_a_connector_out_of_reach_produces_no_row_in_either_state() -> None:
    """**M39.2.1.4.** A manifest naming a connector is a fact about the agent; that nobody
    granted it is a fact about a grant. A row reading requested for a source this reader has
    never heard of tells them the source is installed here and that somebody decided they may
    not reach it.

    The positive half is the same agent read by somebody who can see both sources, which is
    what makes this a filter rather than a refusal: the requested row is the feature, and it
    appears the moment the reader could have seen an attached one.

    Delete this and the tab lists every source an agent's author ever named, to everybody."""
    declared = ["freshdesk", "xero"]

    narrow = connector_rows(declared=declared, attached=["freshdesk"], visible={"freshdesk"})
    wide = connector_rows(declared=declared, attached=["freshdesk"], visible={"freshdesk", "xero"})

    assert [(one.source, one.presence) for one in narrow] == [
        ("freshdesk", Presence.ATTACHED),
    ]
    assert [(one.source, one.presence) for one in wide] == [
        ("freshdesk", Presence.ATTACHED),
        ("xero", Presence.REQUESTED),
    ]


def test_a_connector_row_says_nothing_about_why_a_connector_is_not_attached() -> None:
    """Two states and no third. Anything meaning refused, pending or not granted is a fact
    about a grant on a row read by somebody who may not know the grant exists.

    The field names are pinned as well as the enum, because the same disclosure arrives as a
    `reason` string just as easily as it arrives as a fourth state.

    Delete this and `Presence.NOT_GRANTED` reads like an improvement."""
    assert {one.value for one in Presence} == {"attached", "requested"}
    assert {one.name for one in dataclass_fields(ConnectorRow)} == {
        "source",
        "presence",
        "projects",
        "health",
        "checked_at",
    }


# --- connectors: health is inherited (M39.2.1.5) ---------------------------------------------


def test_health_on_this_row_is_the_connector_pages_own_answer() -> None:
    """**M39.2.1.5.** A second opinion here is a source shown degraded on one page and
    healthy on the other, with nothing saying which is right. The state and the time are
    copied off `ConnectorHealth` rather than derived.

    A degraded source is the discriminating case: it is usable, which is the point of the
    state existing, so a row that only distinguished up from down would lose it.

    Delete this and the workspace grows its own idea of health, and the day the two disagree
    the reassuring one is on the page people open."""
    rows = connector_rows(
        declared=["freshdesk"],
        attached=["freshdesk"],
        visible={"freshdesk"},
        health={"freshdesk": a_probe("freshdesk", HealthState.DEGRADED)},
    )

    assert rows[0].health is HealthState.DEGRADED
    assert rows[0].checked_at == NOW


def test_a_connector_nobody_has_probed_carries_no_health_rather_than_a_healthy_one() -> None:
    """A green light after the prober has stopped is the failure that makes a health
    indicator worse than none, and an unprobed source rendered OK is that failure on day one.

    The constructor refuses half a reading as well, so a state cannot arrive without the time
    that makes it meaningful. That is `KnowledgeItem`'s rule about half a verification,
    applied to a probe.

    Delete this and an absent probe defaults to OK, which is the one default that must never
    be the safe-looking one."""
    rows = connector_rows(declared=["xero"], attached=["xero"], visible={"xero"})

    assert rows[0].health is None
    assert rows[0].checked_at is None

    with pytest.raises(CapabilitiesError, match="half a health reading"):
        ConnectorRow(source="xero", presence=Presence.ATTACHED, health=HealthState.OK)


# --- connectors: the overflow counts what is off the row (M39.2.1.1) -------------------------


def test_the_overflow_counts_what_is_off_the_row_and_never_what_is_out_of_reach() -> None:
    """**M39.2.1.1, and the sharpest case on this tab.** A row of icons and a count of the
    rest is correct when the rest are past the row's edge, and it is the subtraction
    disclosure the moment one of them is past the reader's reach. The two render identically.

    The discriminating case is the third: an agent naming seven sources, read by somebody who
    can see three, shows three and counts none. A strip built from the declared list rather
    than from the visible rows would show three and count four, which is a count of things
    this person may not see, printed beside them.

    **The row's width is asserted as a literal.** Comparing the row against
    `ICONS_ON_THE_ROW` and the overflow against seven minus it puts the constant on both
    sides: change it to four and every side moves together, and the test is green for every
    width the row could hold. It survived a mutation run written that way.

    Delete this and the overflow is computed from whatever list is nearest, which on a
    capabilities tab is the manifest's."""
    assert ICONS_ON_THE_ROW == 5
    seven = [f"source_{index}" for index in range(7)]

    full = connector_strip(connector_rows(declared=seven, attached=seven, visible=set(seven)))
    short = connector_strip(
        connector_rows(declared=seven[:3], attached=seven[:3], visible=set(seven[:3]))
    )
    narrowed = connector_strip(
        connector_rows(declared=seven, attached=seven, visible=set(seven[:3]))
    )

    assert (len(full.shown), full.overflow) == (5, 2)
    assert (len(short.shown), short.overflow) == (3, 0)
    assert (len(narrowed.shown), narrowed.overflow) == (3, 0)
    assert [one.source for one in narrowed.shown] == seven[:3]

    # The property that ties the two halves together, and it holds for any width, which is
    # why it is not the anchor above: what a reader sees plus what they are told is off the
    # end is exactly the number of connectors they may see, and never one more.
    assert len(full.shown) + full.overflow == 7
    assert len(narrowed.shown) + narrowed.overflow == 3


def test_an_overflow_beside_a_row_with_room_left_on_it_is_refused() -> None:
    """The shape that would make the count mean something else, refused at the constructor
    rather than left to whoever assembles a strip somewhere else in the console. A count
    beside a row that is not full is a count of things that are not merely off the end of it.

    The positive half is a full row with a genuine overflow, so this is not passing because
    every strip is refused.

    Delete this and a renderer can pair three icons with a count of four."""
    row = ConnectorRow(source="freshdesk", presence=Presence.ATTACHED)

    with pytest.raises(CapabilitiesError, match="counted as overflow beside a row"):
        ConnectorStrip(shown=(row,), overflow=4)

    with pytest.raises(CapabilitiesError, match="below zero"):
        ConnectorStrip(shown=(row,), overflow=-1)

    assert ConnectorStrip(shown=(row,) * ICONS_ON_THE_ROW, overflow=2).overflow == 2


# --- connectors: the fields projected for this agent (M39.2.1.3) -----------------------------


def test_the_fields_a_connector_projects_are_the_ones_this_run_would_return() -> None:
    """**M39.2.1.3.** A projection declares what is kept locally and answers for the
    projection, not for the reader: every name in it is a column in somebody's source system.

    Three cases in one, and the third is the one that gets written wrongly. A reach holding
    the field's capability keeps it; a reach without it drops it; and a field the policy does
    not classify is dropped whatever the reach holds, because `FieldPolicy.rule_for` returns
    `None` for the absence of a decision rather than the absence of a restriction.

    Order follows the manifest, which is the author's grouping rather than an alphabet.

    Delete this and the tab prints the manifest, and a reader who may see a client's name
    learns the source also carries a status somebody classified as confidential."""
    entity = a_projection("id", "status", "display_name", "lifecycle")

    wide = projected_for(entity, holding("read:client.name", "read:client.status"), POLICY)
    narrow = projected_for(entity, holding("read:client.name"), POLICY)
    nothing = projected_for(entity, holding("read:ticket.internal_note"), POLICY)

    assert wide == ("id", "status", "display_name")
    assert narrow == ("id", "display_name")
    assert nothing == ()
    assert "lifecycle" in entity.field_names


def test_a_row_carries_the_fields_it_was_given_and_no_count_of_the_rest() -> None:
    """The projected list reaches the row whole, so the filtering happens once and in the
    place that has the reach. A row that took the manifest and filtered on render would be a
    second filter with a different input.

    Delete this and `projects` is populated from the manifest, and the filtering becomes
    whatever the renderer does."""
    entity = a_projection("id", "status", "display_name")
    kept = projected_for(entity, holding("read:client.name"), POLICY)

    rows = connector_rows(
        declared=["laravel"],
        attached=["laravel"],
        visible={"laravel"},
        projections={"laravel": kept},
    )

    assert rows[0].projects == ("id", "display_name")


# --- skills: attach only from the approved library (M39.2.2.2) -------------------------------


def test_a_skill_is_attachable_only_once_a_named_person_has_approved_it() -> None:
    """**M39.2.2.2.** The refusal is `brain.tools.skills.pin_skill`'s, called rather than
    restated: a second opinion about a review is a second answer, and the permissive one
    wins.

    The version pinned is the approved digest and not `1.2.3`, which is the whole of the
    difference: a version is a number somebody types, and an edit without one is the
    commonest way a reviewed procedure moves.

    Delete this and an unreviewed skill can be attached, and the review becomes whatever the
    person attaching decided."""
    with pytest.raises(SkillError, match="cannot be pinned"):
        attach_skill(AGENT, a_skill(approved=False))

    approved = a_skill(approved=True)
    attachment = attach_skill(AGENT, approved)

    assert attachment.part is Part.SKILLS
    assert attachment.ref == "triage"
    assert attachment.version == approved.skill.digest()
    assert attachment.version != approved.skill.version


def test_the_attach_path_has_no_parameter_a_repository_could_arrive_through() -> None:
    """Attaching only from the approved library is a rule until somebody adds a convenience
    that takes a repository and imports on the way past. The signature is the enforcement:
    there is nowhere for a URL, an owner, a commit or a branch to arrive.

    The parameter list is pinned whole, so a name nobody thought to forbid is caught too.

    Delete this and `attach_skill(agent, url=...)` is a natural-looking convenience, and the
    review queue is a page nobody has to visit."""
    taken = inspect.signature(attach_skill).parameters

    assert list(taken) == ["agent_id", "imported"]
    assert not set(taken) & NAMES_THAT_WOULD_BE_A_REPOSITORY


def test_capabilities_gaps_reports_an_attach_path_that_takes_a_repository() -> None:
    """The check inside the diagnostic, watched, by handing it an attach path that has one.
    The healthy signature cannot produce this finding, which is why the parameter exists.

    Delete this and the signature check can be removed with the suite green, because every
    other test calls the diagnostic on a healthy module."""

    def from_a_repository(agent_id: str, repo: str, commit: str) -> None:
        return None

    gaps = capabilities_gaps(attach=from_a_repository)

    assert any("takes commit" in one for one in gaps), gaps
    assert any("takes repo" in one for one in gaps), gaps
    assert capabilities_gaps() == ()


# --- knowledge: a predicate, never a document list (M39.2.3.1) -------------------------------


def test_a_knowledge_scope_is_a_predicate_and_has_nowhere_to_put_a_document_list() -> None:
    """**M39.2.3.1.** A list of ids is correct on the afternoon it is written and stale after
    the next upload, and it moves the decision about what an agent may read out of a
    predicate a reviewer reads and into a list nobody reviews.

    Delete this and `KnowledgeScope` grows an `items` field to pin a few documents, and the
    predicate becomes decoration."""
    assert {one.name for one in dataclass_fields(KnowledgeScope)} == {"agent_id", "predicate"}

    scope = KnowledgeScope(agent_id=AGENT, predicate=Scope.department("web"))

    assert scope.predicate.clauses[0].field == "department"


def test_capabilities_gaps_reports_a_scope_type_that_could_hold_a_list() -> None:
    """The check watched, by handing the diagnostic a scope type with the field on it.

    Delete this and the document-list check can be deleted with the suite green."""

    @dataclass(frozen=True)
    class Listed:
        agent_id: str
        predicate: Scope
        items: tuple[str, ...]

    gaps = capabilities_gaps(scope_type=Listed)

    assert any("Listed.items" in one for one in gaps), gaps


def test_a_predicate_may_not_be_written_against_the_items_own_words() -> None:
    """A clause matching on a document's text would be a permission decided by the text of
    the thing being permitted, which is circular and unreviewable: nobody could say what the
    agent reaches without reading every document.

    The positive half is a predicate on the fields an item's row does carry, so this is not
    passing because every predicate is refused.

    Delete this and a scope can be written as "anything whose title contains hosting", and
    the answer to what this agent reads becomes a search."""
    with pytest.raises(CapabilitiesError, match="the fields an item's row carries"):
        KnowledgeScope(
            agent_id=AGENT,
            predicate=Scope(clauses=(Clause(field="title", op=Op.EQ, value="hosting"),)),
        )

    for field_name in PREDICATE_FIELDS:
        allowed = KnowledgeScope(
            agent_id=AGENT,
            predicate=Scope(clauses=(Clause(field=field_name, op=Op.EQ, value="x"),)),
        )

        assert allowed.predicate.clauses[0].field == field_name


def test_capabilities_gaps_reports_a_predicate_field_list_that_reads_the_document() -> None:
    """The check watched, by handing the diagnostic a field list that includes the content.

    Delete this and `PREDICATE_FIELDS` can grow `content` with nothing failing, because the
    constructor would then happily accept the clause it exists to refuse."""
    gaps = capabilities_gaps(predicate_fields=("item_id", "content"))

    assert any("the item's own words" in one for one in gaps), gaps


# --- knowledge: the preview counts what this reader can see (M39.2.3.3) ----------------------


def test_the_preview_counts_the_matching_items_this_reader_can_already_see() -> None:
    """**M39.2.3.3.** How many of my own items a predicate matches attributes nothing: a
    small number means the predicate is narrow, or the corpus is small, or most of it is out
    of my reach, and those are indistinguishable. The number that must not exist is how many
    it matches that I cannot see, and there is no function here that could produce it.

    The discriminating case is the second: the same predicate over a shorter list of items
    gives a smaller number, with nothing anywhere saying the list was shorter.

    Delete this and somebody computes the preview against the whole corpus to make it useful,
    and the tab publishes how many documents exist in a department the reader is not in."""
    scope = KnowledgeScope(agent_id=AGENT, predicate=Scope.department("web"))
    mine = [an_item("i1"), an_item("i2"), an_item("i3", department="finance")]

    assert preview_count(scope, mine) == 2
    assert preview_count(scope, mine[:1]) == 1
    assert preview_count(scope, []) == 0
    assert [one.item_id for one in matching(scope, mine)] == ["i1", "i2"]


def test_a_superseded_item_is_not_in_an_agents_slice_however_the_predicate_reads() -> None:
    """An answer drawn from a replaced item is an answer that was true last quarter.
    `brain.knowledge.item.retrievable` owns which states retrieval may consider, and calling
    it rather than checking the state here means a fifth state is handled by the module that
    added it.

    Delete this and a state check written here disagrees with the knowledge layer's, and the
    two drift the day somebody adds a state."""
    scope = KnowledgeScope(agent_id=AGENT, predicate=Scope.department("web"))
    items = [an_item("live"), an_item("old", state=KnowledgeState.SUPERSEDED)]

    assert [one.item_id for one in matching(scope, items)] == ["live"]
    assert preview_count(scope, items) == 1


def test_an_items_row_carries_what_it_is_and_never_what_it_says() -> None:
    """The row a predicate is tested against, built here rather than by the caller: a caller
    assembling its own could add a field and widen a predicate by supplying something for it
    to match on.

    Delete this and the row grows a `content` key to support one useful predicate, and every
    scope in the system can then be written against document text."""
    row = item_row(an_item("i1"))

    assert set(row) == set(PREDICATE_FIELDS)
    assert row["owner_id"] == READER
    assert row["department"] == "web"
    assert "content" not in row


# --- channels: the capability intersected with the ceiling (M39.2.4.2) -----------------------


def test_a_channel_is_offered_only_where_this_run_could_carry_what_it_reaches() -> None:
    """**M39.2.4.2.** The intersection asked for is between what the channel can carry and
    what the run can reach, and it is asked of the channel's own `may_carry` rather than by
    comparing ranks here: a second comparison is a second answer to the question
    `brain.channels.adapter.assert_can_send` already answers at send time.

    Both directions are asserted. A reach that can touch a restricted field is offered only
    the channel that carries one; the same channels offered to a reach that can touch nothing
    sensitive include the one that cannot.

    Delete this and every channel is offered to everybody, and the refusal arrives at send
    time as the feature appearing broken."""
    channels = [
        a_channel(Channel.LARK, Classification.RESTRICTED),
        a_channel(Channel.WHATSAPP, Classification.INTERNAL),
    ]

    sensitive = offered_channels(holding("read:client.contract_value"), channels, POLICY)
    ordinary = offered_channels(holding("read:client.name"), channels, POLICY)

    assert sensitive == (Channel.LARK,)
    assert ordinary == (Channel.LARK, Channel.WHATSAPP)


def test_an_agent_whose_ceiling_narrows_the_caller_widens_what_it_may_be_reached_on() -> None:
    """The E_run half, and the reason the offer is computed at the caller's reach rather than
    at the agent's ceiling. A caller who can read a restricted field, running through an
    agent whose ceiling does not admit it, has a run that cannot carry it, so a channel that
    could not carry the caller's own reach can carry this one.

    That is the correct answer and the one a ceiling-based offer gets wrong: it would show
    this person a channel their run would be refused on, or hide one it would not.

    Delete this and the offer is computed from whichever entitlement set is nearest, and the
    tab starts describing the ceiling instead of the reader."""
    caller = holding("read:client.name", "read:client.contract_value")
    channels = [a_channel(Channel.WHATSAPP, Classification.INTERNAL)]

    assert offered_channels(caller, channels, POLICY) == ()

    through_a_narrow_agent = run_reach(caller, a_record("read:client.name"))

    assert offered_channels(through_a_narrow_agent, channels, POLICY) == (Channel.WHATSAPP,)


def test_the_highest_classification_is_read_off_the_policy_and_not_off_a_list_here() -> None:
    """A reach that holds nothing returns the floor, which is the honest answer: a run that
    can read nothing can disclose nothing. Returning the most sensitive class by default
    would refuse every channel to somebody with no grants at all, which reads as the system
    being broken rather than as them holding nothing.

    Each of the three reachable classifications is asserted, so a comparison written with the
    wrong direction fails rather than being right for the case somebody happened to try.

    **The last assertion is the one that makes it a maximum rather than a last-one-wins.**
    The reach holds the restricted field and the confidential one, and the confidential rule
    sits after the restricted one in the policy, so a version that simply took every
    reachable rule in turn answers confidential. It survived a mutation run without this
    line, and a run that could carry a restricted field would have been offered a channel
    that may not.

    Delete this and the ceiling is computed from a list of classifications written here, and
    a field reclassified in the policy changes nothing on this tab."""
    assert highest_classification(holding(), POLICY) is Classification.PUBLIC
    assert highest_classification(holding("read:client.name"), POLICY) is Classification.INTERNAL
    assert (
        highest_classification(holding("read:ticket.internal_note"), POLICY)
        is Classification.CONFIDENTIAL
    )
    assert (
        highest_classification(holding("read:client.name", "read:client.contract_value"), POLICY)
        is Classification.RESTRICTED
    )
    order = [(one.entity, one.field) for one in POLICY.rules]

    assert order.index(("client", "contract_value")) < order.index(("ticket", "internal_note"))
    assert (
        highest_classification(
            holding("read:client.contract_value", "read:ticket.internal_note"), POLICY
        )
        is Classification.RESTRICTED
    )


# --- nothing on this tab counts what it withheld ---------------------------------------------


def test_no_type_on_this_tab_can_say_how_much_it_left_out() -> None:
    """The rule asked of the shapes rather than of whoever edits them next, through
    `brain.ops.jobs.hidden_count_fields` rather than a second list of the same names.

    The negative half proves the check is watching, because the healthy surface reports
    nothing and a check that reported nothing on a broken one would look identical.

    Delete this and `ConnectorStrip` grows a `hidden` beside its `overflow`, which is the
    same number the whole module is arranged to refuse."""
    assert capabilities_gaps(surface=CAPABILITIES_SURFACE) == ()

    @dataclass(frozen=True)
    class Helpful:
        shown: tuple[str, ...]
        hidden: int

    gaps = capabilities_gaps(surface=(Helpful,))

    assert any("Helpful.hidden" in one for one in gaps), gaps
