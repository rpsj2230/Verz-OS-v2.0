"""The controls on an agent's capabilities tab, held to the rules that bind the wrong thing.

Every leaf here is a place where a read rule and a write rule meet, so every test builds both
sides out of real modules: real `EntitlementSet`s and a real `AgentRecord` so a reach is the
platform's own, a real `FieldPolicy` so a channel offer is decided by the classification the
redactor would apply, real `ImportedSkill`s so an approval is `pin_skill`'s rather than a
boolean invented here, and the adapters' own declared feature sets so a rendering profile is
computed from what a surface actually says it can do.

Two of these tests exist because a fixture is the usual way this goes wrong. The staleness
case attaches under a grant and then reads at a reach that differs in that one grant and
nothing else, and the run-reach case gives one caller two agents whose ceilings differ in one
capability, because a fixture where the caller and the ceiling change together cannot tell
which of them was read.

Task ids: M39.1.1.3, M39.2.1.2, M39.2.2.1, M39.2.2.3, M39.2.2.4, M39.2.2.5
Task ids: M39.2.3.2, M39.2.3.4, M39.2.3.5, M39.2.4.1, M39.2.4.3, M39.2.4.4
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from dataclasses import fields as dataclass_fields
from datetime import UTC, datetime, timedelta

import pytest

from brain.agents.model import AgentAudience, AgentAuthority, AgentRecord
from brain.audit.ledger import AuditAction, AuditChain
from brain.audit.record import AuditRecorder
from brain.channels.adapter import ChannelCapabilities, Feature
from brain.channels.email import EMAIL_FEATURES
from brain.channels.lark import LARK_FEATURES
from brain.channels.slack import SLACK_FEATURES
from brain.channels.teams import TEAMS_FEATURES
from brain.channels.telegram import TELEGRAM_FEATURES
from brain.channels.whatsapp import WHATSAPP_FEATURES
from brain.console import agent_tabs as tabs_module
from brain.console.agent_output import basis_over
from brain.console.agent_tabs import (
    AGENT_TAB_SURFACE,
    ITEM_ROUTES,
    REVIEW_ROUTE_PREFIX,
    ROUTING_FILLER,
    SKILL_CAPABILITY,
    SKILL_SCREEN,
    USAGE_OF_OTHERS_SCREEN,
    Addition,
    AddRoute,
    AgentTabError,
    ChannelRow,
    Composed,
    Control,
    GroupInstall,
    ItemRetrieval,
    ItemUsage,
    ItemUse,
    RenderProfile,
    Review,
    SkillChip,
    SkillInvocation,
    SkillOffer,
    SkillUsage,
    SkillUse,
    admitted,
    agent_tab_gaps,
    attach,
    channel_rows,
    chips_for,
    description_refusals,
    detach,
    enable,
    folded,
    group_installable,
    install_to_group,
    item_usage,
    offer_for,
    plan_addition,
    register_skill,
    rendering_profile,
    review_route,
    review_state,
    router_collisions,
    skill_usage,
    slice_health,
    usage_basis,
    widen,
)
from brain.console.screens import screen
from brain.console.workspace import Attachment, Basis, Composition, Part, intersections_in
from brain.console.workspace_capabilities import KnowledgeScope, matching
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.envelope import Entity, IdentityMode, SideEffect, ToolDefinition, TypedResult
from brain.core.field_policy import Classification, FieldPolicy, policy_from_rows
from brain.core.scope import Clause, Op, Scope
from brain.gate.context import Channel
from brain.knowledge.item import KnowledgeItem, KnowledgeState
from brain.knowledge.visibility import KnowledgeVisibility, Visibility
from brain.ops.jobs import hidden_count_fields
from brain.tools.registry import ToolRegistry
from brain.tools.skills import (
    ImportedSkill,
    Skill,
    SkillError,
    SkillSource,
    SkillState,
    SourceKind,
    offered_cards,
)

AGENT = "support_triage"
READER = "p_reader"
OTHER = "p_colleague"
REVIEWER = "p_reviewer"
NOW = datetime(2026, 3, 10, 9, 0, tzinfo=UTC)
SINCE = NOW - timedelta(days=30)

#: A real policy, so a channel offer is decided by the classification the redactor would use.
POLICY: FieldPolicy = policy_from_rows(
    [
        ("client", "display_name", "read:client.name", Classification.INTERNAL),
        ("client", "contract_value", "read:client.contract_value", Classification.RESTRICTED),
    ]
)


def holding(*capabilities: str, principal: str = READER) -> EntitlementSet:
    """A caller holding these capabilities company-wide."""
    return EntitlementSet(
        principal_id=principal,
        grants=tuple(
            Grant(capability=Capability(value=one), scope=Scope(clauses=())) for one in capabilities
        ),
    )


def a_record(*capabilities: str, agent_id: str = AGENT) -> AgentRecord:
    """One real agent whose ceiling admits exactly these capabilities."""
    return AgentRecord(
        agent_id=agent_id,
        display_name="Support triage",
        persona="Answers support questions in the house voice.",
        audience=AgentAudience(level=Visibility.PERSONAL, owner_id=READER),
        authority=AgentAuthority(capabilities=tuple(Capability(value=one) for one in capabilities)),
        created_by=READER,
    )


def a_recorder(chain: AuditChain | None = None) -> tuple[AuditRecorder, AuditChain]:
    """One recorder bound to one chain, so a test can read back what a call wrote.

    Built here rather than taken from `test_audit_view` because a test that shares a recorder
    with another module's fixtures shares its actor, and every assertion below about who did
    something would be about a name chosen somewhere else."""
    target = chain if chain is not None else AuditChain()
    return (
        AuditRecorder(
            target,
            actor_id="u_owner",
            ent_hash=EntitlementSet(principal_id="u_owner").ent_hash(),
            trace_id="trace-tabs",
            clock=lambda: NOW,
        ),
        target,
    )


def a_composition(*attachments: Attachment) -> Composition:
    return Composition(agent_id=AGENT, attachments=attachments)


def a_connector(ref: str = "freshdesk", version: str = "2.1.0") -> Attachment:
    return Attachment(part=Part.CONNECTORS, ref=ref, version=version)


def a_skill(
    name: str = "hosting-expiry",
    description: str = "Checks whether a client domain is close to renewal",
    *,
    version: str = "1.0.0",
    body: str = "Look up the domain, then open a ticket.",
) -> Skill:
    return Skill(name=name, description=description, version=version, body=body)


def an_upload_source(location: str = "hosting.zip") -> SkillSource:
    return SkillSource(kind=SourceKind.UPLOAD, location=location, content_digest="a" * 64)


def imported(skill: Skill | None = None) -> ImportedSkill:
    """A skill that has arrived and nobody has read yet."""
    return ImportedSkill(skill=skill or a_skill(), source=an_upload_source())


def approved(skill: Skill | None = None) -> ImportedSkill:
    """A skill a named person approved, unchanged since."""
    return imported(skill).approved_by(REVIEWER, NOW)


def an_item(
    item_id: str,
    *,
    department: str = "web",
    state: KnowledgeState = KnowledgeState.PUBLISHED,
    verified_at: datetime | None = None,
    review_by: datetime | None = None,
) -> KnowledgeItem:
    """One real knowledge item, verified only when a date is given."""
    return KnowledgeItem(
        item_id=item_id,
        content="whatever it says",
        visibility=KnowledgeVisibility.of_department(department),
        owner_id=OTHER,
        state=state,
        verified_by="p_steward" if verified_at is not None else "",
        verified_at=verified_at,
        review_by=review_by,
    )


def a_scope(*, department: str = "web", agent_id: str = AGENT) -> KnowledgeScope:
    return KnowledgeScope(
        agent_id=agent_id,
        predicate=Scope(clauses=(Clause(field="department", op=Op.EQ, value=department),)),
    )


def caps(
    channel: Channel = Channel.SLACK,
    *features: Feature,
    ceiling: Classification = Classification.INTERNAL,
) -> ChannelCapabilities:
    return ChannelCapabilities(
        channel=channel, features=frozenset(features), max_classification=ceiling
    )


# --- attaching and detaching (M39.2.1.2) -----------------------------------------------------


def test_an_attach_is_refused_unless_this_person_reaches_the_thing_they_are_binding() -> None:
    """**M39.2.1.2.** The check the leaf asks for, and its positive sibling in the same test so
    a function that refused everything could not pass.

    The two reaches differ in one grant and in nothing else, which is what makes this a test of
    the capability rather than of the fixture: a wider caller with a different principal id or
    a different scope would leave two explanations for the same pass.

    Delete this and attaching becomes a way of binding a source to an agent that the person
    binding it could not name, and `connector_rows`'s visible filter is the only thing keeping
    it off the page."""
    needs = {"freshdesk": Capability(value="read:ticket.status")}
    recorder, _ = a_recorder()
    bound = attach(
        a_composition(),
        a_connector(),
        by=holding("read:ticket.status"),
        requires=needs,
        recorder=recorder,
        reason_code="requested_by_owner",
    ).composition

    assert bound.attached_to(Part.CONNECTORS) == (a_connector(),)

    with pytest.raises(AgentTabError, match="freshdesk"):
        attach(
            a_composition(),
            a_connector(),
            by=holding(),
            requires=needs,
            recorder=a_recorder()[0],
            reason_code="requested_by_owner",
        )


def test_a_thing_that_does_not_exist_and_one_out_of_reach_are_one_refusal() -> None:
    """DENIED and ABSENT at the attach control. A caller supplies a reference; if an unknown
    one said "no such connector" and an ungranted one said "you may not", the attach control
    would be a way of asking which connectors are installed on this deployment.

    Asserted on the messages being equal rather than on both raising, because both raising is
    satisfied by two refusals that read completely differently.

    Delete this and the two messages drift apart the next time somebody improves one of
    them."""
    with pytest.raises(AgentTabError) as unknown:
        attach(
            a_composition(),
            a_connector(),
            by=holding("read:ticket.status"),
            requires={},
            recorder=a_recorder()[0],
            reason_code="requested_by_owner",
        )
    with pytest.raises(AgentTabError) as unreachable:
        attach(
            a_composition(),
            a_connector(),
            by=holding(),
            requires={"freshdesk": Capability(value="read:ticket.status")},
            recorder=a_recorder()[0],
            reason_code="requested_by_owner",
        )

    assert str(unknown.value) == str(unreachable.value)
    assert "read:ticket.status" not in str(unknown.value)


def test_a_detach_asks_for_nothing_and_a_second_one_is_refused() -> None:
    """**M39.2.1.2**, the half that is deliberately unguarded. Requiring a capability to remove
    an attachment means an attachment nobody can remove on the day the grant behind it lapses,
    which is the failure arriving exactly when somebody is trying to make it stop.

    The second detach is refused because a no-op that reads as an action puts a removal in a
    ledger that M39.1.1.3 says records every add and remove.

    Delete this and somebody adds a capability parameter to `detach` because it looks
    symmetrical, and the symmetry is the bug."""
    bound = a_composition(a_connector())

    left = detach(
        bound,
        Part.CONNECTORS,
        "freshdesk",
        recorder=a_recorder()[0],
        reason_code="grant_lapsed",
    ).composition

    assert left.attachments == ()
    with pytest.raises(AgentTabError, match="not attached"):
        detach(
            left,
            Part.CONNECTORS,
            "freshdesk",
            recorder=a_recorder()[0],
            reason_code="grant_lapsed",
        )


def test_a_detach_names_a_part_as_well_as_a_reference() -> None:
    """One name can be attached to two parts: a connector and a skill may both be called
    `freshdesk`, and `Composition` allows it because its uniqueness is per part and reference.
    A detach matching on the reference alone would remove both.

    Delete this and removing a skill quietly removes the connector it was named after."""
    bound = a_composition(
        a_connector("freshdesk"),
        Attachment(part=Part.SKILLS, ref="freshdesk", version="b" * 64),
    )

    left = detach(
        bound,
        Part.SKILLS,
        "freshdesk",
        recorder=a_recorder()[0],
        reason_code="grant_lapsed",
    ).composition

    assert left.attachments == (a_connector("freshdesk"),)


def test_an_attachment_outlives_the_capability_and_the_read_path_asks_again() -> None:
    """**The staleness question M39.2.1.2 raises by saying "at attach time".**

    An attachment made under a grant stays on the composition after the grant goes, and that is
    safe for runs, because every run recomputes `E(caller) intersect agent_ceiling` and never
    sees the lost capability. It is not safe for disclosure, because the composition keeps
    rendering the row, so the read path re-asks the same question through `admitted`.

    The two reaches differ in exactly the one grant, and the composition is the same object in
    both branches, so nothing but the capability can explain the difference.

    Delete this and `admitted` gets simplified into "return the attachments", which is true on
    the day it is written and wrong the first time a grant lapses."""
    needs = {"freshdesk": Capability(value="read:ticket.status")}
    recorder, _ = a_recorder()
    bound = attach(
        a_composition(),
        a_connector(),
        by=holding("read:ticket.status"),
        requires=needs,
        recorder=recorder,
        reason_code="requested_by_owner",
    ).composition

    assert admitted(bound.attachments, by=holding("read:ticket.status"), requires=needs) == (
        a_connector(),
    )
    assert admitted(bound.attachments, by=holding(), requires=needs) == ()
    assert bound.attachments == (a_connector(),)


def test_admitted_reports_what_survived_and_never_how_much_did_not() -> None:
    """A filter and not a report. `brain.knowledge.item.retrievable` is the shape, and the
    reason is that the difference between the two numbers is the thing a reader may not learn
    by subtraction.

    Asserted on the returned type rather than on today's contents, because a second value
    carrying a count would still pass a test that only read the first one.

    Delete this and a caller adds `(kept, dropped)` because it is convenient for a banner."""
    returns = str(inspect.signature(admitted).return_annotation)

    assert returns == "tuple[Attachment, ...]"


# --- skill chips (M39.2.2.1) -----------------------------------------------------------------


def test_a_chip_carries_the_version_the_source_and_the_review_state() -> None:
    """**M39.2.2.1**, read as three facts about one skill. The source is carried as the kind
    and the location together, because "an upload" and "an upload called hosting.zip" answer
    different questions for a person deciding whether this is the skill they meant.

    Delete this and a chip loses the source, and two skills with the same name from two places
    become one row nobody can tell apart."""
    chip = chips_for([approved()])[0]

    assert chip == SkillChip(
        name="hosting-expiry",
        version="1.0.0",
        source=SourceKind.UPLOAD,
        location="hosting.zip",
        review=Review.APPROVED,
        digest=approved().skill.digest(),
    )


def test_a_skill_edited_after_approval_reads_as_changed_and_never_as_approved() -> None:
    """**The one a chip loses if the review state is copied off the state column.**
    `ImportedSkill.is_executable` is approved, by somebody named, *and unchanged since*, and a
    row edited in place still says APPROVED while its digest no longer matches.

    Built by editing the stored skill rather than by calling `with_content`, because
    `with_content` clears the review and would test the path that already works. This is the
    path where the row and the bytes disagree.

    Delete this and a chip reads approved for a procedure nobody has read, which is worse than
    no chip at all."""
    was = approved()
    edited = was.model_copy(update={"skill": a_skill(body="Look up the domain, then email.")})

    assert edited.state is SkillState.APPROVED
    assert not edited.is_executable()
    assert review_state(edited) is Review.CHANGED
    assert review_state(was) is Review.APPROVED


def test_every_state_a_skill_can_be_in_produces_a_review_state() -> None:
    """`SkillState` is closed and `Review` has to cover it, or a chip renders nothing for a
    state somebody added.

    Delete this and a fourth skill state arrives with no chip behind it, which reads on the tab
    as a skill that is not there."""
    seen = {
        review_state(imported()),
        review_state(approved()),
        review_state(imported().rejected_by(REVIEWER, NOW)),
    }

    assert seen == {Review.PENDING, Review.APPROVED, Review.REJECTED}
    assert {one.value for one in SkillState} == {"imported", "approved", "rejected"}


def test_chips_show_the_unapproved_where_the_model_is_shown_nothing() -> None:
    """The difference between this surface and `brain.tools.skills.offered_cards`, asserted
    against that function rather than described: it answers what a model may be shown and
    withholds an unapproved skill, because a card teaches the model the procedure exists. A
    person configuring the agent has to see the rejected one or the same skill is imported
    again next month.

    Delete this and somebody makes the two consistent, and the queue stops being visible from
    the place the skill would be attached."""
    library = [approved(), imported(a_skill("domain-audit", "Reviews every domain we hold"))]

    assert [one.name for one in chips_for(library)] == ["domain-audit", "hosting-expiry"]
    assert [one.name for one in offered_cards(library)] == ["hosting-expiry"]


# --- the route to the queue (M39.2.2.3) ------------------------------------------------------


def test_an_unapproved_skill_is_never_offered_an_attach_control() -> None:
    """**M39.2.2.3, and the whole leaf is in the word never.** Asserted over every state that
    is not executable, for a reader holding every capability this deployment has a screen for,
    because the failure this prevents is an attach button that appears for somebody senior
    enough.

    Delete this and the review becomes advisory: the button is the one people press."""
    everything = holding(
        SKILL_CAPABILITY.value,
        "read:console.configuration",
        "read:console.content",
        "read:console.existence",
    )
    was = approved()
    edited = was.model_copy(update={"skill": a_skill(body="Something else entirely.")})

    for one in (imported(), imported().rejected_by(REVIEWER, NOW), edited):
        assert offer_for(one, everything).control is not Control.ATTACH


def test_an_approved_skill_is_offered_the_attach_control() -> None:
    """The positive sibling of the test above, without which a function returning REVIEW for
    everything would pass it.

    The reader here holds nothing at all, which is the point: whether a skill may be attached
    is a fact about the review, and the capability check happens in `attach`.

    Delete this and the offer degrades to "never attach", which is safe and useless."""
    offer = offer_for(approved(), holding())

    assert offer.control is Control.ATTACH
    assert offer.route == ""


def test_an_unapproved_skill_routes_to_the_queue_only_where_the_queue_opens() -> None:
    """**M39.2.2.3.** The route is offered where the review screen is, asked of that screen's
    own read rather than of a capability spelled again here, and withheld otherwise: a link
    somebody bounces off is a worse answer than no link.

    The two reaches differ in the skills grant and in nothing else.

    Delete this and either the route disappears for everybody, or it is handed to readers who
    cannot follow it."""
    may_open = holding(SKILL_CAPABILITY.value, "read:console.configuration")
    may_not = holding("read:console.configuration")

    assert offer_for(imported(), may_open).control is Control.REVIEW
    assert offer_for(imported(), may_open).route == "/skills/review/hosting-expiry"
    assert offer_for(imported(), may_not).control is Control.NOTHING
    assert offer_for(imported(), may_not).route == ""


def test_the_review_route_is_the_screens_own_key_and_the_capability_is_the_screens_own() -> None:
    """Both pinned against the registry and against the literal, so a mutation to either
    constant fails here rather than producing a route to a screen that does not exist.

    Delete this and `SKILL_SCREEN` can be repointed at another screen, which silently changes
    which grant decides whether the queue is offered."""
    assert SKILL_SCREEN == "skills"
    assert screen("skills").read.requires == SKILL_CAPABILITY
    assert SKILL_CAPABILITY.value == "read:skill"
    assert REVIEW_ROUTE_PREFIX == "/skills/review/"
    assert review_route("domain-audit") == "/skills/review/domain-audit"

    with pytest.raises(AgentTabError, match="no skill"):
        review_route("  ")


def test_an_offer_cannot_carry_a_route_and_an_attach_at_once() -> None:
    """The pairing the leaf exists to prevent, refused by the type rather than by whoever
    assembles one. Both directions, because a check written one way round accepts the other.

    Delete this and a renderer builds an offer with both, and the attach button is next to the
    link that was supposed to replace it."""
    chip = chips_for([approved()])[0]

    with pytest.raises(AgentTabError, match="review control"):
        SkillOffer(chip=chip, control=Control.ATTACH, route="/skills/review/hosting-expiry")
    with pytest.raises(AgentTabError, match="review control"):
        SkillOffer(chip=chip, control=Control.REVIEW, route="")


# --- the description convention (M39.2.2.5) --------------------------------------------------


def test_a_description_that_only_repeats_the_name_gives_the_router_nothing() -> None:
    """**M39.2.2.5.** The description is what a model chooses on, so one made of the skill's own
    name and filler leaves the choice to be made on the name alone.

    The two skills differ only in the description, and the passing one differs from the name by
    a single word, which is the boundary this rule is drawn at.

    Delete this and "Use for hosting expiry" ships as a router prompt, and which skill runs
    stops being decided by anything anybody wrote."""
    assert description_refusals(a_skill(description="Use for hosting expiry"))
    assert description_refusals(a_skill(description="the hosting expiry skill"))
    assert description_refusals(a_skill(description="Use when hosting expiry"))
    assert description_refusals(a_skill(description="Use when a hosting plan expires")) == ()


def test_the_filler_list_is_what_makes_that_rule_bite() -> None:
    """Without the filler, every description passes by contributing the word "the", and the
    rule becomes decoration. Asserted by handing the checker an empty filler set, which is what
    the parameter is for.

    Delete this and somebody empties `ROUTING_FILLER` to fix a false positive and the rule
    stops firing on anything."""
    weak = a_skill(description="Use for hosting expiry")

    assert description_refusals(weak) != ()
    assert description_refusals(weak, filler=frozenset()) == ()
    assert {"use", "when", "the"} <= ROUTING_FILLER
    assert "expires" not in ROUTING_FILLER


def test_a_description_that_spans_lines_is_truncated_at_an_unknown_point() -> None:
    """A card is one line in the list a router reads. A description with a newline in it either
    breaks that list or is cut at the newline by whoever renders it, and a prompt cut at an
    unknown point routes on half a sentence.

    Both spellings, because a file written on this machine carries the other one.

    Delete this and a pasted paragraph becomes a router prompt whose second half nothing
    reads."""
    assert description_refusals(a_skill(description="Renews a plan.\nUse when it expires."))
    assert description_refusals(a_skill(description="Renews a plan.\rUse when it expires."))
    assert description_refusals(a_skill(description="Renews a plan when it expires.")) == ()


def test_two_skills_described_identically_are_chosen_between_by_position() -> None:
    """**M39.2.2.5's real failure mode, and it is a property of a pair.** One description
    cannot be checked for this when it is parsed, which is why the convention is enforced where
    a skill joins a set rather than where one arrives.

    The folding matters: the two here differ in case and in a full stop, which is a difference
    only a machine can see.

    Delete this and two skills answer to one prompt and the model picks whichever the list held
    first."""
    left = a_skill("domain-audit", "Reviews every domain the company holds")
    right = a_skill("dns-audit", "reviews every domain the company holds.")

    found = router_collisions([left, right])

    assert len(found) == 1
    assert "dns-audit" in found[0]
    assert "domain-audit" in found[0]
    assert router_collisions([left]) == ()


def test_the_folding_is_the_tool_registrys_own_and_not_a_second_one() -> None:
    """The rule this convention is lifted from lives in
    `brain.tools.registry.ToolRegistry.validate`, and the two must fold the same way or a pair
    that collides for tools passes for skills.

    Pinned against that registry's behaviour rather than against a copy of its expression: two
    tools differing only in case and a full stop are reported there, and `folded` gives them
    one string here.

    Delete this and the two foldings drift, and the argument in the docstring stops being
    true."""
    registry = ToolRegistry()
    registry.register(_a_tool("crm.read_client", "Reads a client"), _handler)
    registry.register(_a_tool("crm.read_account", "reads a client."), _handler)

    assert len(registry.validate()) == 1
    assert folded("Reads a client") == folded("reads a client.")
    assert folded("Reads a client") != folded("Reads a company")


class ClientRow(Entity):
    """One row a tool returns, so a registration can be checked against a real shape."""


def _handler() -> TypedResult[ClientRow]:
    return TypedResult[ClientRow]()


def _a_tool(name: str, description: str) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=description,
        entity="client",
        required_capability="read:client.name",
        identity_mode=IdentityMode.DELEGATED,
        side_effect=SideEffect.NONE,
    )


def test_a_skill_whose_description_cannot_route_does_not_reach_the_agent() -> None:
    """**The enforcement point.** The convention is worth nothing where it is only rendered, so
    it is checked where the skill joins the router's menu.

    The two skills differ only in their description, and both are approved by the same named
    reviewer, so the approval cannot explain the difference.

    Delete this and `description_refusals` becomes a function nothing calls."""
    good = approved(a_skill(description="Use when a hosting plan is close to renewal"))
    weak = approved(a_skill(description="Use for hosting expiry"))

    bound = register_skill(
        a_composition(),
        good,
        alongside=[],
        by=holding(SKILL_CAPABILITY.value),
        recorder=a_recorder()[0],
        reason_code="requested_by_owner",
    ).composition

    assert bound.attached_to(Part.SKILLS)[0].ref == "hosting-expiry"
    with pytest.raises(AgentTabError, match="adds no word"):
        register_skill(
            a_composition(),
            weak,
            alongside=[],
            by=holding(SKILL_CAPABILITY.value),
            recorder=a_recorder()[0],
            reason_code="requested_by_owner",
        )


def test_a_skill_collides_only_with_the_ones_on_the_same_agent() -> None:
    """The router reads one agent's cards, so a collision with a skill some other agent holds
    is not a collision anybody experiences, and refusing it would make an approved library
    unusable across a company.

    Delete this and either the check is global, which refuses correct configurations, or it
    checks nothing, which is the state before this module existed."""
    joining = approved(a_skill("dns-audit", "Reviews every domain the company holds"))
    twin = a_skill("domain-audit", "reviews every domain the company holds.")
    unrelated = a_skill("timesheets", "Files the weekly timesheets on a Friday")

    bound = register_skill(
        a_composition(),
        joining,
        alongside=[unrelated],
        by=holding(SKILL_CAPABILITY.value),
        recorder=a_recorder()[0],
        reason_code="requested_by_owner",
    ).composition

    assert bound.attached_to(Part.SKILLS)[0].ref == "dns-audit"
    with pytest.raises(AgentTabError, match="position rather than by meaning"):
        register_skill(
            a_composition(),
            joining,
            alongside=[twin],
            by=holding(SKILL_CAPABILITY.value),
            recorder=a_recorder()[0],
            reason_code="requested_by_owner",
        )


def test_registering_a_skill_still_needs_the_approval_and_pins_the_digest() -> None:
    """The convention is an extra refusal and never a replacement for the review.
    `brain.tools.skills.pin_skill` refuses an unapproved skill and its error is allowed
    through, because restating it here would be a second opinion about a review.

    The pin is the digest and not the version string, which is what makes an edit without a
    version bump visible.

    Delete this and a skill with an excellent description is attached without anybody having
    read it."""
    one = approved(a_skill(description="Use when a hosting plan is close to renewal"))

    bound = register_skill(
        a_composition(),
        one,
        alongside=[],
        by=holding(SKILL_CAPABILITY.value),
        recorder=a_recorder()[0],
        reason_code="requested_by_owner",
    ).composition

    assert bound.attached_to(Part.SKILLS)[0].version == one.skill.digest()
    assert bound.attached_to(Part.SKILLS)[0].version != one.skill.version
    with pytest.raises(SkillError, match="cannot be pinned"):
        register_skill(
            a_composition(),
            imported(a_skill(description="Use when a hosting plan is close to renewal")),
            alongside=[],
            by=holding(SKILL_CAPABILITY.value),
            recorder=a_recorder()[0],
            reason_code="requested_by_owner",
        )


def test_registering_a_skill_runs_the_attach_time_capability_check() -> None:
    """`register_skill` goes through `attach`, so there is one capability check on this tab
    rather than two that can disagree.

    The two reaches differ in the skills grant alone.

    Delete this and the skill path grows its own check, and the day the two disagree the
    permissive one wins."""
    one = approved(a_skill(description="Use when a hosting plan is close to renewal"))

    assert register_skill(
        a_composition(),
        one,
        alongside=[],
        by=holding(SKILL_CAPABILITY.value),
        recorder=a_recorder()[0],
        reason_code="requested_by_owner",
    ).composition.attachments
    with pytest.raises(AgentTabError, match="hosting-expiry"):
        register_skill(
            a_composition(),
            one,
            alongside=[],
            by=holding(),
            recorder=a_recorder()[0],
            reason_code="requested_by_owner",
        )


# --- invocation counts (M39.2.2.4) -----------------------------------------------------------


def an_invocation(
    skill_name: str, *, principal: str = READER, at: datetime = NOW, agent: str = AGENT
) -> SkillInvocation:
    return SkillInvocation(agent_id=agent, skill_name=skill_name, principal_id=principal, at=at)


def test_the_used_and_unused_halves_partition_the_attached_skills() -> None:
    """**M39.2.2.4.** The pruning list is only meaningful as the complement of the used one, so
    both come out of one call: two calls over two different sets produce two lists that do not
    add up, and somebody prunes a skill that was in neither.

    Delete this and the unused list quietly becomes "skills with no invocations anywhere",
    which includes ones this agent never had."""
    usage = skill_usage(
        AGENT,
        [an_invocation("hosting-expiry"), an_invocation("hosting-expiry"), an_invocation("dns")],
        attached=["hosting-expiry", "dns", "timesheets"],
        caller_id=READER,
        basis=Basis.EVERYONE,
        since=SINCE,
        until=NOW,
    )

    assert usage.used == (
        SkillUse(skill_name="hosting-expiry", invocations=2),
        SkillUse(skill_name="dns", invocations=1),
    )
    assert usage.unused == ("timesheets",)
    assert {one.skill_name for one in usage.used} | set(usage.unused) == {
        "hosting-expiry",
        "dns",
        "timesheets",
    }


def test_an_invocation_of_something_this_agent_does_not_carry_reaches_no_figure() -> None:
    """A row for a detached skill would be a row about a configuration the reader is not
    looking at, and the count beside it would be the only place it appeared.

    The same invocation list twice, differing only in what is attached.

    Delete this and detaching a skill leaves its counts on the tab for ever."""
    calls = [an_invocation("hosting-expiry"), an_invocation("removed-last-week")]

    kept = skill_usage(
        AGENT,
        calls,
        attached=["hosting-expiry"],
        caller_id=READER,
        basis=Basis.EVERYONE,
        since=SINCE,
        until=NOW,
    )

    assert kept.used == (SkillUse(skill_name="hosting-expiry", invocations=1),)
    assert kept.unused == ()


def test_an_invocation_of_another_agent_is_not_counted_here() -> None:
    """The tab is one agent's, and a skill attached to two agents accumulates counts on both.
    Counting the other agent's runs would make a shared skill look busy on the agent that never
    used it, which is the opposite of what the pruning list is for.

    The two invocations differ in the agent id alone.

    Delete this and every agent sharing a skill shows the same figure."""
    usage = skill_usage(
        AGENT,
        [an_invocation("hosting-expiry"), an_invocation("hosting-expiry", agent="other_agent")],
        attached=["hosting-expiry"],
        caller_id=READER,
        basis=Basis.EVERYONE,
        since=SINCE,
        until=NOW,
    )

    assert usage.used == (SkillUse(skill_name="hosting-expiry", invocations=1),)


def test_the_window_and_the_basis_are_both_applied_to_an_invocation() -> None:
    """The two filters that make a count somebody else's afternoon or the reader's own, each
    tested with one thing changed: an invocation before the window, and one by a colleague.

    On the narrower basis a skill somebody else used every day reads as unused, which is
    correct and is why `SkillUsage` carries the basis.

    Delete this and either the window is ignored, so a pruning list never empties, or the basis
    is, so a reader is shown their colleagues' activity."""
    calls = [
        an_invocation("hosting-expiry", at=SINCE - timedelta(days=1)),
        an_invocation("hosting-expiry", principal=OTHER),
    ]

    everyone = skill_usage(
        AGENT,
        calls,
        attached=["hosting-expiry"],
        caller_id=READER,
        basis=Basis.EVERYONE,
        since=SINCE,
        until=NOW,
    )
    own = skill_usage(
        AGENT,
        calls,
        attached=["hosting-expiry"],
        caller_id=READER,
        basis=Basis.OWN,
        since=SINCE,
        until=NOW,
    )

    assert everyone.used == (SkillUse(skill_name="hosting-expiry", invocations=1),)
    assert own.used == ()
    assert own.unused == ("hosting-expiry",)


