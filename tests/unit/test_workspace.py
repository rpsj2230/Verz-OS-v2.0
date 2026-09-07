"""The agent workspace held to the rules that stop a front page becoming a second console.

An agent's own page is where four disclosures meet that are separately well behaved. The tab
strip is a menu, and a menu that shows an empty heading has published a count of hidden things
in words. A deep link is an address, and an address that refuses two ways is a way of asking
which agents exist. The headline figures are aggregates over everybody who used the agent, so
they are mostly other people's afternoons. And the composition is a list of attachments, which
is a list somebody will eventually want to store a copy inside.

The eight leaves claimed here are the ones with a rule in them rather than a control. An agent
is composed of ten named parts (M39.1.1.1) each of which is attached, held in a column, held as
a predicate or held as a rung; an attachment is a reference with a version that cannot move
(M39.1.1.2); an instance diverges only on what its template actually supplies (M39.1.1.4); the
strip shows a tab only when it is both readable and not empty (M39.1.2.2); a deep link answers
the same thing to all five of its failures (M39.1.2.4); the headline figures are computed at a
basis the budget screen's own grant decides (M39.1.3.1); spend per caller names the people it
may name and adds no remainder (M39.1.3.3); and the month-end projection is withheld rather
than narrowed when the spend behind it is somebody else's (M39.1.3.4).

Real `EntitlementSet`s, real `AgentRecord`s, real `Actual`s and a real `TemplateInstance`
throughout. A fixture standing in for any of them would be this module agreeing with itself.

Task ids: M39.1.1.1, M39.1.1.2, M39.1.1.4, M39.1.2.2, M39.1.2.4, M39.1.3.1, M39.1.3.3, M39.1.3.4
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from dataclasses import fields as dataclass_fields
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from brain.agents.model import AgentAudience, AgentAuthority, AgentRecord
from brain.agents.template import (
    MANIFEST_PATHS,
    SEALED_PATHS,
    FieldOwner,
    FieldSource,
    TemplateInstance,
)
from brain.chat.turns import Turn, TurnKind
from brain.console import screens as screens_module
from brain.console import workspace as workspace_module
from brain.console.reads import ConsoleRead, Plane, plane_capability
from brain.console.workspace import (
    COLUMN_FIELD,
    DEEP_LINK_PREFIX,
    MOVING_PINS,
    NAMES_THAT_WOULD_BE_AN_INLINE_COPY,
    ONLY_THE_TABS,
    PART_OF_PATH,
    PARTS_NO_TEMPLATE_SUPPLIES,
    PARTS_THAT_CAN_DIVERGE,
    PATHS_THAT_ARE_NOT_COMPOSITION,
    PINNED_PARTS,
    RANGE_DAYS,
    SPEND_OF_OTHERS_SCREEN,
    SUPPLY,
    TAB_COUNT,
    TABS,
    WORKSPACE_SURFACE,
    Attachment,
    Basis,
    CallerSpend,
    Composition,
    Landing,
    Part,
    Range,
    Supply,
    Tab,
    WorkspaceError,
    WorkspaceTab,
    basis_for,
    by_caller,
    compose,
    deep_link,
    divergent_parts,
    headline,
    intersections_in,
    projection,
    record_columns,
    resolve,
    tab_strip,
    visible_actuals,
    window,
    workspace_gaps,
)
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.lane import Lane
from brain.core.principal import PrincipalKind
from brain.core.scope import Scope
from brain.gate.context import TrafficClass
from brain.knowledge.visibility import Visibility
from brain.ops.budgets import DAYS_IN_BUDGET_MONTH, Allowance, BudgetLevel, BudgetPeriod, BudgetRow
from brain.ops.spend import Actual

AGENT = "support_triage"
READER = "p_reader"
SOMEBODY_ELSE = "p_other"

#: Halfway through a thirty-one day month, so a projection at a steady rate doubles and the
#: arithmetic is checkable by hand rather than by re-running the function under test.
MIDMONTH = datetime(2026, 1, 16, 12, 0, tzinfo=UTC)
MONTH_START = datetime(2026, 1, 1, tzinfo=UTC)


def holding(*capabilities: str, planes: tuple[Plane, ...] = (Plane.CONTENT,)) -> EntitlementSet:
    """A caller holding these capabilities company-wide, plus the console planes named.

    Both halves matter: `permitted` is a conjunction of the tool's own capability and the
    console plane, and several tests below need one without the other.
    """
    grants = [
        Grant(capability=Capability(value=one), scope=Scope(clauses=())) for one in capabilities
    ]
    grants += [Grant(capability=plane_capability(one), scope=Scope(clauses=())) for one in planes]
    return EntitlementSet(principal_id=READER, grants=tuple(grants))


def every_tab_capability() -> EntitlementSet:
    """Somebody who may read every tab in the strip."""
    return holding(*[one.read.requires.value for one in TABS])


def a_record(**overrides: object) -> AgentRecord:
    """One real agent record, so the column parts are read off the type they live on."""
    fields: dict[str, object] = {
        "agent_id": AGENT,
        "display_name": "Support triage",
        "persona": "Answers support questions in the house voice.",
        "audience": AgentAudience(level=Visibility.PERSONAL, owner_id=READER),
        "authority": AgentAuthority(capabilities=(Capability(value="read:ticket.subject"),)),
        "created_by": READER,
    }
    fields.update(overrides)
    return AgentRecord.model_validate(fields)


def an_instance(*paths: str) -> TemplateInstance:
    """A real install whose overlay claims exactly `paths`, each with a real owner row."""
    owner = FieldOwner(source=FieldSource.INSTANCE, set_by=READER, set_at=MIDMONTH)
    return TemplateInstance(
        instance_id=AGENT,
        template_id="support_ticket_agent",
        template_version=1,
        content_digest="a" * 64,
        overlay=dict.fromkeys(paths, "a locally set value"),
        overlay_owners=dict.fromkeys(paths, owner),
        created_by=READER,
    )


def a_run(
    *, principal: str = READER, cost: int = 100, at: datetime = MIDMONTH, agent: str | None = AGENT
) -> Actual:
    """One completed run, in the accounting shape `brain.ops.spend` already defines."""
    return Actual(
        principal_id=principal,
        principal_kind=PrincipalKind.HUMAN,
        traffic=TrafficClass.HUMAN_INTERACTIVE,
        department="web",
        agent_id=agent,
        model="main-1",
        lane=Lane.ANSWER,
        cost_minor=cost,
        at=at,
    )


def a_question(*, principal: str = READER, at: datetime = MIDMONTH) -> Turn:
    return Turn(kind=TurnKind.QUESTION, at=at, principal_id=principal, text="how many hours?")


def an_allowance(*, spent: int, ceiling: int = 10_000) -> Allowance:
    """The agent's own budget row and what has gone against it, both real types."""
    return Allowance(
        row=BudgetRow(
            level=BudgetLevel.AGENT,
            subject=AGENT,
            period=BudgetPeriod.MONTH,
            ceiling_minor=ceiling,
            version=1,
            author="p_admin",
            effective_from=MONTH_START,
        ),
        spent_minor=spent,
    )


