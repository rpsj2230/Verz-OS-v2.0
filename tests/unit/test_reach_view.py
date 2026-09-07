"""The agent workspace held to keeping two questions apart, and to disclosing neither cheaply.

Every test here is one of four failures. A block that answers the ceiling question with the
reader's own reach, or the reader's reach with the ceiling. A preview that says what a run
would return without running the gate. A rung that rose without a person. A memory viewer that
shows one person what another person's conversation produced.

**Real objects throughout, and that is not a preference.** The ceiling is
`brain.agents.model.entitlement_ceiling`, the preview is `brain.gate.invoke.invoke` over a real
`ToolRegistry`, the rungs come from a real `brain.gate.leash.Leash`, and the memory verdicts are
`brain.memory.formation.may_recall`. A stand-in for any of them would leave this file asserting
that its own idea of the invariant is self-consistent, which is the state
`tests/unit/test_agent_model.py` names in its own docstring.

**The two headline tests are cross-product tests and neither is redundant.**
`test_two_readers_holding_the_disclosure_see_one_and_the_same_ceiling` fails for code that
narrows the ceiling by the reader. `test_the_ceiling_shows_what_the_agent_holds_and_not_what
_the_reader_holds` fails for code that returns an empty ceiling to everybody. A single test
either way is satisfied by one of the two wrong implementations.

Task ids: M39.3.1.1, M39.3.1.2, M39.3.1.3, M39.3.1.4, M39.3.1.5
Task ids: M39.3.2.1, M39.3.2.2, M39.3.2.3, M39.3.2.4, M39.3.2.5
Task ids: M39.4.1.1, M39.4.1.2, M39.4.1.3, M39.4.1.5
Task ids: M39.4.2.1, M39.4.2.2, M39.4.2.3, M39.4.2.4, M39.4.2.5
"""

from __future__ import annotations

import inspect
from dataclasses import fields as dataclass_fields
from datetime import UTC, datetime, timedelta

import pytest

from brain.agents.model import (
    AUDIENCE_IS_NOT_AUTHORITY,
    AgentAudience,
    AgentAuthority,
    AgentRecord,
    AgentViewer,
    entitlement_ceiling,
)
from brain.console.reach_view import (
    AVAILABILITY_HEADING,
    BACK_LINK,
    CEILING_DISCLOSURE,
    CEILING_HEADING,
    DEMOTED_TO,
    IRREVERSIBLE,
    MINIMUM_AGREEMENT_RATE,
    MINIMUM_CLEAN_RUNS,
    PREVIEW_DISCLOSURE,
    PREVIEW_HEADING,
    PREVIEW_RETURNS_NOTHING,
    AvailabilityBlock,
    CircuitBreak,
    LeashError,
    MemoryViewError,
    Operation,
    PromotionEvidence,
    Provenance,
    RungChange,
    RunPreview,
    TierOneRow,
    TierTwoRow,
    Watch,
    active_tiers,
    availability_block,
    breaker_trips,
    ceiling_block,
    freeze,
    leash_matrix,
    may_raise,
    provenance_of,
    reach_view_gaps,
    readable,
    revisions,
    run_preview,
    run_reach,
    rung_history,
    separate_memory,
    split_memory,
    thaw,
    tier_one_rows,
    tier_three_routing,
    tier_two_rows,
)
from brain.console.screens import screen
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.envelope import Entity, IdentityMode, SideEffect, ToolDefinition, TypedResult
from brain.core.redaction import render_lock
from brain.core.scope import Scope
from brain.gate.catalogue import SIDE_EFFECT_ORDER, EmptyCatalogueError, ProjectedCatalogue
from brain.gate.injection import AutonomyTier, RiskAssessment
from brain.gate.leash import Leash, LeashEntry
from brain.knowledge.visibility import Visibility
from brain.memory.correction import Correction, Demotion, Supersession
from brain.memory.digest import Learning
from brain.memory.formation import Formation, MemoryKind, clause_place
from brain.memory.signals import Signal
from brain.memory.tiers import (
    PROMOTION_AGREEMENT,
    Change,
    Occurrence,
    Tier,
    blast_radius,
    may_promote,
    propose,
)
from brain.ops.halt import MINIMUM_REASON
from brain.tools.registry import ToolRegistry

NOW = datetime(2026, 9, 8, 9, 0, tzinfo=UTC)

STEWARD = "u_wei_ling"
COLLEAGUE = "u_priya"
STRANGER = "u_ahmad"

WEB = "web"
FINANCE = "finance"

#: Distinct from every scope slug and tool object in the tree, so this estate cannot trip
#: `brain.ops.sweeps.sweep_slug_collisions`.
DESK = "support_triage"

IN_WEB = clause_place(department=WEB)
IN_FINANCE = clause_place(department=FINANCE)

CLIENT_TOOL = "client.read_summary"
TICKET_TOOL = "ticket.read_status"
CLIENT_CAP = "read:client.name"
TICKET_CAP = "read:ticket.status"


# ------------------------------------------------------------------------------- fixtures
class ClientRow(Entity):
    name: str = ""


def a_handler() -> TypedResult[ClientRow]:
    return TypedResult[ClientRow]()


def _definition(name: str, capability: str, effect: SideEffect = SideEffect.NONE) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description="does a thing",
        entity=name.split(".")[0],
        required_capability=capability,
        side_effect=effect,
        identity_mode=IdentityMode.DELEGATED,
    )


def registry() -> ToolRegistry:
    """A real registry with two tools, so a projection has something to narrow."""
    built = ToolRegistry()
    built.register(_definition(CLIENT_TOOL, CLIENT_CAP), a_handler)
    built.register(_definition(TICKET_TOOL, TICKET_CAP), a_handler)
    return built


def holder(
    *capabilities: str,
    principal_id: str = STEWARD,
    scope: Scope | None = None,
) -> EntitlementSet:
    return EntitlementSet(
        principal_id=principal_id,
        grants=tuple(
            Grant(capability=Capability(value=one), scope=scope or Scope.unrestricted())
            for one in capabilities
        ),
    )


def authority(
    *capabilities: str,
    scope: Scope | None = None,
    tools: frozenset[str] = frozenset({CLIENT_TOOL}),
    effect: SideEffect = SideEffect.NONE,
) -> AgentAuthority:
    return AgentAuthority(
        scope=scope if scope is not None else Scope.unrestricted(),
        capabilities=tuple(Capability(value=one) for one in capabilities),
        allowed_tools=tools,
        max_side_effect=effect,
    )


def record(
    *,
    agent_id: str = DESK,
    audience: AgentAudience | None = None,
    reach: AgentAuthority | None = None,
) -> AgentRecord:
    return AgentRecord(
        agent_id=agent_id,
        display_name="Support triage",
        persona="Answers support questions in the house voice.",
        audience=audience or AgentAudience(level=Visibility.PERSONAL, owner_id=STEWARD),
        authority=reach or authority(CLIENT_CAP),
        created_by=STEWARD,
    )


def viewer(principal_id: str, *departments: str) -> AgentViewer:
    return AgentViewer(principal_id=principal_id, departments=frozenset(departments))


def learning(
    memory_id: str,
    change: Change = Change.PREFERENCE,
    *,
    at: datetime = NOW,
    scope: Scope = IN_WEB,
    capability: str = CLIENT_CAP,
    kind: MemoryKind = MemoryKind.ADAPTIVE,
    writer: str = COLLEAGUE,
    agent_id: str | None = DESK,
    replaced_id: str | None = None,
    evidence: frozenset[Signal] = frozenset({Signal.REASKED}),
) -> Learning:
    return Learning(
        memory_id=memory_id,
        proposal=propose(change, subject=f"subject:{memory_id}"),
        formation=Formation(
            principal_id=writer,
            capabilities=(Capability(value=capability),),
            scope=scope,
            ent_hash="0" * 32,
            formed_at=at,
            kind=kind,
        ),
        evidence=evidence,
        agent_id=agent_id,
        replaced_id=replaced_id,
    )