def test_the_basis_on_this_tab_is_the_usage_screens_and_not_the_budgets() -> None:
    """`brain.console.agent_output.basis_over` with one screen key, and the key is the thing
    under test: an invocation count is a usage figure, so a reader sees everybody's exactly
    when they could open the usage screen and read them there.

    The third reach holds the budget grant and the plane and not the usage grant, which is the
    case that separates this screen from the one `brain.console.workspace.basis_for` uses.

    Delete this and the tab can be repointed at another screen's grant, which is a figure
    reachable from a place no administrator reviewing that screen would look."""
    assert USAGE_OF_OTHERS_SCREEN == "usage"
    for reach in (
        holding(),
        holding("read:usage"),
        holding("read:usage", "read:console.configuration"),
        holding("read:budget", "read:console.configuration"),
    ):
        assert usage_basis(reach) is basis_over("usage", reach)
    assert usage_basis(holding("read:usage", "read:console.configuration")) is Basis.EVERYONE
    assert usage_basis(holding("read:budget", "read:console.configuration")) is Basis.OWN


# --- adding to knowledge (M39.2.3.2) ---------------------------------------------------------


def test_an_item_added_by_upload_is_reached_only_if_the_predicate_matches() -> None:
    """**M39.2.3.2**, and the trap in it. Adding an item to an agent's knowledge tab does not
    make the agent draw on it: the predicate decides, and an item that does not match is added
    and never reached.

    The two items differ in the department alone.

    Delete this and the bug is somebody uploading a document, the agent still saying it does
    not know, and nothing anywhere saying the predicate did not match."""
    inside = plan_addition(a_scope(), an_item("k1"), AddRoute.UPLOAD)
    outside = plan_addition(a_scope(), an_item("k2", department="finance"), AddRoute.UPLOAD)

    assert inside == Addition(route=AddRoute.UPLOAD, item_id="k1", reached=True)
    assert outside == Addition(route=AddRoute.UPLOAD, item_id="k2", reached=False)