# --- an agent is composed of ten named parts (M39.1.1.1) -------------------------------------


def test_an_agent_is_composed_of_the_ten_parts_the_work_breakdown_names() -> None:
    """**M39.1.1.1.** The ten are the list the workspace is arranged by: a part nothing
    enumerates has no tab, no diff row and no divergence flag, and it goes missing without
    anything failing.

    Asserted on the member values rather than on the count alone, because a count is satisfied
    by any ten names and the interesting failure is a part quietly renamed into something the
    rest of the console does not recognise.

    Delete this and `Part` can lose `memory` to a refactor that tidies the enum, and the
    memory tab becomes a heading with nothing behind it."""
    assert {one.value for one in Part} == {
        "persona",
        "knowledge",
        "connectors",
        "skills",
        "channels",
        "availability",
        "leash",
        "model_policy",
        "memory",
        "automations",
    }


def test_every_part_says_how_it_reaches_the_agent_so_the_pinnable_ones_are_derived() -> None:
    """A part with no supply is a part an attachment for would be accepted or refused by
    accident, because `Attachment` decides from `PINNED_PARTS` and that set is derived from
    `SUPPLY`.

    The positive half names the five that can be attached, so a supply changed from `COLUMN`
    to `PINNED` fails here rather than quietly letting somebody attach a second persona.

    Delete this and `SUPPLY` can lose a part, `PINNED_PARTS` silently shrinks, and attaching a
    channel starts raising `WorkspaceError`."""
    assert set(SUPPLY) == set(Part)
    assert set(PINNED_PARTS) == {
        Part.CONNECTORS,
        Part.SKILLS,
        Part.CHANNELS,
        Part.MEMORY,
        Part.AUTOMATIONS,
    }
    assert SUPPLY[Part.KNOWLEDGE] is Supply.PREDICATE
    assert SUPPLY[Part.LEASH] is Supply.RUNG


def test_workspace_gaps_reports_a_part_that_says_nothing_about_how_it_is_supplied() -> None:
    """The check inside the diagnostic, watched. `workspace_gaps` takes the supply mapping
    rather than reading the module's own, because a diagnostic that can only be run against a
    healthy tree has nothing to report and every one of its refusals survives a mutation.

    Delete this and the exhaustiveness check can be removed with every other test in this file
    still green, because they all call the diagnostic on a healthy module."""
    short: dict[Part, Supply] = {
        part: supply for part, supply in SUPPLY.items() if part is not Part.MEMORY
    }

    gaps = workspace_gaps(supply=short)

    assert any("memory has no supply" in one for one in gaps), gaps
    assert workspace_gaps() == ()


def test_every_column_part_names_a_field_the_agent_record_actually_carries() -> None:
    """A column part is one the record supplies itself, and the mapping says which field. A
    field name the record does not have renders an empty pane where the agent's own decision
    goes, and nothing else in the system would notice.

    Checked against `AgentRecord.model_fields` rather than against a list here, which is the
    constant-anchoring rule applied to a mapping: the names are held to the model's own.

    Delete this and `COLUMN_FIELD` can name `model_tier`, which reads correctly and returns
    nothing."""
    assert set(COLUMN_FIELD) == {Part.PERSONA, Part.MODEL_POLICY, Part.AVAILABILITY}
    for part, field_name in COLUMN_FIELD.items():
        assert field_name in AgentRecord.model_fields, part

    record = a_record()
    columns = record_columns(record)

    assert columns[Part.PERSONA] == record.persona
    assert columns[Part.MODEL_POLICY] is record.tier
    assert columns[Part.AVAILABILITY] is record.audience


def test_workspace_gaps_reports_a_column_part_pointing_at_a_field_that_is_not_there() -> None:
    """The other half of the same guard, watched, by handing the diagnostic a mapping that
    names a field `AgentRecord` does not have.

    Delete this and the check can go, and the first person to rename a field on the record
    finds out from a blank pane."""
    gaps = workspace_gaps(columns={Part.MODEL_POLICY: "model_tier"})

    assert any("which AgentRecord does not have" in one for one in gaps), gaps


# --- an attachment is a reference with a pinned version (M39.1.1.2) ---------------------------


def test_an_attachment_is_a_reference_and_has_nowhere_to_put_a_copy() -> None:
    """**M39.1.1.2.** A skill copied onto an agent stops being the skill in the library the
    moment either changes, and `brain.tools.skills.is_executable` then answers about the
    original while the agent runs the duplicate.

    Asserted on the field names of the type rather than on a convention, because the failure
    arrives as a field somebody adds to save a lookup, and a rule in prose does not stop it.

    Delete this and `Attachment` grows a `body`, and the review that approved the skill
    approved a different string from the one that runs."""
    names = {one.name for one in dataclass_fields(Attachment)}

    assert names == {"part", "ref", "version"}
    assert not names & NAMES_THAT_WOULD_BE_AN_INLINE_COPY