def preview_of(
    *,
    subject: EntitlementSet,
    previewer: EntitlementSet,
    reach: AgentAuthority | None = None,
    leash: Leash | None = None,
) -> RunPreview | None:
    return run_preview(
        record=record(reach=reach),
        subject_id=subject.principal_id,
        subject_entitlement=subject,
        previewer=previewer,
        registry=registry(),
        leash=leash or Leash(),
        assessment=RiskAssessment(score=0, matched=()),
        now=NOW,
    )


# ============================================================ M39.3.1.1 the availability block
def test_the_availability_block_says_who_may_start_an_agent_and_never_what_it_reaches() -> None:
    """**The structural half of the two-block separation.**

    Asserted on the field names rather than on a rendered heading, because a heading is text
    a docstring can supply and a field is a thing a renderer can read. There is no capability,
    no ceiling, no entitlement and no tool list on this shape, so a renderer cannot put one
    under the availability heading however hard the pressure to.

    Delete this and the block grows a `capabilities` field the first time somebody wants both
    facts on one card, and the copy on it is then contradicted by the field beside it."""
    block = availability_block(record(), viewer(STEWARD))
    names = {one.name for one in dataclass_fields(AvailabilityBlock)}

    assert block.level == Visibility.PERSONAL.value
    assert block.owner_id == STEWARD
    assert names.isdisjoint(
        {"capabilities", "capability", "ceiling", "entitlement", "tools", "reach"}
    )


def test_a_person_in_the_audience_and_a_person_outside_it_are_told_apart() -> None:
    """The positive and the negative in one test, because a block that said nobody was ever
    included would pass a refusal test and be useless.

    `reader_is_included` is `brain.agents.model.visible_to`, which is the predicate
    `select_agent` actually skips an agent on, so a block calling somebody included is a
    block about an agent that would really route to them.

    Delete this and `visible_to` can be replaced by a constant and the availability block
    still looks right on the one screen anybody checks."""
    departmental = record(
        audience=AgentAudience(level=Visibility.DEPARTMENT, owner_id=STEWARD, department=WEB)
    )

    assert availability_block(departmental, viewer(COLLEAGUE, WEB)).reader_is_included is True
    assert availability_block(departmental, viewer(STRANGER, FINANCE)).reader_is_included is False


def test_availability_is_computed_without_any_reach_being_available_to_consult() -> None:
    """The other half, read off the signature. `availability_block` takes a record and a
    viewer, and an `AgentViewer` carries no entitlement, so there is no path by which
    authority could reach this decision even if a later edit wanted one.

    Delete this and an entitlement parameter appears here, and the day it is consulted the
    audience starts widening with the ceiling, which is the coupling
    `brain.agents.model.AUDIENCE_IS_NOT_AUTHORITY` exists to refuse."""
    taken = set(inspect.signature(availability_block).parameters)

    assert taken == {"record", "reader"}
    assert "entitlement" not in {one.name for one in dataclass_fields(AgentViewer)}


# ================================================================ M39.3.1.2 the ceiling block
def test_two_readers_holding_the_disclosure_see_one_and_the_same_ceiling() -> None:
    """**The test this whole surface exists for.** A ceiling is a property of the agent, so
    two people who may see it see the same thing, whatever else they hold.

    The two readers here hold disjoint grants: one reaches clients, the other reaches tickets
    in another department, and the agent's ceiling covers both. Code that narrowed the ceiling
    by the reader would hand each of them half of it, and each would believe that half was the
    agent's limit.

    Delete this and `ceiling_block` can start intersecting, which is the collapse the group is
    named after and which nothing else in this file would notice."""
    agent = record(reach=authority(CLIENT_CAP, TICKET_CAP))
    one = ceiling_block(agent, holder(CEILING_DISCLOSURE.value, CLIENT_CAP, principal_id=STEWARD))
    other = ceiling_block(
        agent,
        holder(CEILING_DISCLOSURE.value, TICKET_CAP, principal_id=COLLEAGUE, scope=IN_FINANCE),
    )

    assert one == other
    assert one.capabilities == (CLIENT_CAP, TICKET_CAP)


def test_the_ceiling_shows_what_the_agent_holds_and_not_what_the_reader_holds() -> None:
    """The sibling of the test above, and it fails for the opposite wrong implementation: a
    `ceiling_block` returning nothing to everybody satisfies equality and discloses nothing.

    This reader holds the vocabulary grant and none of the agent's own capabilities, so a
    ceiling narrowed to them would be empty. It is not: it is the agent's set, read off
    `entitlement_ceiling`, which is the same object `E_run` intersects by.

    Delete this and the safest possible bug, a ceiling that is always locked or always empty,
    passes the rest of this file."""
    agent = record(reach=authority(CLIENT_CAP, TICKET_CAP))
    block = ceiling_block(agent, holder(CEILING_DISCLOSURE.value))

    assert block.locked is False
    assert block.capabilities == tuple(
        sorted(one.capability.value for one in entitlement_ceiling(agent).grants)
    )
    assert block.render() == (CLIENT_CAP, TICKET_CAP)


def test_a_reader_without_the_vocabulary_grant_gets_one_lock_and_no_count() -> None:
    """Locked means one string, from `brain.core.redaction.render_lock`, which takes no
    arguments so it cannot vary by reader, by field or by reason.

    Asserted against `render_lock()` rather than against the literal it returns, because the
    property is that this surface uses the system's one lock and not that the word is
    "Restricted".

    Delete this and the withheld case grows a sentence of its own, which two people comparing
    screens can read, or a count, which is the subtraction rule broken outright."""
    block = ceiling_block(record(reach=authority(CLIENT_CAP, TICKET_CAP)), holder(CLIENT_CAP))

    assert block.locked is True
    assert block.capabilities == ()
    assert block.scope is None
    assert block.max_side_effect is None
    assert block.render() == (render_lock(),)


def test_the_ceiling_disclosure_is_the_grant_the_capabilities_screen_already_requires() -> None:
    """The constant, anchored outside itself.

    `CEILING_DISCLOSURE` is written out in `reach_view` rather than read off the screen
    registry, so this comparison is against another module's value rather than against itself.
    Repointing either one fails here, which is the point: a ceiling is a subset of the
    capability vocabulary and must not acquire a private grant of its own that somebody could
    hand out without meaning to disclose the vocabulary.

    Delete this and the two drift, and the ceiling ends up behind a grant nobody reviewing
    access would recognise as a disclosure decision."""
    assert screen("capabilities").read.requires == CEILING_DISCLOSURE


def test_the_preview_disclosure_is_the_grant_the_people_screen_already_requires() -> None:
    """The same anchoring for the other of the two constants, and a separate test because
    they are separate claims: one is about the capability vocabulary and the other is about
    reading somebody's grants.

    Delete this and the preview acquires a private grant of its own, which somebody could
    hand out without realising they were handing out a way to enumerate a colleague's
    access."""
    assert screen("people").read.requires == PREVIEW_DISCLOSURE


def test_the_three_headings_are_three_different_sentences() -> None:
    """A heading is what the reader actually reads, and two blocks under one heading is the
    collapse without a line of code changing.

    Delete this and a tidy-up that gives the ceiling and the preview the same heading passes
    every other test in this file, because every other test asserts on values."""
    assert len({AVAILABILITY_HEADING, CEILING_HEADING, PREVIEW_HEADING}) == 3


def test_the_module_reports_no_gaps_as_it_stands() -> None:
    """`reach_view_gaps` is seven checks about edits somebody would make for a good reason,
    and a diagnostic nobody runs is a diagnostic that is wrong. This is what runs it.

    Green here is the baseline the checks are worth having: a gaps function that always
    returned findings would be switched off, and one that could never return any is not
    checking anything, which is what the mutations against `IRREVERSIBLE` and the headings
    demonstrate it is not.

    Delete this and every one of the seven becomes a comment."""
    assert reach_view_gaps() == ()