def test_a_link_takes_the_same_route_as_an_upload_and_a_predicate_takes_neither() -> None:
    """The three routes the leaf names, and the difference between them: two add an item and
    the third adds none, so asking for an addition by widening is refused rather than answered
    with an item id nothing produced.

    Delete this and `AddRoute.PREDICATE` produces an `Addition` describing an item that was
    never uploaded."""
    assert plan_addition(a_scope(), an_item("k1"), AddRoute.LINK).reached
    assert {AddRoute.UPLOAD, AddRoute.LINK} == ITEM_ROUTES

    with pytest.raises(AgentTabError, match="adds no item"):
        plan_addition(a_scope(), an_item("k1"), AddRoute.PREDICATE)


def test_the_addition_path_has_no_parameter_a_url_could_arrive_through() -> None:
    """The address check belongs to `brain.knowledge.uploads.receive_link`, which reuses
    `brain.tools.fetch` whole; the part a second copy leaves out is re-running the rules on
    every redirect. A convenience here taking a URL would be that second copy.

    Asserted through the diagnostic with a function that does take one, so the check is
    exercised rather than merely satisfied by today's signature.

    Delete this and somebody adds `plan_addition(url=...)` because it saves a call."""

    def takes_a_url(url: str) -> object:
        return url

    assert any("re-checks the address" in one for one in agent_tab_gaps(addition=takes_a_url))
    assert agent_tab_gaps() == ()