def test_workspace_gaps_reports_an_attachment_type_that_could_carry_a_body() -> None:
    """The check watched, by handing the diagnostic an attachment type that has the field.
    The healthy type cannot produce this finding, which is exactly why the parameter exists.

    Delete this and the inline-copy check can be deleted with the suite green, because
    `Attachment` never has one of those fields on a good day."""

    @dataclass(frozen=True)
    class Forked:
        part: Part
        ref: str
        version: str
        body: str

    gaps = workspace_gaps(attachment_type=Forked)

    assert any("Forked.body" in one for one in gaps), gaps


def test_an_attachment_pinned_to_a_version_that_moves_is_refused() -> None:
    """latest, main and head all read as a version and all resolve to whatever is there on
    the day, so the review that approved the attachment approved a moment. This is
    `brain.tools.skills.SkillSource`'s refusal one level up, where the attachment rather than
    the import is being written.

    The four spellings are written out here rather than read off `MOVING_PINS`, and then the
    whole set is iterated as well. Iterating alone would compare the constant against itself:
    remove `latest` from it and every side of the comparison moves together, and the test
    stays green for every set the constant could possibly hold.

    The positive half is what makes it a pin rather than a ban: a semantic version and a
    digest are both accepted, so this is not passing because everything is refused.

    Delete this and an agent can be attached to `skills/triage@latest`, and the golden set
    that proved it works was run against different words."""
    for moving in ("latest", "main", "head", "*"):
        assert moving in MOVING_PINS
        with pytest.raises(WorkspaceError, match="pinned to"):
            Attachment(part=Part.SKILLS, ref="triage", version=moving)

    for moving in sorted(MOVING_PINS):
        with pytest.raises(WorkspaceError, match="pinned to"):
            Attachment(part=Part.SKILLS, ref="triage", version=moving)

    assert Attachment(part=Part.SKILLS, ref="triage", version="1.2.3").version == "1.2.3"
    assert Attachment(part=Part.CONNECTORS, ref="freshdesk", version="b" * 64).ref == "freshdesk"

    with pytest.raises(WorkspaceError, match="carries no version"):
        Attachment(part=Part.SKILLS, ref="triage", version="  ")


def test_a_part_the_record_supplies_itself_cannot_also_be_attached() -> None:
    """An attachment of a persona would be a second copy of a value the record already
    carries, and which of the two a run used is then unanswerable.

    Delete this and a workspace can show a pinned persona beside the record's own, with
    nothing saying which one the model was given."""
    with pytest.raises(WorkspaceError, match="cannot be attached"):
        Attachment(part=Part.PERSONA, ref="house-voice", version="1.0.0")

    assert Attachment(part=Part.MEMORY, ref="agent-memory", version="7").part is Part.MEMORY


def test_a_composition_refuses_the_same_thing_attached_to_one_part_twice() -> None:
    """Two attachments of one reference are two versions of one thing, and which a run
    resolves is whichever the reader iterated first.

    The positive half attaches the same reference to two different parts, which is legitimate
    and must keep working: a connector and a channel can share a name.

    Delete this and an agent can be pinned to two versions of one skill at once."""
    one = Attachment(part=Part.SKILLS, ref="triage", version="1.0.0")
    two = Attachment(part=Part.SKILLS, ref="triage", version="2.0.0")

    with pytest.raises(WorkspaceError, match="attached to"):
        Composition(agent_id=AGENT, attachments=(one, two))

    shared = Composition(
        agent_id=AGENT,
        attachments=(one, Attachment(part=Part.CHANNELS, ref="triage", version="1.0.0")),
    )

    assert shared.pinned_parts == {Part.SKILLS, Part.CHANNELS}
    assert shared.attached_to(Part.SKILLS) == (one,)


def test_a_composition_is_built_from_the_attachments_the_reader_was_handed() -> None:
    """`compose` reads the record for its id and nothing else, so an attachment the caller
    may not see is simply not in the composition. An attachment outside somebody's reach and
    an attachment nobody made produce the same workspace.

    Delete this and `compose` can start reading a store, and the composition stops being the
    reader's own view of the agent."""
    record = a_record()

    assert compose(record).attachments == ()
    assert compose(record).agent_id == AGENT

    seen = compose(record, [Attachment(part=Part.SKILLS, ref="triage", version="1.0.0")])

    assert seen.pinned_parts == {Part.SKILLS}


# --- divergence fires only on what the template supplies (M39.1.1.4) --------------------------


def test_every_manifest_path_is_declared_as_composition_or_declared_as_not_composition() -> None:
    """**M39.1.1.4 rests on this.** A manifest path in neither set is a local edit that raises
    no divergence flag and is not declared as something that should not raise one, which is a
    silent gap rather than a decision.

    Held to `brain.agents.template.MANIFEST_PATHS` rather than to a list here, so a path added
    to the manifest fails this rather than being classified by omission.

    Delete this and the next manifest path lands in neither set, and an instance that overlays
    it looks identical to its template on the workspace."""
    covered = set(PART_OF_PATH) | PATHS_THAT_ARE_NOT_COMPOSITION

    assert covered == set(MANIFEST_PATHS)
    assert not set(PART_OF_PATH) & PATHS_THAT_ARE_NOT_COMPOSITION