# ======================================================================= M39.3.1.3 the copy
def test_the_availability_block_carries_the_rule_itself_and_not_a_second_wording_of_it() -> None:
    """`copy` is `brain.agents.model.AUDIENCE_IS_NOT_AUTHORITY`, the same object, so a second
    statement of the rule cannot appear here and drift from the first.

    Identity rather than equality, because a retyped copy of the same sentence would satisfy
    equality and is exactly the thing being refused: one of the two gets edited later.

    The copy has to name both things it separates, or it is a sentence about one of them.
    That is asserted against `brain.agents.model`'s constant rather than against a string in
    this file, so it is a property of the rule and not of a fixture.

    Delete this and the console grows its own phrasing of the rule, and the two are then two
    rules that agree today."""
    block = availability_block(record(), viewer(STEWARD))
    taken = set(inspect.signature(availability_block).parameters)
    said = AUDIENCE_IS_NOT_AUTHORITY.lower()

    assert block.copy is AUDIENCE_IS_NOT_AUTHORITY
    assert block.heading == AVAILABILITY_HEADING
    assert taken.isdisjoint({"copy", "heading", "text", "wording"})
    assert "audience" in said
    assert "authority" in said


# ================================================== M39.3.1.4 and M39.3.1.5 the worked preview
def test_a_preview_returns_the_tools_that_persons_run_would_actually_reach() -> None:
    """**The positive case.** Without it every refusal below is satisfied by a `run_preview`
    that always returns nothing.

    The subject here reaches both tools and the agent allows both, so the preview names both
    and carries the rung the run would be held to.

    Delete this and a preview that always says nothing passes the rest of this section."""
    subject = holder(CLIENT_CAP, TICKET_CAP, principal_id=COLLEAGUE)
    seen = preview_of(
        subject=subject,
        previewer=holder(PREVIEW_DISCLOSURE.value),
        reach=authority(CLIENT_CAP, TICKET_CAP, tools=frozenset({CLIENT_TOOL, TICKET_TOOL})),
    )

    assert seen is not None
    assert seen.reaches() == (CLIENT_TOOL, TICKET_TOOL)
    assert seen.rung() is AutonomyTier.SHADOW
    assert seen.notice == ""


def test_a_preview_is_narrowed_by_the_agent_ceiling_and_not_only_by_the_person() -> None:
    """The preview is `E_run` and not `E(caller)`, which is what makes it a preview of this
    agent rather than of this person.

    The subject reaches both tools; the agent allows one. A preview computed from the
    subject's grants alone would name both, and an administrator would grant nothing because
    the screen said the access was already there.

    Delete this and the preview stops being about the agent, and the two questions this
    surface separates are collapsed inside the third block."""
    subject = holder(CLIENT_CAP, TICKET_CAP, principal_id=COLLEAGUE)
    seen = preview_of(
        subject=subject,
        previewer=holder(PREVIEW_DISCLOSURE.value),
        reach=authority(CLIENT_CAP, tools=frozenset({CLIENT_TOOL})),
    )

    assert seen is not None
    assert seen.reaches() == (CLIENT_TOOL,)


def test_a_preview_of_a_run_that_would_start_nothing_names_nothing_it_refused() -> None:
    """A refused run is one sentence, identical whatever the reason, on
    `brain.gate.leash.REFUSAL_NOTICE`'s argument.

    The exception `invoke` raises names which required tools failed to resolve, and putting it
    on a screen would answer the ceiling question one capability at a time for a reader who
    was refused the ceiling block.

    Delete this and the refusal starts explaining itself, and the preview becomes the probe
    the locked ceiling block exists to prevent."""
    seen = preview_of(
        subject=holder(TICKET_CAP, principal_id=STRANGER),
        previewer=holder(PREVIEW_DISCLOSURE.value),
        reach=authority(CLIENT_CAP, tools=frozenset({CLIENT_TOOL})),
    )

    assert seen is not None
    assert seen.invocation is None
    assert seen.reaches() == ()
    assert seen.rung() is None
    assert seen.notice == PREVIEW_RETURNS_NOTHING
    assert CLIENT_TOOL not in seen.notice
    assert CLIENT_CAP not in seen.notice


def test_previewing_somebody_elses_run_needs_the_grant_that_reading_grants_needs() -> None:
    """A preview of a person's run is a report of what that person holds, so it is governed by
    the capability the People screen requires.

    `None` rather than a refusal object: a reader who may not ask learns nothing about whether
    the person has any grants at all, which is the answer `select_agent` gives for an agent
    somebody cannot see.

    Delete this and any reader of the agent workspace can enumerate a colleague's access one
    preview at a time."""
    assert (
        preview_of(
            subject=holder(CLIENT_CAP, principal_id=COLLEAGUE),
            previewer=holder(CLIENT_CAP, principal_id=STRANGER),
        )
        is None
    )


def test_the_preview_carries_a_catalogue_only_the_projector_could_have_built() -> None:
    """**M39.3.1.5 as a structural property rather than a promise.**

    `ProjectedCatalogue` refuses construction outside `brain.gate.catalogue.project`, so a
    preview holding one is proof the projection ran. Both halves are asserted: that the
    preview has one, and that building one by hand is refused, because the second is what
    makes the first mean anything.

    Delete this and `run_preview` can be rewritten to assemble a list of tool names, which
    would look identical on the screen and would be a second projector.
    """
    seen = preview_of(
        subject=holder(CLIENT_CAP, principal_id=COLLEAGUE),
        previewer=holder(PREVIEW_DISCLOSURE.value),
    )

    assert seen is not None
    assert seen.invocation is not None
    assert isinstance(seen.invocation.catalogue, ProjectedCatalogue)
    with pytest.raises(EmptyCatalogueError):
        ProjectedCatalogue(static=(), caller_specific=(), token=object())


def test_run_preview_has_no_parameter_a_tool_list_could_arrive_through() -> None:
    """The other half of the same rule, read off the signature so that it holds for an
    implementation nobody has written yet.

    Delete this and a `tools=` argument appears here as a test convenience and becomes the way
    the screen answers when the gate is slow."""
    taken = set(inspect.signature(run_preview).parameters)

    assert taken.isdisjoint({"tools", "catalogue", "estimate", "expected", "sample", "assume"})
    assert "registry" in taken


def test_the_pair_reach_is_the_platforms_one_intersection_and_not_a_second_one() -> None:
    """`run_reach` is `E(caller) intersect agent_ceiling`, computed by
    `EntitlementSet.intersect`, and this asserts the answer against that method directly
    rather than against a value this file assembled.

    The agent is a lens: a caller holding nothing comes out holding nothing however wide the
    ceiling, and a caller holding more than the ceiling comes out at the ceiling.

    Delete this and a third implementation of the central rule can appear on a console
    module, which is what `tests/invariants/test_single_implementation.py` counts by name and
    would not catch if it were spelled differently."""
    agent = record(reach=authority(CLIENT_CAP))
    caller = holder(CLIENT_CAP, TICKET_CAP)

    assert run_reach(caller, agent) == caller.intersect(entitlement_ceiling(agent))
    assert run_reach(holder(), agent).grants == ()
    assert tuple(one.capability.value for one in run_reach(caller, agent).grants) == (CLIENT_CAP,)


# ================================================================== M39.3.2.1 the leash matrix
def test_a_rung_on_one_operation_leaves_every_other_operation_where_it_was() -> None:
    """**The property the matrix exists for.** An agent trusted to read a client is not
    thereby trusted to write to one, and a matrix that filled a blank cell from its row would
    put back the per-agent default `brain.gate.leash.Leash` deliberately has no field for.

    Driven through a real `Leash`, so the cell is `rung_for`'s answer rather than this file's.

    Delete this and the matrix can inherit, and the inheritance reads on screen as the table
    working."""
    leash = Leash(
        entries=(
            LeashEntry(
                agent_id=DESK,
                target="client.read",
                scope=Scope.unrestricted(),
                rung=AutonomyTier.AUTONOMOUS,
            ),
        )
    )
    matrix = leash_matrix(leash, DESK, entities=["client"])

    assert matrix.rung("client", Operation.READ) is AutonomyTier.AUTONOMOUS
    assert matrix.rung("client", Operation.DRAFT) is AutonomyTier.SHADOW
    assert matrix.rung("client", Operation.WRITE) is AutonomyTier.SHADOW