def test_widening_a_predicate_reaches_more_and_never_less() -> None:
    """**M39.2.3.2's third route.** Dropping a clause widens what the agent draws on, and the
    property that makes it safe is that it cannot narrow: everything the original reached is
    still reached.

    Asserted over both items, so a `widen` that returned an unrelated scope would fail on the
    first assertion rather than passing on the second.

    Delete this and `widen` can be written as "return a new scope" and silently drop the wrong
    clause."""
    narrow = a_scope()
    items = [an_item("k1"), an_item("k2", department="finance")]

    wider = widen(narrow, drop=["department"])

    assert [one.item_id for one in matching(narrow, items)] == ["k1"]
    assert [one.item_id for one in matching(wider, items)] == ["k1", "k2"]
    assert wider.predicate.is_unrestricted()


def test_dropping_a_clause_that_is_not_there_is_refused() -> None:
    """A no-op that reads as an action, and the person who asked has been told they widened
    something. The same refusal `detach` makes.

    Delete this and a typo in a field name reads as a successful widening, and the agent
    reaches exactly what it did before."""
    with pytest.raises(AgentTabError, match="no clause on"):
        widen(a_scope(), drop=["owner_id"])


def test_a_widened_predicate_is_still_a_predicate_the_scope_type_accepts() -> None:
    """`KnowledgeScope` refuses a predicate written against the item's own words, and a widen
    that built a scope by hand could sidestep that constructor. It does not: the result goes
    through the same type.

    Delete this and widening becomes the one path a predicate can enter by without being
    checked."""
    two = KnowledgeScope(
        agent_id=AGENT,
        predicate=Scope(
            clauses=(
                Clause(field="department", op=Op.EQ, value="web"),
                Clause(field="owner_id", op=Op.EQ, value=OTHER),
            )
        ),
    )

    left = widen(two, drop=["owner_id"])

    assert isinstance(left, KnowledgeScope)
    assert [one.field for one in left.predicate.clauses] == ["department"]