def test_workspace_gaps_reports_a_manifest_path_that_is_in_neither_set_or_in_both() -> None:
    """Both halves of the same check, watched, because the healthy pair produces neither
    finding and a diagnostic that cannot be exercised is a diagnostic nobody can trust.

    Delete this and both branches can be removed with the suite green."""
    orphaned = workspace_gaps(paths=("persona", "a.new.path"))
    doubled = workspace_gaps(
        paths=("persona",), composition_paths=PART_OF_PATH, other_paths={"persona"}
    )

    assert any("is in neither set" in one for one in orphaned), orphaned
    assert any("is both a composition path and not one" in one for one in doubled), doubled


def test_an_instance_diverges_on_the_parts_its_template_supplies_and_on_no_others() -> None:
    """**M39.1.1.4.** The flag is per part because the workspace is arranged by part, and it
    is read off the overlay because that is the value a run actually uses;
    `brain.agents.upgrade` gives the argument about why an ownership row is not the place to
    read it from.

    Three cases, and the third is the discriminating one: an overlay of `identity.display_name`
    is a real local edit and is not a divergence of the composition, so a flag that fired on
    every overlaid path would fail here.

    Delete this and the flag becomes "this install has an overlay", which is true of almost
    every install and tells a reader nothing."""
    assert divergent_parts(an_instance("persona")) == {Part.PERSONA}
    assert divergent_parts(an_instance("persona", "skills")) == {Part.PERSONA, Part.SKILLS}
    assert divergent_parts(an_instance("identity.display_name")) == frozenset()
    assert divergent_parts(an_instance()) == frozenset()


def test_the_leash_is_supplied_by_a_template_and_still_cannot_diverge() -> None:
    """The leash is in the manifest, so it is a composition path, and it is sealed, so an
    overlay may not carry it. `PARTS_THAT_CAN_DIVERGE` is derived from both of the template
    module's tuples rather than listed, so sealing a sixth path removes a part from it.

    Delete this and `PARTS_THAT_CAN_DIVERGE` can be written out as four names, and the day
    somebody unseals the leash the workspace goes on saying it cannot diverge."""
    assert PART_OF_PATH["guardrails.leash"] is Part.LEASH
    assert "guardrails.leash" in SEALED_PATHS
    assert Part.LEASH not in PARTS_THAT_CAN_DIVERGE
    assert set(PARTS_THAT_CAN_DIVERGE) == {
        Part.PERSONA,
        Part.CONNECTORS,
        Part.SKILLS,
        Part.MODEL_POLICY,
    }


def test_five_of_the_ten_parts_are_not_in_a_template_at_all() -> None:
    """Channels, memory, automations, availability and the knowledge predicate are decided by
    the install, so there is nothing for an instance to disagree with. Stating it as a derived
    set is what stops a reader assuming the divergence flag covers the whole composition.

    Delete this and somebody adds `channels` to `PART_OF_PATH` on the reasonable-sounding
    grounds that a template ought to name channels, and the mapping then names a path the
    manifest does not have."""
    assert set(PARTS_NO_TEMPLATE_SUPPLIES) == {
        Part.CHANNELS,
        Part.MEMORY,
        Part.AUTOMATIONS,
        Part.AVAILABILITY,
        Part.KNOWLEDGE,
    }
    assert not PARTS_NO_TEMPLATE_SUPPLIES & set(PART_OF_PATH.values())


# --- the tab strip shows what is readable and not empty (M39.1.2.2) --------------------------


def test_the_tab_strip_is_computed_from_grants_and_never_from_who_is_asking() -> None:
    """The rule `brain.console.screens` states about the menu, one level down. A strip built
    from a role disagrees with the gate in the direction nobody notices: the tab shows because
    of the role and the tool behind it refuses because of the grant.

    The parameter list is pinned whole, so a name nobody thought to forbid is caught as well
    as the five that are.

    Delete this and `tab_strip(entitlement, role=...)` is a natural-looking convenience."""
    taken = inspect.signature(tab_strip).parameters

    assert list(taken) == ["entitlement", "populated", "now"]
    for forbidden in ("role", "roles", "is_admin", "super_admin", "override"):
        assert forbidden not in taken, forbidden


def test_a_tab_nobody_may_read_and_a_tab_with_nothing_in_it_are_one_absence() -> None:
    """**M39.1.2.2, and the whole point of the strip.** A heading reading Memory above an
    empty pane tells the reader this agent has a memory they may not read, which is the
    subtraction disclosure spelled out instead of counted.

    The discriminating assertion is the equality: the strip a caller with no memory grant sees
    is the *same tuple* as the strip a caller with the grant sees when the tab is empty. A
    test that only checked each was short would pass with two different absences.

    Delete this and one of the two conditions can be dropped, and the strip starts announcing
    either what the agent has or what the reader may not read."""
    everything = every_tab_capability()
    without_memory = holding(
        *[one.read.requires.value for one in TABS if one.tab is not Tab.MEMORY]
    )

    denied = tab_strip(without_memory, populated=[Tab.MEMORY, Tab.SETTINGS])
    empty = tab_strip(everything, populated=[Tab.SETTINGS])

    assert denied == empty
    assert [one.tab for one in denied] == [Tab.SETTINGS]

    both = tab_strip(everything, populated=[Tab.MEMORY, Tab.SETTINGS])

    assert [one.tab for one in both] == [Tab.MEMORY, Tab.SETTINGS]


def test_the_strip_returns_the_tabs_and_there_is_no_second_value_beside_them() -> None:
    """A count of the tabs that were left out is a count of what this agent has and this
    person may not see. The annotation is compared against the class name rather than against
    a literal, which is what stops the constant being checked against itself.

    Delete this and `tuple[tuple[WorkspaceTab, ...], int]` passes the diagnostic by moving the
    constant with it, and "and 3 more" becomes a reasonable-looking affordance."""
    assert f"tuple[{WorkspaceTab.__name__}, ...]" == ONLY_THE_TABS
    assert str(inspect.signature(tab_strip).return_annotation) == ONLY_THE_TABS

    strip = tab_strip(every_tab_capability(), populated=[Tab.SETTINGS, Tab.MEMORY])

    assert [type(one) for one in strip] == [WorkspaceTab, WorkspaceTab]