def test_every_cell_of_the_matrix_holds_the_rung_configured_for_that_cell_alone() -> None:
    """The positive case over a full grid: two entities and three operations, each configured
    differently, and every one of the six comes back as configured.

    Without this, a matrix that returned SHADOW everywhere would pass the test above.

    Delete this and the matrix can stop reading the leash at all."""
    wanted = {
        ("client", Operation.READ): AutonomyTier.AUTONOMOUS,
        ("client", Operation.DRAFT): AutonomyTier.ASSISTED,
        ("client", Operation.WRITE): AutonomyTier.SHADOW,
        ("ticket", Operation.READ): AutonomyTier.ASSISTED,
        ("ticket", Operation.DRAFT): AutonomyTier.SHADOW,
        ("ticket", Operation.WRITE): AutonomyTier.AUTONOMOUS,
    }
    leash = Leash(
        entries=tuple(
            LeashEntry(
                agent_id=DESK,
                target=f"{entity}.{operation.value}",
                scope=Scope.unrestricted(),
                rung=rung,
            )
            for (entity, operation), rung in wanted.items()
        )
    )
    matrix = leash_matrix(leash, DESK, entities=["client", "ticket"])

    assert len(matrix.cells) == len(wanted)
    for (entity, operation), rung in wanted.items():
        assert matrix.rung(entity, operation) is rung


def test_a_matrix_built_in_one_department_is_not_the_matrix_built_in_another() -> None:
    """The "and scope" half of the leaf. A rung is per agent, per target *and* per scope, so
    an agent trusted in maintenance is not trusted in finance, and the matrix has to be read
    against the row the work is happening on.

    The same leash and the same entities produce two different grids for two different rows,
    which is `Scope.matches` doing its job through `rung_for` rather than through anything
    written here.

    Delete this and the matrix can drop the row, and a grid computed once is shown for every
    department, which is trust earned in one place spending itself in another."""
    leash = Leash(
        entries=(
            LeashEntry(
                agent_id=DESK,
                target="client.write",
                scope=Scope.department(WEB),
                rung=AutonomyTier.AUTONOMOUS,
            ),
        )
    )
    in_web = leash_matrix(leash, DESK, entities=["client"], row={"department": WEB})
    in_finance = leash_matrix(leash, DESK, entities=["client"], row={"department": FINANCE})

    assert in_web.rung("client", Operation.WRITE) is AutonomyTier.AUTONOMOUS
    assert in_finance.rung("client", Operation.WRITE) is AutonomyTier.SHADOW


def test_a_matrix_refuses_an_entity_that_already_names_an_operation() -> None:
    """`brain.gate.leash.TARGET` admits one dot. Composing a second produces a target no entry
    can ever match, and the grid comes back all SHADOW, which reads as a cautious
    configuration rather than as a broken lookup.

    Delete this and the most confusing possible failure ships looking correct."""
    with pytest.raises(LeashError):
        leash_matrix(Leash(), DESK, entities=["ticket.update_status"])


def test_asking_the_matrix_for_a_cell_it_was_not_built_for_refuses_rather_than_guessing() -> None:
    """A matrix that answered for an entity nobody asked about would be the fallback the leash
    refuses to have, moved to the layer that renders it.

    Delete this and `rung` starts returning `MISSING_ENTRY_RUNG` for anything, which is a
    plausible-looking answer about a target this matrix knows nothing about."""
    matrix = leash_matrix(Leash(), DESK, entities=["client"])

    with pytest.raises(LeashError):
        matrix.rung("invoice", Operation.WRITE)


# ============================================================== M39.3.2.2 promotion evidence
def test_a_rung_rises_on_evidence_that_clears_both_bars_and_names_a_person() -> None:
    """The positive case. A guard tested only by its refusals is satisfied by a function that
    refuses everything, and a leash console that can never raise a rung is a console nobody
    uses twice.

    Delete this and every refusal below is met by `may_raise` returning False."""
    evidence = PromotionEvidence(
        clean_runs=MINIMUM_CLEAN_RUNS,
        agreement_rate=MINIMUM_AGREEMENT_RATE,
        approver_id=STEWARD,
    )

    assert (
        may_raise(
            was=AutonomyTier.SHADOW,
            proposed=AutonomyTier.ASSISTED,
            evidence=evidence,
            effect=SideEffect.WRITE,
        )
        is True
    )


@pytest.mark.parametrize(
    "evidence",
    [
        None,
        PromotionEvidence(
            clean_runs=MINIMUM_CLEAN_RUNS - 1,
            agreement_rate=1.0,
            approver_id=STEWARD,
        ),
        PromotionEvidence(
            clean_runs=MINIMUM_CLEAN_RUNS,
            agreement_rate=MINIMUM_AGREEMENT_RATE - 0.01,
            approver_id=STEWARD,
        ),
    ],
    ids=["no evidence at all", "too few clean runs", "agreement below the bar"],
)
def test_a_rung_does_not_rise_on_absent_or_thin_evidence(
    evidence: PromotionEvidence | None,
) -> None:
    """Three ways the evidence fails, each one a separate refusal rather than one lumped
    check, because the interesting case is the one somebody drops while making another pass.

    Delete this and a rung rises on an empty record, which is the state every agent is in on
    its first day."""
    assert (
        may_raise(
            was=AutonomyTier.SHADOW,
            proposed=AutonomyTier.AUTONOMOUS,
            evidence=evidence,
            effect=SideEffect.WRITE,
        )
        is False
    )


def test_evidence_with_no_named_approver_cannot_be_constructed_at_all() -> None:
    """A threshold being met is not a person deciding, and a tier-three change waits for a
    person. Refused at construction rather than at the check, so a record of a rung rise
    always names somebody.

    Delete this and the history fills with rises attributed to a number."""
    with pytest.raises(LeashError):
        PromotionEvidence(clean_runs=99, agreement_rate=1.0, approver_id="  ")


def test_a_rung_falls_without_any_evidence_or_approver_at_all() -> None:
    """The asymmetry, and it is the half that matters during an incident: turning something
    down must never be the operation with paperwork on it.

    Both directions asserted, so an implementation that simply returned True is caught by the
    tests above and one that simply returned False is caught here.

    Delete this and somebody discovers mid-incident that they cannot lower a rung without
    assembling a promotion record."""
    assert (
        may_raise(
            was=AutonomyTier.AUTONOMOUS,
            proposed=AutonomyTier.SHADOW,
            evidence=None,
            effect=SideEffect.MONEY,
        )
        is True
    )
    assert (
        may_raise(
            was=AutonomyTier.ASSISTED,
            proposed=AutonomyTier.ASSISTED,
            evidence=None,
            effect=SideEffect.MONEY,
        )
        is True
    )


def test_the_clean_run_bar_is_at_least_the_bar_a_tier_two_shortcut_has_to_clear() -> None:
    """The constant, anchored against another module's value rather than against itself.

    A rung rise is a tier-three change and a procedural shortcut is tier two, so the evidence
    bar for the first cannot sit below the bar for the second.

    The agreement rate has no other module's figure to be anchored against, so what is
    asserted is the property that makes any figure right: it has to be above one half. At or
    below that, the person reviewing disagrees at least as often as they agree, and a rung
    rising on that is a rung rising on a coin flip. A figure above a half and below nine
    tenths is a judgement this test deliberately does not make, and that is recorded rather
    than dressed up as a check.

    Delete this and `MINIMUM_CLEAN_RUNS` can be lowered to one with both of its own tests
    still green, because they import it."""
    assert MINIMUM_CLEAN_RUNS >= PROMOTION_AGREEMENT
    assert 0.5 < MINIMUM_AGREEMENT_RATE <= 1.0


def test_a_leash_increase_is_gated_so_agreement_alone_can_never_promote_one() -> None:
    """The premise the whole asymmetry rests on, asserted against `brain.memory.tiers`
    directly rather than restated here.

    Ten independent occurrences on separate days are handed to the real `may_promote`, which
    refuses because the change is gated and agreement is not what a gated change waits for.

    Delete this and this module can grow its own promotion rule that evidence satisfies, and
    a trust increase happens because three conversations agreed."""
    proposal = propose(Change.LEASH_INCREASE, subject="agent:support_triage")
    plenty = [Occurrence(conversation_id=f"c_{n}", on=NOW - timedelta(days=n)) for n in range(10)]

    assert blast_radius(Change.LEASH_INCREASE) is Tier.GATED
    assert may_promote(proposal, plenty, now=NOW) is False