# --- coverage and staleness (M39.2.3.4) ------------------------------------------------------


def test_the_three_verification_counts_sum_to_the_slice() -> None:
    """**M39.2.3.4.** Superseded and archived items are dropped by `matching` before anything
    is counted, so the three states partition the slice. If they did not, a figure would be
    missing from every reading and nothing would say which.

    Delete this and a fourth badge state arrives and the coverage figure silently stops adding
    up."""
    items = [
        an_item("k1", verified_at=NOW - timedelta(days=10), review_by=NOW + timedelta(days=10)),
        an_item("k2", verified_at=NOW - timedelta(days=40), review_by=NOW - timedelta(days=1)),
        an_item("k3"),
        an_item("k4", state=KnowledgeState.SUPERSEDED),
    ]

    health = slice_health(a_scope(), items, now=NOW)

    assert (health.matched, health.verified, health.stale, health.unverified) == (3, 1, 1, 1)
    assert health.verified + health.stale + health.unverified == health.matched


def test_an_item_is_stale_only_once_its_review_date_has_passed() -> None:
    """The staleness half, with `now` as the only thing that differs between the two readings.
    One item, one review date, two clocks: a fixture with two items would let a wrong badge
    lookup pass by picking the other one.

    Delete this and staleness is computed from something other than the review date, and every
    item reads as current."""
    due = NOW + timedelta(days=1)
    items = [an_item("k1", verified_at=NOW - timedelta(days=10), review_by=due)]

    before = slice_health(a_scope(), items, now=NOW)
    after = slice_health(a_scope(), items, now=due + timedelta(seconds=1))

    assert (before.verified, before.stale) == (1, 0)
    assert (after.verified, after.stale) == (0, 1)