def test_workspace_gaps_reports_a_strip_that_could_be_told_who_is_asking_or_what_it_hid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both signature checks inside the diagnostic, watched. Patching `tab_strip` for one that
    takes a role, and then for one that returns a count, is how this test says what the broken
    module would look like without requiring one.

    Delete this and both checks can be removed with every other test in this file still green,
    because they all call the diagnostic on a healthy module."""

    def told_who_is_asking(
        entitlement: EntitlementSet, role: str, now: Any = None
    ) -> tuple[WorkspaceTab, ...]:
        return TABS

    monkeypatch.setattr(workspace_module, "tab_strip", told_who_is_asking)

    assert any("because of who somebody is" in one for one in workspace_gaps())

    def with_a_count(
        entitlement: EntitlementSet, now: Any = None
    ) -> tuple[tuple[WorkspaceTab, ...], int]:
        return TABS, 0

    monkeypatch.setattr(workspace_module, "tab_strip", with_a_count)

    assert any("a description of what it withheld" in one for one in workspace_gaps())


def test_every_tab_requires_a_capability_some_screen_already_requires() -> None:
    """A tab needing a capability no screen names would be a grant invented by a workspace:
    reachable from an agent's page and from nowhere an administrator reviews, because the
    capabilities screen lists what screens ask for.

    Held to `brain.console.screens.SCREENS` rather than to a list here, so a tab wired to
    something new fails rather than being justified by its own registry.

    Delete this and the workspace can require `read:agent_memory`, which nothing grants and
    nothing lists, and the tab is invisible to everybody for a reason nobody can find."""
    required = {one.read.requires for one in screens_module.SCREENS}

    assert {one.read.requires for one in TABS} <= required
    assert len(TABS) == TAB_COUNT == 7


def test_workspace_gaps_reports_a_tab_wired_to_a_capability_no_screen_asks_for() -> None:
    """The check watched, by handing the diagnostic a tab that requires something invented.

    Delete this and the check can go, because the healthy registry never produces it."""
    invented = WorkspaceTab(
        tab=Tab.MEMORY,
        read=ConsoleRead(
            screen="agent_workspace.memory",
            tool="console.memory",
            requires=Capability(value="read:agent_memory"),
            plane=Plane.CONTENT,
        ),
        purpose="a tab a test built so the diagnostic has something to report on",
    )

    gaps = workspace_gaps(tabs=(invented, invented))

    assert any("which no screen requires" in one for one in gaps), gaps
    assert any("registered twice" in one for one in gaps), gaps


def test_a_tab_wired_to_a_read_that_audits_itself_as_something_else_is_refused() -> None:
    """A tab whose read names another screen writes an audit row pointing at a place nobody
    can navigate to, which is the rule `brain.console.screens.Screen` enforces for screens.

    Delete this and the memory tab can audit itself as `console.memory`, and the audit trail
    for an agent's memory reads as the company-wide memory screen."""
    with pytest.raises(WorkspaceError, match="audits itself"):
        WorkspaceTab(
            tab=Tab.MEMORY,
            read=ConsoleRead(
                screen="memory",
                tool="console.memory",
                requires=Capability(value="read:memory"),
                plane=Plane.CONTENT,
            ),
            purpose="a tab whose read points at the wrong place",
        )


def test_the_strip_comes_back_in_the_order_the_work_breakdown_lists_the_tabs() -> None:
    """The order is the order somebody reads the strip in, which is why `TABS` is a tuple and
    not a mapping. Conversations first and Settings last is the shape of every workspace this
    console will have.

    Delete this and the registry can become a dict, and the strip becomes whatever the
    renderer sorted by."""
    assert [one.tab for one in TABS] == [
        Tab.CONVERSATIONS,
        Tab.AUTOMATIONS,
        Tab.PEOPLE,
        Tab.KNOWLEDGE,
        Tab.MEMORY,
        Tab.ARTIFACTS,
        Tab.SETTINGS,
    ]

    strip = tab_strip(every_tab_capability(), populated=[Tab.SETTINGS, Tab.CONVERSATIONS])

    assert [one.tab for one in strip] == [Tab.CONVERSATIONS, Tab.SETTINGS]


# --- a deep link refuses identically however it fails (M39.1.2.4) ----------------------------


def test_a_deep_link_answers_the_same_thing_to_all_five_of_its_failures() -> None:
    """**M39.1.2.4.** An address for every tab is an address a person can type, and answering
    "no such agent" and "not for you" differently turns the address bar into a way of asking
    which agents exist.

    All five are asserted against the same value rather than each against `None` separately,
    because the property is sameness rather than falsity: a version returning a different
    empty thing for one of them would pass five separate checks.

    **Each link is wrong in exactly one way and right in the other four**, which is what makes
    the row for the audience discriminating. A first version passed every failure a link with
    no populated tabs, so the audience check was masked by the empty strip behind it and
    removing it altogether survived the mutation run.

    The positive case is what stops this passing because `resolve` refuses everything.

    Delete this and the first person to add a helpful 404 makes the workspace enumerable."""
    entitlement = every_tab_capability()
    visible = {AGENT}
    populated = [Tab.SETTINGS]
    refusals = [
        resolve(
            f"/nope/{AGENT}/settings", entitlement, visible_agents=visible, populated=populated
        ),
        resolve(
            f"{DEEP_LINK_PREFIX}{AGENT}", entitlement, visible_agents=visible, populated=populated
        ),
        resolve(
            f"{DEEP_LINK_PREFIX}{AGENT}/nonsense",
            entitlement,
            visible_agents=visible,
            populated=populated,
        ),
        resolve(
            f"{DEEP_LINK_PREFIX}other/settings",
            entitlement,
            visible_agents=visible,
            populated=populated,
        ),
        resolve(
            f"{DEEP_LINK_PREFIX}{AGENT}/settings", entitlement, visible_agents=visible, populated=()
        ),
    ]

    assert refusals == [None, None, None, None, None]

    # A prefix wrong by one character, and the rest of the address correct. Sliced off
    # without being checked it leaves exactly this agent and this tab, so a resolver that
    # trimmed the prefix instead of recognising it lands here. The first version of this test
    # used `/nope/` and the trim happened to produce nothing resolvable, so removing the check
    # altogether survived the mutation run.
    assert (
        resolve(
            f"/agentsX{AGENT}/settings",
            entitlement,
            visible_agents=visible,
            populated=populated,
        )
        is None
    )

    landed = resolve(
        f"{DEEP_LINK_PREFIX}{AGENT}/settings",
        entitlement,
        visible_agents=visible,
        populated=populated,
    )

    assert landed == Landing(agent_id=AGENT, tab=workspace_module.tab(Tab.SETTINGS))