# ================================================================ M39.3.2.3 circuit breakers
def test_a_rung_that_fell_shows_the_metric_and_the_two_figures_that_tripped_it() -> None:
    """A demotion a person cannot act on is a demotion somebody reverses on the next
    complaint, so the metric, the measurement and the threshold all travel with it.

    Asserted on the fields and then on the rendered sentence containing all three, rather than
    on the sentence alone, because a sentence is text a docstring could supply.

    Delete this and the console shows a rung that dropped with nothing beside it."""
    tripped = CircuitBreak(metric="agreement_rate", measured=0.4, threshold=0.9, at=NOW)
    rendered = tripped.render()

    assert tripped.metric == "agreement_rate"
    assert str(tripped.measured) in rendered
    assert str(tripped.threshold) in rendered
    assert tripped.metric in rendered


@pytest.mark.parametrize(
    ("watch", "measured", "trips"),
    [
        (Watch.FALLS_BELOW, 0.4, True),
        (Watch.FALLS_BELOW, 0.9, False),
        (Watch.FALLS_BELOW, 1.0, False),
        (Watch.RISES_ABOVE, 1.4, True),
        (Watch.RISES_ABOVE, 0.9, False),
        (Watch.RISES_ABOVE, 0.9, False),
    ],
    ids=[
        "a rate that fell",
        "a rate on its threshold",
        "a rate above it",
        "a count that rose",
        "a count under it",
        "a count on its threshold",
    ],
)
def test_a_breaker_trips_in_the_direction_its_metric_is_bad_in(
    watch: Watch, measured: float, trips: bool
) -> None:
    """Both directions, because a breaker that assumed one would be silently inert for half
    the metrics anybody wires to it, and inert looks exactly like a system behaving well.

    Equality does not trip on either side: a threshold is the worst acceptable value, and a
    breaker firing at equality fires on the day somebody sets the threshold to what they have
    just measured.

    Delete this and the breaker fires one way only, and the metric nobody tested is the one
    that never demotes anything."""
    broken = breaker_trips(
        watch=watch, metric="agreement_rate", measured=measured, threshold=0.9, at=NOW
    )

    assert (broken is not None) is trips
    if broken is not None:
        assert broken.measured == measured
        assert broken.threshold == 0.9


def test_a_tripped_breaker_puts_the_rung_on_the_bottom_and_not_one_step_down() -> None:
    """A step down leaves the agent still acting while whatever tripped the breaker is still
    true, so the rung walks down over hours while the thing being measured keeps happening.

    Asserted against the bottom of `AutonomyTier` rather than against zero, so a member added
    below `SHADOW` moves this with it rather than leaving a literal behind.

    Delete this and the demotion becomes a decrement, which is the shape that reads as
    proportionate and is the one that keeps an agent running through an incident."""
    tripped = breaker_trips(
        watch=Watch.FALLS_BELOW, metric="agreement_rate", measured=0.1, threshold=0.9, at=NOW
    )

    assert tripped is not None
    assert DEMOTED_TO is min(AutonomyTier)
    assert (
        may_raise(
            was=AutonomyTier.AUTONOMOUS,
            proposed=DEMOTED_TO,
            evidence=None,
            effect=SideEffect.MONEY,
        )
        is True
    )


def test_a_circuit_break_with_no_metric_is_refused_at_construction() -> None:
    """A rung that fell for no reason anybody can show is a rung that goes straight back up.

    Delete this and a demotion can be recorded with an empty metric, which renders as a blank
    space beside a number nobody can interpret."""
    with pytest.raises(LeashError):
        CircuitBreak(metric="   ", measured=0.4, threshold=0.9, at=NOW)


# ======================================================= M39.3.2.4 money and irreversibility
@pytest.mark.parametrize("effect", sorted(IRREVERSIBLE), ids=lambda one: str(one.value))
def test_a_rung_over_an_irreversible_target_does_not_rise_on_one_signature(
    effect: SideEffect,
) -> None:
    """Money moves and a sent message cannot be recalled, so the rung over either needs two
    people rather than one.

    Both members asserted rather than only money, because the message that has left the
    building is the one people forget is irreversible.

    Delete this and an agent is trusted to send on the strength of one approval."""
    one_signature = PromotionEvidence(
        clean_runs=MINIMUM_CLEAN_RUNS, agreement_rate=1.0, approver_id=STEWARD
    )
    two_signatures = PromotionEvidence(
        clean_runs=MINIMUM_CLEAN_RUNS,
        agreement_rate=1.0,
        approver_id=STEWARD,
        second_approver_id=COLLEAGUE,
    )

    assert (
        may_raise(
            was=AutonomyTier.SHADOW,
            proposed=AutonomyTier.ASSISTED,
            evidence=one_signature,
            effect=effect,
        )
        is False
    )
    assert (
        may_raise(
            was=AutonomyTier.SHADOW,
            proposed=AutonomyTier.ASSISTED,
            evidence=two_signatures,
            effect=effect,
        )
        is True
    )


def test_a_reversible_target_still_rises_on_one_signature() -> None:
    """The other side of the boundary, so the second approver is a rule about irreversibility
    rather than about promotion in general.

    Delete this and requiring two approvers everywhere passes the test above, and the console
    asks for a second signature to let an agent read a ticket."""
    evidence = PromotionEvidence(
        clean_runs=MINIMUM_CLEAN_RUNS, agreement_rate=1.0, approver_id=STEWARD
    )

    for effect in (SideEffect.NONE, SideEffect.DRAFT, SideEffect.WRITE):
        assert (
            may_raise(
                was=AutonomyTier.SHADOW,
                proposed=AutonomyTier.ASSISTED,
                evidence=evidence,
                effect=effect,
            )
            is True
        )


def test_one_person_cannot_stand_for_both_approvers() -> None:
    """A second signature that is the first signature is one signature written twice, and the
    boundary then has one person behind it.

    Delete this and the two-approver rule is satisfied by typing the same name in both
    boxes."""
    with pytest.raises(LeashError):
        PromotionEvidence(
            clean_runs=MINIMUM_CLEAN_RUNS,
            agreement_rate=1.0,
            approver_id=STEWARD,
            second_approver_id=STEWARD,
        )


def test_the_effects_needing_two_approvers_are_the_ones_at_or_above_send() -> None:
    """`IRREVERSIBLE` is written out rather than derived, so this comparison is against
    `brain.gate.catalogue.SIDE_EFFECT_ORDER` and not against itself.

    Delete this and the set can be narrowed to money alone, and sending stops needing a second
    person with every other test in this file still green."""
    from_order = frozenset(SIDE_EFFECT_ORDER[SIDE_EFFECT_ORDER.index(SideEffect.SEND) :])

    assert from_order == IRREVERSIBLE
    assert SideEffect.WRITE not in IRREVERSIBLE


# ==================================================================== M39.3.2.5 the history
def test_every_move_appears_in_order_with_the_evidence_that_caused_it() -> None:
    """A history is read forwards, because a demotion is read against whatever raised the rung
    in the first place.

    The evidence stays attached rather than being summarised into the row: a promotion keeps
    its approver and a demotion keeps its metric, which is what makes the history answer the
    question anybody actually asks of it.

    Delete this and the history becomes a list of rung values with dates, which says that
    something changed and never why."""
    rose = RungChange(
        at=NOW - timedelta(days=2),
        entity="client",
        operation=Operation.DRAFT,
        was=AutonomyTier.SHADOW,
        became=AutonomyTier.ASSISTED,
        evidence=PromotionEvidence(
            clean_runs=MINIMUM_CLEAN_RUNS, agreement_rate=1.0, approver_id=STEWARD
        ),
    )
    fell = RungChange(
        at=NOW,
        entity="client",
        operation=Operation.DRAFT,
        was=AutonomyTier.ASSISTED,
        became=AutonomyTier.SHADOW,
        evidence=CircuitBreak(metric="agreement_rate", measured=0.3, threshold=0.9, at=NOW),
    )

    history = rung_history([fell, rose])

    assert history == (rose, fell)
    assert history[0].is_promotion is True
    assert isinstance(history[0].evidence, PromotionEvidence)
    assert history[0].evidence.approver_id == STEWARD
    assert isinstance(history[1].evidence, CircuitBreak)
    assert history[1].evidence.metric == "agreement_rate"