def test_coverage_over_an_empty_slice_is_withheld_rather_than_nought() -> None:
    """Nought is a measurement and an empty slice is the absence of one. Rendering "0 per cent
    covered" for an agent whose predicate matches nothing this reader can see is an alarm about
    a corpus rather than about coverage, and it is the alarm nobody can act on.

    The positive half is in the same test, so a property returning None always would fail.

    Delete this and an agent with a narrow predicate reads as a knowledge base nobody has
    verified."""
    empty = slice_health(a_scope(), [], now=NOW)
    one = slice_health(
        a_scope(),
        [an_item("k1", verified_at=NOW - timedelta(days=1), review_by=NOW + timedelta(days=1))],
        now=NOW,
    )

    assert empty.matched == 0
    assert empty.coverage is None
    assert empty.staleness is None
    assert one.coverage == 1.0
    assert one.staleness == 0.0


def test_an_item_outside_this_agents_predicate_is_in_no_figure() -> None:
    """ "Exactly this agent's slice" is the leaf's own wording, and the figure has to be over
    `matching` rather than over whatever the caller handed in, or every agent in the company
    shows the same coverage.

    The two items differ in the department alone.

    Delete this and coverage becomes a fact about the corpus with an agent's name on it."""
    items = [an_item("k1"), an_item("k2", department="finance")]

    assert slice_health(a_scope(), items, now=NOW).matched == 1
    assert slice_health(a_scope(department="finance"), items, now=NOW).matched == 1


# --- what the agent reached for (M39.2.3.5) --------------------------------------------------


def a_retrieval(
    item_id: str, *, principal: str = READER, at: datetime = NOW, agent: str = AGENT
) -> ItemRetrieval:
    return ItemRetrieval(agent_id=agent, item_id=item_id, principal_id=principal, at=at)


def test_the_items_never_touched_are_the_complement_of_the_ones_retrieved() -> None:
    """**M39.2.3.5.** The never list is the pruning list and is only meaningful as the
    complement, so both halves come from one call over one set. Two calls over two sets produce
    two lists that do not add up.

    Delete this and the never list becomes every item in the corpus that this agent did not
    read, which is a different and much longer statement."""
    within = matching(a_scope(), [an_item("k1"), an_item("k2"), an_item("k3")])

    usage = item_usage(
        AGENT,
        [a_retrieval("k1"), a_retrieval("k1"), a_retrieval("k2")],
        within=within,
        caller_id=READER,
        basis=Basis.EVERYONE,
        since=SINCE,
        until=NOW,
    )

    assert usage.most_retrieved == (
        ItemUse(item_id="k1", retrievals=2),
        ItemUse(item_id="k2", retrievals=1),
    )
    assert usage.never_retrieved == ("k3",)
    assert {one.item_id for one in usage.most_retrieved} | set(usage.never_retrieved) == {
        "k1",
        "k2",
        "k3",
    }


def test_a_retrieval_of_something_outside_this_slice_reaches_no_figure() -> None:
    """The disclosure argument in one assertion. `within` is the reader's own visible slice, so
    a retrieval of anything else contributes to no number they are shown, and a count of it
    could not be recovered from what they are.

    The two retrievals differ in the item alone, and both are inside the window and on the
    wider basis.

    Delete this and a retrieval of a document this reader may not see puts a number on their
    screen."""
    within = matching(a_scope(), [an_item("k1")])

    usage = item_usage(
        AGENT,
        [a_retrieval("k1"), a_retrieval("k_finance")],
        within=within,
        caller_id=READER,
        basis=Basis.EVERYONE,
        since=SINCE,
        until=NOW,
    )

    assert usage.most_retrieved == (ItemUse(item_id="k1", retrievals=1),)
    assert usage.never_retrieved == ()


def test_a_retrieval_by_another_agent_or_outside_the_window_is_not_counted() -> None:
    """The other two filters, each with one thing changed. An agent's tab shows that agent's
    reading, and a figure over all time cannot show that an item stopped being useful.

    Delete this and the never list never empties, or it fills with items another agent read."""
    within = matching(a_scope(), [an_item("k1")])

    usage = item_usage(
        AGENT,
        [
            a_retrieval("k1", agent="other_agent"),
            a_retrieval("k1", at=SINCE - timedelta(days=1)),
        ],
        within=within,
        caller_id=READER,
        basis=Basis.EVERYONE,
        since=SINCE,
        until=NOW,
    )

    assert usage.most_retrieved == ()
    assert usage.never_retrieved == ("k1",)


def test_the_narrower_basis_counts_only_this_readers_own_retrievals() -> None:
    """The figure moves when somebody else works, so on the narrower basis it is the reader's
    own, labelled as such. A colleague's retrieval of the same item is the only difference
    between the two readings.

    Delete this and a reader who cannot open the usage screen is shown their colleagues'
    reading habits on an agent's knowledge tab."""
    within = matching(a_scope(), [an_item("k1")])
    log = [a_retrieval("k1", principal=OTHER)]

    everyone = item_usage(
        AGENT,
        log,
        within=within,
        caller_id=READER,
        basis=Basis.EVERYONE,
        since=SINCE,
        until=NOW,
    )
    own = item_usage(
        AGENT, log, within=within, caller_id=READER, basis=Basis.OWN, since=SINCE, until=NOW
    )

    assert everyone.most_retrieved == (ItemUse(item_id="k1", retrievals=1),)
    assert everyone.basis is Basis.EVERYONE
    assert own.most_retrieved == ()
    assert own.never_retrieved == ("k1",)


# --- channels (M39.2.4.1, M39.2.4.3) ---------------------------------------------------------


def test_a_row_appears_only_for_a_channel_this_run_could_carry() -> None:
    """**M39.2.4.1 standing on M39.2.4.2.** A channel this run could not carry produces no row
    rather than a disabled one, because a disabled row says the deployment has that surface and
    that this agent's widest reach is too sensitive for it, which are two facts about a ceiling
    on a row read by somebody who may not know either.

    The two records differ in one ceiling capability and the caller is the same object in both,
    which is what makes this a test of the reach rather than of the fixture.

    Delete this and a narrow surface renders as a switch nobody can turn on, and the reason is
    printed beside it."""
    caller = holding("read:client.name", "read:client.contract_value")
    surfaces = [caps(Channel.SLACK), caps(Channel.LARK, ceiling=Classification.RESTRICTED)]

    narrow = channel_rows(caller, a_record("read:client.name"), surfaces, POLICY, enabled=())
    wide = channel_rows(
        caller,
        a_record("read:client.name", "read:client.contract_value"),
        surfaces,
        POLICY,
        enabled=(),
    )

    assert [one.channel for one in narrow] == [Channel.SLACK, Channel.LARK]
    assert [one.channel for one in wide] == [Channel.LARK]