def test_a_deep_link_to_a_tab_this_caller_may_not_read_lands_nowhere() -> None:
    """The grant half of the same refusal, separated out because the populated half is easy to
    keep and the grant half is the one a later edit drops: a resolver that trusted the tab key
    and left the check to the pane would pass every test above.

    Delete this and a person who may not read memory can still reach the memory pane by
    typing its address, and whatever renders it decides."""
    without_memory = holding(
        *[one.read.requires.value for one in TABS if one.tab is not Tab.MEMORY]
    )
    link = deep_link(AGENT, Tab.MEMORY)

    assert resolve(link, without_memory, visible_agents={AGENT}, populated=[Tab.MEMORY]) is None
    assert (
        resolve(link, every_tab_capability(), visible_agents={AGENT}, populated=[Tab.MEMORY])
        is not None
    )


def test_a_landing_has_nowhere_to_write_down_why_a_link_failed() -> None:
    """A refusal that said which of the five things was wrong would answer the question the
    address bar was being used to ask. The type is the enforcement: there is no field a reason
    could go in, so adding one is a diff somebody reviews.

    Delete this and `Landing` grows a `refused` field, and the reason travels to whatever
    renders the page."""
    names = {one.name for one in dataclass_fields(Landing)}

    assert names == {"agent_id", "tab"}
    assert not names & {"refused", "because", "reason", "state", "error"}


def test_a_link_built_by_deep_link_is_one_resolve_reads_back() -> None:
    """The two halves are one grammar, and a grammar written twice is a grammar that drifts:
    a builder that emitted `/agent/` and a resolver expecting `/agents/` would leave every
    console alert pointing nowhere, with each half passing its own test.

    Delete this and the prefix can move on one side only."""
    entitlement = every_tab_capability()

    for one in Tab:
        link = deep_link(AGENT, one)
        landed = resolve(link, entitlement, visible_agents={AGENT}, populated=list(Tab))

        assert landed is not None, link
        assert landed.tab.tab is one
        assert landed.agent_id == AGENT

    with pytest.raises(WorkspaceError, match="not an address"):
        deep_link("  ", Tab.SETTINGS)


# --- the headline figures are computed at the caller's basis (M39.1.3.1) ---------------------


def test_the_front_page_shows_everybody_only_to_a_reader_who_could_open_the_budget() -> None:
    """**M39.1.3.1, and the disclosure argument the whole of the cost section turns on.** A
    figure that moves when somebody else works is a statement about their afternoon, so the
    front page may not be a shortcut past a screen's grant.

    The screen key is anchored against `brain.console.screens` rather than a capability
    written here, and the plane case is the discriminating one: a caller holding `read:budget`
    with no console plane could not open the budget screen either, and gets the narrower
    basis.

    Delete this and `basis_for` can be reduced to a capability check, and an auditor granted
    existence starts reading a department's spend off an agent's front page."""
    budget = screens_module.screen(SPEND_OF_OTHERS_SCREEN)

    assert budget.read.requires == Capability(value="read:budget")

    assert basis_for(holding("read:budget")) is Basis.EVERYONE
    assert basis_for(holding("read:question")) is Basis.OWN
    assert basis_for(holding("read:budget", planes=())) is Basis.OWN
    assert basis_for(holding("read:budget", planes=(Plane.EXISTENCE,))) is Basis.OWN


def test_a_headline_counts_only_the_rows_this_reader_may_be_shown() -> None:
    """**M39.1.3.1.** Three filters, and each one is a way the figure could have been somebody
    else's: another person's run, another agent's run, and a run outside the window.

    Both bases are asserted, because a filter tested only in the narrow direction is satisfied
    by a function that returns nothing.

    Delete this and the headline totals every row it is handed, and the first shared agent
    publishes its department's spend to whoever opens it."""
    rows = [
        a_run(principal=READER, cost=100),
        a_run(principal=SOMEBODY_ELSE, cost=900),
        a_run(principal=READER, cost=50, agent="another_agent"),
        a_run(principal=READER, cost=7, at=MIDMONTH - timedelta(days=45)),
    ]
    since, until = window(Range.THIRTY_DAYS, MIDMONTH)

    mine = headline(
        AGENT, caller_id=READER, basis=Basis.OWN, actuals=rows, since=since, until=until
    )
    everyone = headline(
        AGENT, caller_id=READER, basis=Basis.EVERYONE, actuals=rows, since=since, until=until
    )

    assert (mine.spend_minor, mine.runs) == (100, 1)
    assert (everyone.spend_minor, everyone.runs) == (1000, 2)
    assert mine.basis is Basis.OWN