def test_a_rise_recorded_against_a_circuit_break_is_refused_and_so_is_the_reverse() -> None:
    """A history saying somebody was trusted further for having failed is worse than no
    history, and a demotion with promotion evidence attached shows no metric for a rung that
    dropped.

    Delete this and the two evidence kinds become interchangeable, and the history stops being
    readable in either direction."""
    good = PromotionEvidence(clean_runs=MINIMUM_CLEAN_RUNS, agreement_rate=1.0, approver_id=STEWARD)
    tripped = CircuitBreak(metric="errors", measured=9.0, threshold=1.0, at=NOW)

    with pytest.raises(LeashError):
        RungChange(
            at=NOW,
            entity="client",
            operation=Operation.WRITE,
            was=AutonomyTier.SHADOW,
            became=AutonomyTier.AUTONOMOUS,
            evidence=tripped,
        )
    with pytest.raises(LeashError):
        RungChange(
            at=NOW,
            entity="client",
            operation=Operation.WRITE,
            was=AutonomyTier.AUTONOMOUS,
            became=AutonomyTier.SHADOW,
            evidence=good,
        )


# ================================================================== M39.4.1.1 readable text
def test_a_memory_the_reader_reaches_is_shown_in_its_own_words() -> None:
    """**The positive case, and the leaf itself.** A viewer whose whole point is that memory
    is not an opaque store has to actually render the sentence.

    The verdict is the real `may_recall`, computed inside `readable`, and it travels on the
    value so a renderer holding the text is holding the reason it may show it.

    Delete this and a viewer that shows nobody anything passes every refusal below."""
    said = "Prefers the summary before the detail."
    text = readable(learning("m_1"), said, holder(CLIENT_CAP, scope=IN_WEB), now=NOW)

    assert text is not None
    assert text.statement == said
    assert text.seen.confidence > 0
    assert text.provenance is Provenance.EXTRACTED


def test_a_memory_the_reader_does_not_reach_produces_nothing_and_reports_nothing() -> None:
    """None is the whole answer. Nothing here says a statement was withheld, because "there is
    something I know and will not say" is a fact about what exists.

    Two refusals, and they are different: the wrong capability, and the right capability in the
    wrong department. The second is the one a viewer scoped by principal rather than by place
    would let through.

    Delete this and a viewer shows one person what another person's conversation produced."""
    assert readable(learning("m_1"), "Anything.", holder(TICKET_CAP, scope=IN_WEB), now=NOW) is None
    assert (
        readable(learning("m_1"), "Anything.", holder(CLIENT_CAP, scope=IN_FINANCE), now=NOW)
        is None
    )


def test_a_blank_statement_is_refused_rather_than_rendered_as_an_empty_row() -> None:
    """An empty row in a viewer built to show memory as text is the opaque store with a
    heading on it.

    Delete this and the viewer renders blanks for memories whose text was never stored, and
    nobody can tell those from memories that say nothing."""
    with pytest.raises(MemoryViewError):
        readable(learning("m_1"), "   ", holder(CLIENT_CAP, scope=IN_WEB), now=NOW)


def test_the_viewer_will_not_accept_a_recall_verdict_somebody_else_reached() -> None:
    """`readable` takes an `EntitlementSet` and computes the verdict. It does not take a
    `Recollection`, because a signature taking one can be handed a verdict reached elsewhere,
    and the caller that reaches it wrongly is the surface, every time.

    Delete this and a convenience overload appears that accepts a recollection, and the
    permission decision moves to whoever calls it."""
    annotations = {
        name: str(one.annotation) for name, one in inspect.signature(readable).parameters.items()
    }

    assert "reader" in annotations
    assert not any("Recollection" in one for one in annotations.values())


# ====================================================== M39.4.1.2 curated against extracted
def test_curated_and_extracted_memory_are_two_lists_and_never_one() -> None:
    """The split is the leaf. What somebody stated and what the system worked out carry
    different weight, and a single list sorted by confidence puts a fresh guess above a
    standing statement.

    Delete this and the two are merged for tidiness, and a guess is read as a statement."""
    stated = learning("m_said", kind=MemoryKind.PERSISTENT)
    worked_out = learning("m_guessed", kind=MemoryKind.ADAPTIVE)
    view = split_memory(
        [(stated, "Invoices go out on the first."), (worked_out, "Prefers short answers.")],
        holder(CLIENT_CAP, scope=IN_WEB),
        now=NOW,
    )

    assert [one.memory_id for one in view.curated] == ["m_said"]
    assert [one.memory_id for one in view.extracted] == ["m_guessed"]


def test_a_session_memory_is_refused_rather_than_quietly_called_curated() -> None:
    """A session memory lives in a cache keyed by thread and dies with the conversation, so
    there is nothing for a viewer to show and nothing anybody could go back to.

    Folding it into either column would present a conversation's working as though somebody
    had stated it, which is the one thing the curated column must not contain.

    Delete this and an unpromoted session memory appears in the viewer under whichever
    heading the mapping happened to default to."""
    with pytest.raises(MemoryViewError):
        provenance_of(MemoryKind.SESSION)
    assert provenance_of(MemoryKind.PERSISTENT) is Provenance.CURATED
    assert provenance_of(MemoryKind.ADAPTIVE) is Provenance.EXTRACTED


def test_the_split_says_nothing_about_the_memories_the_reader_could_not_see() -> None:
    """One memory in, none visible, and the view is two empty tuples with no field anywhere
    that could hold how many were dropped.

    Delete this and a total appears at the top of a page of rows, which beside a filtered
    listing is the number of things this reader may not see."""
    view = split_memory([(learning("m_1"), "Anything.")], holder(TICKET_CAP, scope=IN_WEB), now=NOW)
    names = {one.name for one in dataclass_fields(type(view))}

    assert view.curated == ()
    assert view.extracted == ()
    assert names.isdisjoint({"count", "total", "hidden", "withheld", "more"})


# ======================================================= M39.4.1.3 revisions and their diffs
def test_a_revision_shows_what_changed_and_what_prompted_the_change() -> None:
    """The positive case for the leaf: a diff per revision and the trigger that caused it.

    The trigger comes off the `Supersession` rather than out of the two statements, because a
    viewer that inferred why something changed by comparing text would be a classifier
    deciding what a correction meant.

    Delete this and the history becomes two statements side by side with no reason between
    them."""
    old = learning("m_old", at=NOW - timedelta(days=3))
    new = learning("m_new", at=NOW, replaced_id="m_old")
    seen = revisions(
        [(old, "Invoices go out on the first."), (new, "Invoices go out on the fifth.")],
        holder(CLIENT_CAP, scope=IN_WEB),
        now=NOW,
        supersessions=(
            Supersession(
                superseded_id="m_old",
                by_id="m_new",
                prompted_by=Signal.CONTRADICTED,
                at=NOW,
            ),
        ),
    )

    assert [one.memory_id for one in seen] == ["m_old", "m_new"]
    assert seen[1].trigger is Signal.CONTRADICTED
    assert seen[1].correction is Correction.SUPERSEDED
    assert any(line.startswith("-") for line in seen[1].diff)
    assert any(line.startswith("+") for line in seen[1].diff)
    assert seen[0].diff == ()


def test_a_reader_admitted_to_one_side_of_a_revision_is_shown_no_diff_and_no_note() -> None:
    """**The sharpest edge on this surface.** A diff renders both statements, and the older
    one was formed under its own tags, which may be wider than the newer one's.

    Here the older memory was formed in finance and the newer in web, and the reader reaches
    web only. They get the revision and no diff, and nothing on the value says a revision was
    withheld: that note is the count with the number left off.

    Delete this and the memory viewer shows one department's statements to another through the
    change history, which is the one place nobody looks."""
    old = learning("m_old", at=NOW - timedelta(days=3), scope=IN_FINANCE)
    new = learning("m_new", at=NOW, scope=IN_WEB, replaced_id="m_old")
    seen = revisions(
        [(old, "Finance says the fifteenth."), (new, "Web says the fifth.")],
        holder(CLIENT_CAP, scope=IN_WEB),
        now=NOW,
    )

    assert [one.memory_id for one in seen] == ["m_new"]
    assert seen[0].diff == ()
    assert seen[0].replaced_id == "m_old"