def test_a_row_says_whether_the_install_has_that_channel_switched_on() -> None:
    """**M39.2.4.1's per-channel enable.** Two rows from one call, differing only in whether the
    install lists them, so a function returning a constant would fail.

    Delete this and every offered channel renders as enabled, which is the state where nobody
    can tell what the agent actually answers on."""
    surfaces = [caps(Channel.SLACK), caps(Channel.EMAIL)]

    rows = channel_rows(
        holding("read:client.name"),
        a_record("read:client.name"),
        surfaces,
        POLICY,
        enabled=[Channel.SLACK],
    )

    assert {one.channel: one.enabled for one in rows} == {
        Channel.SLACK: True,
        Channel.EMAIL: False,
    }


def test_enabling_a_channel_with_no_row_is_refused_and_the_others_stay_on() -> None:
    """A channel with no row is every channel this run could not carry and every channel this
    deployment does not have, in one refusal, so the enable control is not a way of asking
    which adapters are configured.

    The positive half is in the same test: enabling keeps what was already on, because an
    enable that returned one channel would silently switch the others off.

    Delete this and either the switch turns on a surface nothing can deliver, or turning one on
    turns the rest off."""
    rows = channel_rows(
        holding("read:client.name"),
        a_record("read:client.name"),
        [caps(Channel.SLACK), caps(Channel.EMAIL)],
        POLICY,
        enabled=[Channel.SLACK],
    )

    assert enable(rows, Channel.EMAIL) == (Channel.EMAIL, Channel.SLACK)
    with pytest.raises(AgentTabError, match="not a channel"):
        enable(rows, Channel.WHATSAPP)


def test_the_rendering_profile_is_the_widest_layout_the_surface_declares() -> None:
    """**M39.2.4.3.** Cards before attachments, stated rather than left to whichever branch was
    written first: the two are not exclusive and `brain.channels.lark` declares both.

    Asserted against the adapters' own feature sets rather than against sets invented here, so
    a surface that changes what it declares moves this test.

    Delete this and a Lark answer renders as plain text because the branch order changed."""
    assert rendering_profile(caps(Channel.LARK, *LARK_FEATURES)) is RenderProfile.CARD
    assert rendering_profile(caps(Channel.SLACK, *SLACK_FEATURES)) is RenderProfile.ATTACHMENT
    assert rendering_profile(caps(Channel.EMAIL, *EMAIL_FEATURES)) is RenderProfile.ATTACHMENT
    assert rendering_profile(caps(Channel.TEAMS, *TEAMS_FEATURES)) is RenderProfile.PLAIN
    assert rendering_profile(caps(Channel.TELEGRAM, *TELEGRAM_FEATURES)) is RenderProfile.PLAIN
    assert rendering_profile(caps(Channel.WHATSAPP, *WHATSAPP_FEATURES)) is RenderProfile.ATTACHMENT
    assert rendering_profile(caps(Channel.LARK, Feature.CARDS)) is RenderProfile.CARD


def test_a_profile_is_chosen_from_the_adapter_and_cannot_be_asked_for() -> None:
    """ "Chosen automatically" is the leaf's own wording, and the way it stays true is that
    there is nowhere to put a choice. A configured profile is a way of declaring a capability
    the adapter does not have, and `assert_can_send` then refuses at the send rather than at
    the configuration.

    Exercised through the diagnostic with a function that does take one.

    Delete this and a profile parameter arrives as a convenience for one surface."""

    def takes_a_choice(capabilities: ChannelCapabilities, profile: str) -> object:
        return (capabilities, profile)

    assert list(inspect.signature(rendering_profile).parameters) == ["capabilities"]
    assert any("chosen by hand" in one for one in agent_tab_gaps(profile=takes_a_choice))


# --- group installation (M39.2.4.4) ----------------------------------------------------------


def test_the_feature_member_exists_and_gates_the_install() -> None:
    """**M39.2.4.4.** `brain.console.workspace_capabilities` recorded this leaf as blocked
    because `Feature` had no member for it, and objected that adding one with nothing behind it
    would be a capability an adapter declares and nothing honours. The member is here and it
    gates a refusal.

    The two capability values differ in that one feature and nothing else.

    Delete this and the member becomes a label."""
    assert Feature.GROUP_INSTALL in Feature
    assert group_installable(caps(Channel.SLACK, Feature.GROUP_INSTALL))
    assert not group_installable(caps(Channel.SLACK))


def test_no_adapter_declares_group_installation_yet() -> None:
    """The honest state, written down so it is a finding rather than a silence. None of the six
    adapters has a path for the conversation reference a vendor hands back, so the console
    offers group installation nowhere, and inventing support a channel does not have is the
    failure the member was withheld to avoid.

    This goes red the day an adapter declares it, which is the right direction: somebody then
    reads this test, checks the adapter really has the path, and removes the line.

    Delete this and the claim in the docstring is unchecked."""
    declared = (
        EMAIL_FEATURES,
        LARK_FEATURES,
        SLACK_FEATURES,
        TEAMS_FEATURES,
        TELEGRAM_FEATURES,
        WHATSAPP_FEATURES,
    )

    for features in declared:
        assert Feature.GROUP_INSTALL not in features


def test_a_group_install_needs_the_feature_and_an_enabled_channel() -> None:
    """Two refusals and the positive case, each with one thing changed: a surface that does not
    declare the feature, and a surface that does but which this agent does not answer on.

    Delete this and an agent is installed into a room on a channel it cannot speak on, which
    reads to everybody in that room as the feature being broken."""
    able = caps(Channel.SLACK, Feature.GROUP_INSTALL)
    rows = (
        ChannelRow(
            channel=Channel.SLACK,
            enabled=True,
            profile=RenderProfile.PLAIN,
            group_installable=True,
        ),
        ChannelRow(
            channel=Channel.EMAIL,
            enabled=False,
            profile=RenderProfile.PLAIN,
            group_installable=False,
        ),
    )

    assert install_to_group(AGENT, able, "C0AB", rows=rows) == GroupInstall(
        agent_id=AGENT, channel=Channel.SLACK, room_ref="C0AB"
    )
    with pytest.raises(AgentTabError, match="does not declare group installation"):
        install_to_group(AGENT, caps(Channel.SLACK), "C0AB", rows=rows)
    with pytest.raises(AgentTabError, match="not enabled"):
        install_to_group(AGENT, caps(Channel.EMAIL, Feature.GROUP_INSTALL), "C0AB", rows=rows)


def test_a_group_install_has_nowhere_to_put_a_reach() -> None:
    """**Installing an agent into a room is not a grant to the room.** Every answer there is
    computed at `brain.channels.room.floor`, recomputed for each answer because membership
    moves, and an install carrying an entitlement would be a second answer to what a room may
    see, written once and stale by the first joiner.

    Asserted on the field set and again through the diagnostic against a type that does carry
    one, so the check is exercised.

    Delete this and somebody caches the room's envelope on the install to save a lookup at send
    time."""

    @dataclass(frozen=True)
    class WithAReach:
        agent_id: str
        entitlement: str

    assert {one.name for one in dataclass_fields(GroupInstall)} == {
        "agent_id",
        "channel",
        "room_ref",
    }
    assert any(
        "would make an install a grant" in one for one in agent_tab_gaps(install_type=WithAReach)
    )

    with pytest.raises(AgentTabError, match="no agent or no conversation"):
        GroupInstall(agent_id=AGENT, channel=Channel.SLACK, room_ref="  ")


# --- the rules this surface shares with its siblings ------------------------------------------


def test_this_surface_intersects_no_entitlement_sets_of_its_own() -> None:
    """The invariant's structural half, the same check `brain.console.workspace`,
    `brain.console.workspace_capabilities` and the two agent tabs beside this one make of
    themselves. Every reach here arrives as an argument or comes from `run_reach`, which is the
    console's one call into `EntitlementSet.intersect`.

    Asserted twice: directly, and through the diagnostic against a source that does intersect,
    so the check itself is exercised rather than merely satisfied by a clean tree.

    Delete this and a helper on this tab starts narrowing a reach, and the copy that is subtly
    wrong is the one deciding what an agent is bound to."""
    intersecting = "def f(a, b):\n    return a.intersect(b)\n"

    assert intersections_in(inspect.getsource(tabs_module)) == ()
    assert any(
        "intersects two entitlement sets" in one for one in agent_tab_gaps(source=intersecting)
    )