def test_the_message_count_is_filtered_the_same_way_the_spend_is() -> None:
    """A message count is the same disclosure in a different unit: how often somebody else
    used the agent is their activity, and a count that escaped the basis would be the back
    door to the figure the spend refused.

    Answers are not counted, so a chatty agent does not double every reader's figure, and
    what is being counted is what people asked it.

    Delete this and `messages` is computed over every turn handed in, and the narrow basis
    leaks by a different column."""
    turns = [
        a_question(principal=READER),
        a_question(principal=SOMEBODY_ELSE),
        a_question(principal=READER, at=MIDMONTH - timedelta(days=45)),
        Turn(kind=TurnKind.ANSWER, at=MIDMONTH, principal_id=READER, text="four hundred"),
    ]
    since, until = window(Range.THIRTY_DAYS, MIDMONTH)

    mine = headline(AGENT, caller_id=READER, basis=Basis.OWN, turns=turns, since=since, until=until)
    everyone = headline(
        AGENT, caller_id=READER, basis=Basis.EVERYONE, turns=turns, since=since, until=until
    )

    assert mine.messages == 1
    assert everyone.messages == 2


def test_no_type_on_this_surface_can_say_how_much_it_left_out() -> None:
    """The rule asked of the shapes rather than of whoever edits them next, using
    `brain.ops.jobs.hidden_count_fields` rather than a second list of forbidden names: two
    lists of the same names is one that goes stale.

    The negative half proves the check is watching, because the healthy surface reports
    nothing and a check that reported nothing on a broken one would look identical.

    Delete this and `Headline` grows a `total` beside the reader's own spend, which is the
    other figure by subtraction."""
    assert workspace_gaps(surface=WORKSPACE_SURFACE) == ()

    @dataclass(frozen=True)
    class Helpful:
        spend_minor: int
        hidden: int

    gaps = workspace_gaps(surface=(Helpful,))

    assert any("Helpful.hidden" in one for one in gaps), gaps


def test_the_four_ranges_are_seven_thirty_and_ninety_days_and_the_month_so_far() -> None:
    """The windows the front page selects between. Month to date is the odd one and has no
    length: it shortens to nothing on the first of the month, and a figure that resets while a
    budget does not is read as a fall in spend.

    **The three lengths are anchored outside the mapping.** Comparing `window`'s output
    against `RANGE_DAYS` alone compares the constant with itself: change the thirty and both
    sides move, and the test is green for every length the range could hold. The middle one is
    held to `brain.ops.budgets.DAYS_IN_BUDGET_MONTH`, because a month range that disagreed
    with the month a budget is divided into would sit a figure beside a ceiling it was not
    measured against; the shortest is a week and the longest is three of those months.

    Delete this and the thirty-day range can become a calendar month, and a figure labelled
    thirty days covers thirty-one."""
    assert RANGE_DAYS[Range.SEVEN_DAYS] == timedelta(weeks=1).days
    assert RANGE_DAYS[Range.THIRTY_DAYS] == DAYS_IN_BUDGET_MONTH
    assert RANGE_DAYS[Range.NINETY_DAYS] == 3 * DAYS_IN_BUDGET_MONTH

    for one, days in RANGE_DAYS.items():
        since, until = window(one, MIDMONTH)

        assert until == MIDMONTH
        assert (until - since).days == days, one

    assert set(RANGE_DAYS) == set(Range) - {Range.MONTH_TO_DATE}
    assert window(Range.MONTH_TO_DATE, MIDMONTH) == (MONTH_START, MIDMONTH)

    with pytest.raises(WorkspaceError, match="naive instant"):
        window(Range.SEVEN_DAYS, MIDMONTH.replace(tzinfo=None))


def test_visible_actuals_keeps_a_machines_rows_because_the_label_is_not_a_filter() -> None:
    """`brain.ops.spend` labels machine traffic rather than dropping it, and what a report
    does with the label is that report's decision. An automation running as a named principal
    is that principal's spend here as it is there.

    Delete this and the front page quietly disagrees with the budget screen about what an
    agent cost, and the person reconciling an invoice finds out."""
    machine = Actual(
        principal_id=READER,
        principal_kind=PrincipalKind.SERVICE,
        traffic=TrafficClass.AUTOMATION,
        department="web",
        agent_id=AGENT,
        model="main-1",
        lane=Lane.ANSWER,
        cost_minor=40,
        at=MIDMONTH,
    )
    since, until = window(Range.THIRTY_DAYS, MIDMONTH)

    kept = visible_actuals(
        AGENT, [machine], caller_id=READER, basis=Basis.OWN, since=since, until=until
    )

    assert kept == (machine,)
    assert machine.machine is True


# --- spend attributed per caller, with no remainder (M39.1.3.3) ------------------------------


def test_spend_per_caller_names_the_people_it_may_name_and_adds_no_remainder() -> None:
    """**M39.1.3.3.** Attribution per caller is what makes one heavy user visible, and the
    obvious way to keep the column adding up is a final row reading other. That row is the
    spend of every person the reader may not be told about.

    The discriminating assertion is that the rows sum to the headline figure on both bases: a
    remainder row would make the narrow basis sum to more than the reader's own spend, and
    dropping rows would make the wide basis sum to less than the total.

    Delete this and the first person to notice the column does not add up adds the row that
    makes it."""
    rows = [a_run(principal=READER, cost=100), a_run(principal=SOMEBODY_ELSE, cost=900)]
    since, until = window(Range.THIRTY_DAYS, MIDMONTH)

    mine = by_caller(
        AGENT, caller_id=READER, basis=Basis.OWN, actuals=rows, since=since, until=until
    )
    everyone = by_caller(
        AGENT, caller_id=READER, basis=Basis.EVERYONE, actuals=rows, since=since, until=until
    )

    assert mine == (CallerSpend(principal_id=READER, spend_minor=100),)
    assert [one.principal_id for one in everyone] == [SOMEBODY_ELSE, READER]
    assert [one.spend_minor for one in everyone] == [900, 100]

    for basis, column in ((Basis.OWN, mine), (Basis.EVERYONE, everyone)):
        figure = headline(
            AGENT, caller_id=READER, basis=basis, actuals=rows, since=since, until=until
        )

        assert sum(one.spend_minor for one in column) == figure.spend_minor