def test_a_demoted_memory_carries_its_correction_and_no_diff_it_did_not_earn() -> None:
    """The other correction kind. A demotion replaces nothing, so there is no previous
    statement and no diff, and the row still says which correction was written.

    `Correction` has two members and no third, so the one thing this can never say is that
    something was removed.

    Delete this and a demotion is indistinguishable from a memory nothing has happened to."""
    demoted = learning("m_1")
    seen = revisions(
        [(demoted, "Renewal is in March.")],
        holder(CLIENT_CAP, scope=IN_WEB),
        now=NOW,
        demotions=(Demotion(memory_id="m_1", field="client.renewal_date", at=NOW),),
    )

    assert seen[0].correction is Correction.DEMOTED
    assert seen[0].trigger is None
    assert seen[0].diff == ()


# ===================================================== M39.4.1.5 per agent and per person
def test_a_learning_that_is_both_the_agents_and_the_persons_appears_in_both_lists() -> None:
    """Neither hides the other, read literally. Assigning a learning to whichever list was
    built first makes one of the two incomplete, and the reader has no way to tell which.

    Delete this and the per-person list quietly loses everything that happened while an agent
    was running, which is most of it."""
    mine = learning("m_mine", writer=COLLEAGUE, agent_id=DESK)
    view = separate_memory(
        now=NOW,
        caller=holder(CLIENT_CAP, scope=IN_WEB),
        record=record(reach=authority(CLIENT_CAP)),
        subject_id=COLLEAGUE,
        learnings=[mine],
    )

    assert [one.memory_id for one in view.per_agent] == ["m_mine"]
    assert [one.memory_id for one in view.per_person] == ["m_mine"]


def test_the_per_agent_list_is_read_at_the_run_reach_and_not_at_the_callers_own() -> None:
    """An agent is a lens. A tab showing what the agent knows rather than what this caller may
    be told is the one place the lens would stop applying.

    The caller reaches the memory on their own grants; the agent's ceiling does not cover the
    capability it was formed under, so the memory is absent from the agent's list and present
    on the person's, which is exactly the difference between the two questions.

    Delete this and the agent tab widens to the caller's whole reach, and an agent's memory
    tab starts showing memories that agent never formed."""
    formed_on_tickets = learning("m_1", capability=TICKET_CAP, writer=COLLEAGUE)
    view = separate_memory(
        now=NOW,
        caller=holder(TICKET_CAP, scope=IN_WEB),
        record=record(reach=authority(CLIENT_CAP)),
        subject_id=COLLEAGUE,
        learnings=[formed_on_tickets],
    )

    assert view.per_agent == ()
    assert [one.memory_id for one in view.per_person] == ["m_1"]


def test_a_memory_from_somebody_elses_conversation_is_in_neither_list() -> None:
    """Both sides go through `may_recall`, so the split is not a way around the entitlement
    check: a memory formed under a capability this caller does not reach is absent from both.

    Delete this and the per-person list becomes a way of reading colleagues' conversations by
    naming them as the subject."""
    theirs = learning("m_1", capability=TICKET_CAP, writer=STRANGER, agent_id=DESK)
    view = separate_memory(
        now=NOW,
        caller=holder(CLIENT_CAP, scope=IN_WEB),
        record=record(reach=authority(CLIENT_CAP, TICKET_CAP)),
        subject_id=STRANGER,
        learnings=[theirs],
    )

    assert view.per_agent == ()
    assert view.per_person == ()


# ============================================================ M39.4.2.1 which tiers are active
def test_the_declared_tiers_are_what_this_agent_learns_at() -> None:
    """The positive case. A state that reported nothing active would pass both refusals
    below and would be a screen that says learning is off when it is on.

    Delete this and `active_tiers` can return nothing for everybody."""
    from brain.console.reach_view import LearningState

    state = LearningState(agent_id=DESK, declared=frozenset({Tier.AUTOMATIC, Tier.PROMOTED}))

    assert active_tiers(state) == (Tier.AUTOMATIC, Tier.PROMOTED)


def test_tier_three_is_never_reported_as_active_however_it_is_declared() -> None:
    """A gated change waits for a person and nothing in this system can approve one, so an
    agent is never learning at tier three. Reporting it as active would tell a reader the
    agent widens access by itself.

    Delete this and the console says an agent learns at the tier that changes who may see
    what."""
    from brain.console.reach_view import LearningState

    state = LearningState(agent_id=DESK, declared=frozenset(Tier))

    assert Tier.GATED not in active_tiers(state)
    assert active_tiers(state) == (Tier.SESSION, Tier.AUTOMATIC, Tier.PROMOTED)


def test_a_frozen_agent_is_learning_at_nothing_at_all() -> None:
    """The whole of what the freeze does, asserted on the answer rather than on the flag.

    Delete this and a freeze becomes a label on a screen while the tiers stay active."""
    from brain.console.reach_view import LearningState

    state = LearningState(agent_id=DESK, declared=frozenset({Tier.AUTOMATIC, Tier.PROMOTED}))

    assert active_tiers(freeze(state, at=NOW, by=STEWARD)) == ()


# ================================================================= M39.4.2.2 tier one and undo
def test_a_tier_one_row_carries_an_undo_and_has_nowhere_to_record_an_approval() -> None:
    """A tier-one change has already taken effect, so asking somebody to approve it is asking
    about a decision that was made by not needing one.

    The control writes a mark rather than a removal: `Correction` has two members and
    `brain.memory.correction` argues there is no third.

    Delete this and an approval queue grows on the automatic tier, which is the queue nobody
    works and which then holds up the changes that are already live."""
    rows = tier_one_rows([learning("m_1", Change.PREFERENCE)], agent_id=DESK)
    names = {one.name for one in dataclass_fields(TierOneRow)}

    assert [one.memory_id for one in rows] == ["m_1"]
    assert rows[0].control_writes is Correction.DEMOTED
    assert names.isdisjoint({"approver", "approved_at", "approval", "decision", "queue"})


def test_only_automatic_changes_appear_in_the_tier_one_list() -> None:
    """A tier-two proposal has not taken effect and a tier-three one is waiting for a person.
    Putting either beside a one-click undo offers to undo something that never happened.

    Delete this and the undo control appears beside a scope widening, which is a person
    deciding a gated change by pressing something that says undo."""
    rows = tier_one_rows(
        [
            learning("m_auto", Change.PREFERENCE),
            learning("m_rule", Change.FAST_PATH_RULE),
            learning("m_gated", Change.COMPANY_KNOWLEDGE),
        ],
        agent_id=DESK,
    )

    assert [one.memory_id for one in rows] == ["m_auto"]


def test_a_tier_one_row_offers_to_restore_what_it_replaced_when_there_is_one() -> None:
    """The other branch of the control, which is `brain.memory.digest.undo`'s own rule read
    off the same field rather than decided again.

    Delete this and every undo writes a demotion, so undoing a memory that replaced an earlier
    one loses the earlier one as well."""
    rows = tier_one_rows([learning("m_new", Change.PREFERENCE, replaced_id="m_old")], agent_id=DESK)

    assert rows[0].control_writes is Correction.SUPERSEDED


def test_the_row_predicts_what_the_real_undo_control_would_actually_write() -> None:
    """**The loop closed.** `control_writes` is a promise about what pressing the control
    does, and the control is `brain.memory.review.delete`, which is `digest.undo` under the
    name the surface calls it. A promise nothing checks is a label.

    Both branches, driven through the real `delete`, so the row and the mark cannot drift:
    a learning that replaced something is restored, and one that replaced nothing is demoted.
    Each side is pinned against a literal rather than against the other, so this is not the
    row and the mark agreeing with themselves.

    Delete this and the row can say one thing while the button writes another, and the
    difference is invisible until somebody presses it."""
    from brain.memory.review import delete

    replaced = learning("m_new", Change.PREFERENCE, replaced_id="m_old")
    fresh = learning("m_only", Change.PREFERENCE)

    assert tier_one_rows([replaced], agent_id=DESK)[0].control_writes is Correction.SUPERSEDED
    assert isinstance(delete(replaced, at=NOW).correction, Supersession)
    assert tier_one_rows([fresh], agent_id=DESK)[0].control_writes is Correction.DEMOTED
    assert isinstance(delete(fresh, at=NOW).correction, Demotion)