def test_no_type_on_this_tab_can_say_how_much_was_left_out() -> None:
    """`brain.ops.jobs.hidden_count_fields` over the declared surface, and the surface is
    declared rather than discovered so that a type added to the tab and not to the tuple is a
    type the check never sees.

    Exercised against a type that does carry one, because a scan over a clean tree reports
    nothing whatever the rule says.

    Delete this and a summary grows a `total` because it makes a percentage renderable."""

    @dataclass(frozen=True)
    class WithATotal:
        agent_id: str
        total: int

    assert hidden_count_fields(AGENT_TAB_SURFACE) == ()
    assert hidden_count_fields([WithATotal]) == ("WithATotal.total",)
    assert any("not shown" in one for one in agent_tab_gaps(surface=[WithATotal]))


def test_the_detach_path_takes_nothing_that_could_guard_it() -> None:
    """The asymmetry stated as a check rather than as a paragraph. A capability parameter on
    `detach` is the edit that looks like tidying up and produces an attachment nobody can
    remove during the incident that needs it removed.

    Delete this and `detach(by=...)` arrives because `attach` has one."""

    def guarded(composition: Composition, part: Part, ref: str, *, by: object) -> object:
        return (composition, part, ref, by)

    assert not {"by", "entitlement", "reach", "requires"} & set(
        inspect.signature(detach).parameters
    )
    assert any("nobody can remove" in one for one in agent_tab_gaps(removal=guarded))


def test_the_diagnostic_is_silent_on_the_real_module() -> None:
    """The deployment check. Every other assertion above hands the diagnostic a broken input to
    prove the finding fires; this is the half that says the module itself is clean, and it is
    the one that goes red when somebody adds a field or a parameter this file argues against.

    Delete this and the diagnostic can be right about constructed inputs while the module it
    was written for has drifted."""
    assert agent_tab_gaps() == ()


def test_the_types_a_reader_is_handed_are_all_on_the_declared_surface() -> None:
    """`AGENT_TAB_SURFACE` is what the checks above run over, so a type missing from it is a
    type nothing checks. Asserted against the types the public functions actually return.

    Delete this and a new summary type is added to the tab and to nothing else."""
    returned = {
        SkillChip,
        SkillOffer,
        SkillUsage,
        Addition,
        ItemUsage,
        ChannelRow,
        GroupInstall,
    }

    assert returned <= set(AGENT_TAB_SURFACE)


# --- every add and remove reaches the ledger (M39.1.1.3) --------------------------------------


def test_an_attach_and_a_detach_each_reach_the_ledger_with_who_when_why_and_which_way() -> None:
    """**M39.1.1.3 asks for who, when and why, and the direction is the fourth thing it needs
    without saying so.** An entry that records a composition change without saying whether the
    thing arrived or left answers "was this agent ever able to do that" and not "can it now",
    and the second is the question somebody asks during an incident.

    Who is the recorder's actor, bound once so a call site cannot get it wrong. When is the
    entry's. Why is the reason code. All four are read back off the entry rather than off the
    arguments, because an argument that never reached the entry would satisfy a check on the
    input.

    Both calls write to one chain and the chain still verifies, so the two entries are a
    sequence rather than two unrelated rows.

    Delete this and the tab can bind and unbind things with nothing recorded, which is a
    change to what an agent can do that nobody can date."""
    recorder, chain = a_recorder()
    needs = {"freshdesk": Capability(value="read:ticket.status")}

    bound = attach(
        a_composition(),
        a_connector(),
        by=holding("read:ticket.status"),
        requires=needs,
        recorder=recorder,
        reason_code="requested_by_owner",
    )
    freed = detach(
        bound.composition,
        Part.CONNECTORS,
        "freshdesk",
        recorder=recorder,
        reason_code="grant_lapsed",
    )

    assert bound.entry.action is AuditAction.COMPOSE_CHANGE
    assert bound.entry.subject == f"agent:{a_composition().agent_id}"
    assert bound.entry.actor_id == "u_owner"
    assert bound.entry.details["reference"] == "freshdesk"
    assert bound.entry.details["direction"] == "attached"
    assert bound.entry.details["reason_code"] == "requested_by_owner"

    assert freed.entry.details["direction"] == "detached"
    assert freed.entry.details["reason_code"] == "grant_lapsed"
    assert freed.composition.attached_to(Part.CONNECTORS) == ()

    assert len(chain.entries) == 2
    assert chain.verify() is None


def test_a_refused_attach_writes_nothing_to_the_ledger() -> None:
    """A refused attach changed nothing, and a ledger carrying attempts beside changes is a
    ledger where "what does this agent carry" cannot be answered by reading it. The entry is
    therefore written after the refusal and never before.

    The positive half is the test above; this is the one that fails if the write moves to the
    top of the function, which is where somebody would put it to record the intent.

    Delete this and every refused attempt becomes a row saying a thing was attached."""
    recorder, chain = a_recorder()

    with pytest.raises(AgentTabError, match="cannot be attached"):
        attach(
            a_composition(),
            a_connector(),
            by=holding(),
            requires={"freshdesk": Capability(value="read:ticket.status")},
            recorder=recorder,
            reason_code="requested_by_owner",
        )
    with pytest.raises(AgentTabError, match="is not attached"):
        detach(
            a_composition(),
            Part.CONNECTORS,
            "freshdesk",
            recorder=recorder,
            reason_code="grant_lapsed",
        )

    assert chain.entries == ()


def test_neither_call_can_hand_back_a_composition_without_its_entry() -> None:
    """**The structural half, and the reason the pair type exists.** An entry written by a
    second call is a line somebody forgets, wraps in a condition, or moves below an early
    return; `brain.ops.export.bulk_export` reached the same conclusion about the widest
    permission act in the system and returns its audit row for the same reason.

    Asserted on the annotations rather than on a call, because the wrong version arrives as a
    signature change: an `audit: AuditEntry | None = None` parameter, or a return type
    loosened back to `Composition` so a caller can ignore the entry. Behaviour alone would
    keep passing on the day either lands.

    Delete this and the recording becomes optional again by the smallest possible edit."""
    import inspect

    for one in (attach, detach, register_skill):
        signature = inspect.signature(one)

        assert signature.return_annotation in {"Composed", Composed}, one.__name__
        taken = signature.parameters
        assert "recorder" in taken, one.__name__
        assert "reason_code" in taken, one.__name__
        assert taken["recorder"].default is inspect.Parameter.empty, one.__name__
        assert taken["reason_code"].default is inspect.Parameter.empty, one.__name__


def test_a_reason_that_is_prose_is_refused_by_the_recorder_and_not_softened_here() -> None:
    """The why is a code and not a sentence, and this module does not have its own opinion
    about that: `brain.audit.record` refuses prose because `redact_details` admits field names
    and reduces anything else to the marker, so a sentence would be stored as `<redacted>` and
    the why would be gone from the record kept to answer for it.

    What is asserted here is that the refusal is allowed through rather than wrapped. Wrapping
    it would make a rule of the ledger look like an opinion of this tab, which is the argument
    `attach` already makes about letting `Composition`'s duplicate refusal propagate.

    Delete this and somebody catches the ledger's refusal here and substitutes a default
    reason, which is a record that answers the question with a value nobody chose."""
    recorder, chain = a_recorder()

    with pytest.raises(ValueError, match="reason code"):
        attach(
            a_composition(),
            a_connector(),
            by=holding("read:ticket.status"),
            requires={"freshdesk": Capability(value="read:ticket.status")},
            recorder=recorder,
            reason_code="the owner asked me to",
        )

    assert chain.entries == ()