def test_the_per_caller_column_carries_no_share_and_no_rank() -> None:
    """A share is the same figure divided by a total, and a total the reader was not shown is
    one they can recover from two rows and a percentage.

    Delete this and a percentage column arrives to make the heaviest user obvious, and the
    total comes with it."""
    assert {one.name for one in dataclass_fields(CallerSpend)} == {
        "principal_id",
        "spend_minor",
    }


def test_two_callers_who_spent_the_same_come_back_in_a_settled_order() -> None:
    """Ordering by spend alone leaves ties to whatever the mapping iterated, so two readings
    of an unchanged ledger are two different lists and an operator comparing them is comparing
    nothing.

    Delete this and the column reorders itself between refreshes."""
    rows = [a_run(principal="p_b", cost=100), a_run(principal="p_a", cost=100)]
    since, until = window(Range.THIRTY_DAYS, MIDMONTH)

    column = by_caller(
        AGENT, caller_id=READER, basis=Basis.EVERYONE, actuals=rows, since=since, until=until
    )

    assert [one.principal_id for one in column] == ["p_a", "p_b"]


# --- the projection is withheld rather than narrowed (M39.1.3.4) -----------------------------


def test_a_projection_is_absent_rather_than_narrowed_when_the_spend_behind_it_is_shared() -> None:
    """**M39.1.3.4.** A projection to month end is spend to date extrapolated against the
    agent's own ceiling. The ceiling belongs to nobody; the spend to date is everybody who ran
    the agent, and the headroom beside it is that subtraction already performed.

    Narrowing it would produce a confident figure that is wrong, which is worse than no
    figure, so the narrower basis gets nothing at all.

    Delete this and somebody makes the projection work for everybody by using the reader's own
    spend, and the agent's headroom is published to whoever opens the page."""
    allowance = an_allowance(spent=4000)

    assert projection(AGENT, allowance=allowance, basis=Basis.OWN, now=MIDMONTH) is None

    seen = projection(AGENT, allowance=allowance, basis=Basis.EVERYONE, now=MIDMONTH)

    assert seen is not None
    assert seen.spent_minor == 4000
    assert seen.ceiling_minor == 10_000


def test_a_projection_carries_the_month_forward_at_the_rate_so_far() -> None:
    """Halfway through a thirty-one day January, spend so far projects to roughly twice
    itself. The figure is asserted against arithmetic done here rather than against the
    function's own output, which is what stops this testing the function against itself.

    Rounded up, once, because `brain.ops.budgets` says money is counted in whole minor units
    and rounds towards the ceiling being crossed rather than away from it.

    Delete this and the projection can extrapolate over a fixed thirty days, and a February
    projection overshoots by a tenth every year."""
    seen = projection(AGENT, allowance=an_allowance(spent=4000), basis=Basis.EVERYONE, now=MIDMONTH)

    assert seen is not None

    elapsed = (MIDMONTH - MONTH_START).total_seconds()
    whole = (datetime(2026, 2, 1, tzinfo=UTC) - MONTH_START).total_seconds()

    assert seen.projected_minor == -(-4000 * whole // elapsed)
    assert seen.projected_minor > seen.spent_minor
    assert seen.over_ceiling is False

    heavy = projection(
        AGENT, allowance=an_allowance(spent=9000), basis=Basis.EVERYONE, now=MIDMONTH
    )

    assert heavy is not None
    assert heavy.over_ceiling is True


def test_a_projection_computed_from_a_naive_instant_is_refused() -> None:
    """A naive instant is hours out in whichever direction the host sits, and a month boundary
    is exactly where that shows: a projection made from one runs off the end of the wrong
    month.

    Delete this and the projection is silently wrong for a few hours either side of every
    month end, which is when somebody looks at it."""
    with pytest.raises(WorkspaceError, match="naive instant"):
        projection(
            AGENT,
            allowance=an_allowance(spent=10),
            basis=Basis.EVERYONE,
            now=MIDMONTH.replace(tzinfo=None),
        )


def test_a_projection_at_the_first_instant_of_a_month_projects_what_was_spent() -> None:
    """The boundary where the arithmetic divides by nothing. A month with no time elapsed has
    no rate to carry forward, and the honest answer is the spend itself rather than a very
    large number or an exception on the first of the month.

    Delete this and the front page raises `ZeroDivisionError` at midnight on the first."""
    seen = projection(
        AGENT, allowance=an_allowance(spent=25), basis=Basis.EVERYONE, now=MONTH_START
    )

    assert seen is not None
    assert seen.projected_minor == 25


# --- the workspace computes no reach of its own ----------------------------------------------


def test_the_workspace_intersects_no_entitlement_sets_of_its_own() -> None:
    """**The invariant's structural half.** `E_run(caller, agent)` is computed by one
    `EntitlementSet.intersect`, which `brain.gate.leash.decide` and `ops.automation.flow_reach`
    both call and neither reimplements. A third copy is a third place for the central rule to
    be subtly wrong, and the wrong copy is the one in production.

    Parsed rather than searched for the word, because the module's own docstring says
    `intersect` several times and a text search would report itself. The positive half proves
    the parser sees a real call, so this is not passing because it sees nothing.

    Delete this and a helper here starts narrowing a reach, and the console has an opinion
    about the platform's one rule."""
    assert intersections_in(inspect.getsource(workspace_module)) == ()
    assert intersections_in("caller.intersect(ceiling)\n") == (1,)
    assert intersections_in("# caller.intersect(ceiling)\n") == ()

    gaps = workspace_gaps(source="def reach(a, b):\n    return a.intersect(b)\n")

    assert any("intersects two entitlement sets" in one for one in gaps), gaps