# ================================================== M39.4.2.3 tier two, evidence and promotion
def test_a_tier_two_rule_is_promotable_only_once_independent_conversations_agree() -> None:
    """Both directions, driven through the real `brain.memory.tiers.may_promote`, so the
    counting rule stays in one place and this surface only carries the verdict across.

    Three separate conversations promote; three repetitions of one do not, which is the whole
    of what independent means and the reason the count is not done here.

    Delete this and the promote control lights up on one person having a bad afternoon."""
    rule = learning("m_rule", Change.FAST_PATH_RULE)
    separate = [
        Occurrence(conversation_id=f"c_{n}", on=NOW - timedelta(days=n))
        for n in range(PROMOTION_AGREEMENT)
    ]
    one_conversation = [
        Occurrence(conversation_id="c_same", on=NOW - timedelta(days=n))
        for n in range(PROMOTION_AGREEMENT)
    ]

    ready = tier_two_rows([rule], agent_id=DESK, occurrences={"m_rule": separate}, now=NOW)
    not_ready = tier_two_rows(
        [rule], agent_id=DESK, occurrences={"m_rule": one_conversation}, now=NOW
    )

    assert ready[0].promote_ready is True
    assert not_ready[0].promote_ready is False


def test_a_rule_with_no_recorded_agreement_is_not_promotable_by_default() -> None:
    """A missing lookup must not read as consensus. The control is dark when nothing has been
    counted, which is the correct default for a rule nobody has seen twice.

    Delete this and an absent occurrences map lights up every promote control on the page."""
    rows = tier_two_rows([learning("m_rule", Change.FAST_PATH_RULE)], agent_id=DESK, now=NOW)

    assert rows[0].promote_ready is False
    assert rows[0].evidence == (Signal.REASKED,)


def test_a_tier_two_row_carries_no_conversation_it_was_learnt_from() -> None:
    """Evidence names what was noticed and never whose conversation it was. A row listing
    occurrences would tell an administrator which conversations produced a rule, which is a
    note about who the system learns from.

    Delete this and the occurrences travel to the screen as the obvious way to show the
    evidence, and the count arrives with them."""
    names = {one.name for one in dataclass_fields(TierTwoRow)}

    assert names.isdisjoint(
        {"occurrences", "conversations", "conversation_id", "principal_id", "count"}
    )


# ========================================================== M39.4.2.4 tier three and the queue
def test_a_gated_change_is_routed_to_its_own_department_with_a_way_back() -> None:
    """The leaf: routed to the department queue, and carrying the link back to the agent it
    came from so that the person reviewing it can see what asked.

    A key rather than a URL, so this module holds no opinion about how the console is
    addressed.

    Delete this and gated changes arrive in a queue with no way back to the agent, which makes
    them unreviewable in practice and approved on trust."""
    routed = tier_three_routing(
        [learning("m_1", Change.SCOPE_WIDENING, scope=IN_WEB)], agent_id=DESK
    )

    assert len(routed) == 1
    assert routed[0].department == WEB
    assert routed[0].back_to == BACK_LINK.format(agent_id=DESK)
    assert DESK in routed[0].back_to


def test_only_gated_changes_are_routed_to_a_department_queue() -> None:
    """Tier one has happened and tier two is waiting on agreement. Routing either to the queue
    buries the decisions that need a person under the ones that do not.

    Delete this and the tier-three queue fills with preferences, and the alarm that says it is
    not being worked through starts firing about nothing."""
    routed = tier_three_routing(
        [
            learning("m_pref", Change.PREFERENCE),
            learning("m_rule", Change.FAST_PATH_RULE),
            learning("m_gated", Change.LEASH_INCREASE),
        ],
        agent_id=DESK,
    )

    assert [one.memory_id for one in routed] == ["m_gated"]


def test_a_gated_change_naming_no_department_is_refused_rather_than_sent_to_everybody() -> None:
    """The only queue left for an unscoped change is everybody's, and a scope widening in
    everybody's queue is a scope widening nobody owns.

    Delete this and unscoped gated changes land in a default queue, which is the queue that
    exists because nobody chose it."""
    with pytest.raises(MemoryViewError):
        tier_three_routing(
            [learning("m_1", Change.CAPABILITY_ADDITION, scope=Scope.unrestricted())],
            agent_id=DESK,
        )


# ==================================================================== M39.4.2.5 the freeze
def test_one_control_stops_every_tier_and_takes_no_exception() -> None:
    """The value of a single control is that the person pressing it does not have to know
    which tiers matter at the moment they are least able to work it out.

    Both halves: the signature has no tier parameter, and the answer is that nothing is
    active. The signature half is what holds for an implementation nobody has written yet.

    Delete this and the freeze grows a "keep tier one" option, which is a decision made under
    exactly the conditions that make it wrong."""
    from brain.console.reach_view import LearningState

    taken = set(inspect.signature(freeze).parameters)
    state = LearningState(agent_id=DESK, declared=frozenset(Tier))

    assert taken.isdisjoint({"tier", "tiers", "only", "except_", "keep"})
    assert active_tiers(freeze(state, at=NOW, by=STEWARD)) == ()


def test_starting_learning_again_takes_a_stated_reason_at_the_halt_modules_own_minimum() -> None:
    """Stopping is free and restarting is the act that carries the risk, which is
    `brain.ops.halt`'s rule, and the minimum is imported from there rather than restated: two
    minimums for the same kind of sentence is one of them being shorter, and the shorter one
    is the one somebody uses during an incident.

    Delete this and "ok" resumes learning on an agent that was frozen for a reason nobody
    recorded."""
    from brain.console.reach_view import LearningState

    frozen = freeze(
        LearningState(agent_id=DESK, declared=frozenset({Tier.AUTOMATIC})),
        at=NOW,
        by=STEWARD,
    )

    with pytest.raises(LeashError):
        thaw(frozen, by=STEWARD, reason="x" * (MINIMUM_REASON - 1))
    assert thaw(frozen, by=STEWARD, reason="y" * MINIMUM_REASON).is_frozen is False


def test_a_freeze_keeps_the_declaration_so_a_thawed_agent_learns_what_it_did() -> None:
    """The freeze is recorded beside the declaration rather than by emptying it. An agent
    thawed after a freeze that had emptied it would come back learning at nothing, which looks
    exactly like the freeze having worked.

    Delete this and an incident permanently switches off learning on every agent it touched,
    and nobody notices for a month."""
    from brain.console.reach_view import LearningState

    declared = frozenset({Tier.AUTOMATIC, Tier.PROMOTED})
    state = LearningState(agent_id=DESK, declared=declared)
    again = thaw(freeze(state, at=NOW, by=STEWARD), by=STEWARD, reason="the source was fixed")

    assert again.declared == declared
    assert active_tiers(again) == (Tier.AUTOMATIC, Tier.PROMOTED)


def test_a_second_freeze_does_not_move_the_time_learning_actually_stopped() -> None:
    """When learning stopped is the question asked afterwards, and a second press that moved
    the timestamp would answer it with the time somebody last pressed the button.

    Delete this and the record says an agent stopped learning at the moment the second
    administrator arrived."""
    from brain.console.reach_view import LearningState

    first = freeze(
        LearningState(agent_id=DESK, declared=frozenset({Tier.AUTOMATIC})), at=NOW, by=STEWARD
    )
    second = freeze(first, at=NOW + timedelta(hours=3), by=COLLEAGUE)

    assert second.frozen_at == NOW
    assert second.frozen_by == STEWARD


def test_a_freeze_by_nobody_is_refused() -> None:
    """A freeze leaves an agent not learning, which somebody has to answer for later.

    Delete this and an anonymous freeze is indistinguishable from a configuration error."""
    from brain.console.reach_view import LearningState

    with pytest.raises(LeashError):
        freeze(LearningState(agent_id=DESK, declared=frozenset({Tier.AUTOMATIC})), at=NOW, by=" ")
