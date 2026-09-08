"""Six per-agent views widened to the estate, held to what the widening may show.

Every test hands over rows the owning module produced and asks what a governance screen may
put in front of one reader. Nothing here recomputes a rung, a diff, a promotion verdict or a
retention horizon, because a fixture that rebuilt one would be testing this file rather than
the decision.

Six leaves are claimed and each is a widening decision rather than a page. A leash matrix and
a rung history are assembled from the agents a reader may already see, and the approver on a
promotion follows the People screen's grant so that a withheld name and a demotion are one
empty string (M27.3.12). The skill queue and its summary come back from one call over one
narrowed list, because two correct functions over two different lists publish the difference
(M27.3.13). A library row carries the level and never the predicate, and the grouping by
department is withheld on the narrower basis rather than shown short (M27.3.14). The three
learning tiers are three tuples, tier three is withheld on the narrower basis because it is
the only one that names a department, and there is no bulk undo (M27.3.15). An estate artifact
listing is assembled per agent and keeps the reader's own output when its agent is not visible
(M27.3.16). A memory viewer requires a subject and there is no value meaning everybody
(M27.3.17).

Real `LeashMatrix`es built by the real `leash_matrix` over a real `Leash`, real
`ImportedSkill`s through `brain.tools.review.pending`, real `Learning`s through the real
`propose` and `Formation`, and real `Artifact`s. `brain.console.workspace.Basis` is used
throughout rather than a boolean, because that enum is the existing rule and a second one is
what these tests exist to refuse.

Task ids: M27.3.12, M27.3.13, M27.3.14
Task ids: M27.3.15, M27.3.16, M27.3.17
"""

from __future__ import annotations

import re
from dataclasses import fields, make_dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from brain.console import govern_estate as estate_module
from brain.console.agent_output import Artifact, ArtifactKind, basis_over
from brain.console.govern import Placed
from brain.console.govern_estate import (
    DEPARTMENT_SPAN_SCREEN,
    ESTATE_COUNT,
    NAMES_THAT_WOULD_ASK_FOR_EVERYBODY,
    NAMES_THAT_WOULD_BE_A_BULK_CONTROL,
    NAMES_THAT_WOULD_BE_A_PREDICATE,
    PROMOTION_APPROVER_SCREEN,
    EstateError,
    LearningReview,
    LibraryItem,
    LibraryRow,
    approver_of,
    artifact_estate,
    departments_represented,
    estate_gaps,
    learning_review,
    leash_estate,
    library_rows,
    rung_estate,
    skill_queue,
    spans_departments,
    subject_memory,
)
from brain.console.reach_view import (
    CircuitBreak,
    Operation,
    PromotionEvidence,
    RungChange,
    TierOneRow,
    TierThreeRouting,
    TierTwoRow,
    leash_matrix,
)
from brain.console.reads import Plane, plane_capability
from brain.console.screens import screen
from brain.console.workspace import Basis
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Clause, Op, Scope
from brain.gate.injection import AutonomyTier
from brain.gate.leash import Leash, LeashEntry
from brain.knowledge.visibility import KnowledgeVisibility, Visibility
from brain.memory.correction import Correction
from brain.memory.digest import Learning
from brain.memory.formation import Formation, MemoryKind
from brain.memory.signals import Signal
from brain.memory.tiers import Change, propose
from brain.ops.retention import DataClass
from brain.tools.review import pending
from brain.tools.skills import ImportedSkill, Skill, SkillSource, SourceKind

#: A fixed moment, so an expiry test cannot pass because the machine's clock happened to sit
#: on the convenient side of a boundary. Everything below is built relative to it.
NOW = datetime(2027, 5, 4, 10, 0, tzinfo=UTC)

#: Two departments, so a scoped reader has somewhere to be refused.
MAINTENANCE = "maintenance"
FINANCE = "finance"

#: Two agents, one of them outside the reader's audience in every test that varies it.
DESK = "agent_desk"
FINANCE_AGENT = "agent_ledger"

#: The `Task ids:` lines of the module under test, read rather than restated.
TASK_LINE_RE = re.compile(r"^\s*Task ids:\s*(.+)$", re.M)
TASK_ID_RE = re.compile(r"\bM\d+(?:\.\d+){2,4}\b")


def holding(
    *capabilities: str,
    planes: tuple[Plane, ...] = (Plane.CONTENT,),
    scope: Scope | None = None,
    principal_id: str = "u_reader",
) -> EntitlementSet:
    """A reader holding these capabilities in one scope, plus the plane grants named.

    The content plane by default, because three of the six screens here show it and a reader
    short of it would be refused for a reason none of these tests is about.
    """
    where = scope if scope is not None else Scope(clauses=())
    grants = [Grant(capability=Capability(value=one), scope=where) for one in capabilities]
    grants += [Grant(capability=plane_capability(one), scope=where) for one in planes]
    return EntitlementSet(principal_id=principal_id, grants=tuple(grants))


def in_department(name: str) -> Scope:
    """A scope naming one department, which the rows below either match or do not."""
    return Scope(clauses=(Clause(field="department", op=Op.EQ, value=name),))


def a_leash(agent_id: str) -> Leash:
    """One real leash with one entry, so a matrix has something configured to find."""
    return Leash(
        entries=(
            LeashEntry(
                agent_id=agent_id,
                target="client.read",
                scope=Scope(clauses=()),
                rung=AutonomyTier.AUTONOMOUS,
            ),
        )
    )


def a_matrix(agent_id: str) -> object:
    """One real matrix, through the real `brain.console.reach_view.leash_matrix`.

    Built rather than constructed, so a cell here is one that function actually looked up and
    a test cannot be satisfied by a matrix it would never have produced.
    """
    return leash_matrix(a_leash(agent_id), agent_id, entities=("client",))


def a_promotion_change(entity: str = "client") -> RungChange:
    """One rung rise, with the evidence that moved it and the person who approved it."""
    return RungChange(
        at=NOW - timedelta(days=2),
        entity=entity,
        operation=Operation.READ,
        was=AutonomyTier.SHADOW,
        became=AutonomyTier.AUTONOMOUS,
        evidence=PromotionEvidence(clean_runs=20, agreement_rate=0.95, approver_id="u_head"),
    )


def a_demotion_change(entity: str = "client") -> RungChange:
    """One rung fall, with the metric that tripped it and no person on it at all."""
    return RungChange(
        at=NOW - timedelta(days=1),
        entity=entity,
        operation=Operation.READ,
        was=AutonomyTier.AUTONOMOUS,
        became=AutonomyTier.SHADOW,
        evidence=CircuitBreak(
            metric="agreement_rate", measured=0.4, threshold=0.9, at=NOW - timedelta(days=1)
        ),
    )


def a_waiting_skill(name: str) -> ImportedSkill:
    """One skill that has arrived and nobody has read yet."""
    return ImportedSkill(
        skill=Skill(
            name=name,
            description="a procedure a test wrote so the queue has something real in it",
            version="1.0.0",
            body="Look the client up, then open a ticket.",
        ),
        source=SkillSource(kind=SourceKind.UPLOAD, location=f"{name}.zip", content_digest="a" * 64),
    )


def a_library_item(item_id: str, *, department: str) -> Placed[LibraryItem]:
    """One knowledge item at department visibility, placed in the department it belongs to."""
    return Placed(
        record=LibraryItem(
            item_id=item_id,
            visibility=KnowledgeVisibility.of_department(department, owner_id="u_author"),
        ),
        where={"department": department},
    )


def an_artifact(artifact_id: str, *, agent_id: str, caller: str) -> Artifact:
    """One real artifact, through `Artifact`'s own validators."""
    return Artifact(
        artifact_id=artifact_id,
        agent_id=agent_id,
        kind=ArtifactKind.REPORT,
        run_id=f"run_{artifact_id}",
        agent_version="4.2.0",
        caller_id=caller,
        entitlement_hash=holding("read:client.name", principal_id=caller).ent_hash(),
        at=NOW - timedelta(hours=1),
        data_class=DataClass.BUSINESS_RECORD,
        bytes_stored=100,
    )


def a_learning(
    memory_id: str,
    *,
    subject_principal: str,
    replaced_id: str | None = None,
    at: datetime = NOW,
) -> Learning:
    """One real learning, formed by one principal, through the real `propose` and `Formation`."""
    return Learning(
        memory_id=memory_id,
        proposal=propose(Change.PREFERENCE, subject=f"subject:{memory_id}"),
        formation=Formation(
            principal_id=subject_principal,
            capabilities=(Capability(value="read:client.name"),),
            scope=Scope(clauses=()),
            ent_hash="0" * 32,
            formed_at=at,
            kind=MemoryKind.ADAPTIVE,
        ),
        evidence=frozenset({Signal.REASKED}),
        agent_id=DESK,
        replaced_id=replaced_id,
    )


def a_tier_one(memory_id: str) -> TierOneRow:
    """One automatic change with the control that undoes it."""
    return TierOneRow(
        memory_id=memory_id,
        change=Change.PREFERENCE,
        control_writes=Correction.DEMOTED,
        learned_at=NOW,
    )


def a_tier_two(memory_id: str) -> TierTwoRow:
    """One proposed rule with its evidence kinds and no conversation on it."""
    return TierTwoRow(
        memory_id=memory_id,
        change=Change.PROCEDURAL_SHORTCUT,
        evidence=(Signal.REASKED,),
        promote_ready=False,
        learned_at=NOW,
    )


def a_tier_three(memory_id: str, *, department: str) -> TierThreeRouting:
    """One gated change, routed to the department its scope named."""
    return TierThreeRouting(memory_id=memory_id, department=department, back_to="agent:x/learning")


# ------------------------------------------------------- the one span decision (M27.3.14)
def test_the_department_grouping_follows_the_scopes_screens_own_grant() -> None:
    """**The rule both cross-department leaves turn on.** Delete this and the grouping gets a
    capability of its own, invented from the rendering layer, and the administrator who
    reviews grants would never meet it. The screen that governs a listing of departments is
    the Scopes and departments screen, so that is the grant.

    The two readers differ only in whether they hold that screen's capability; both hold the
    Library screen's, so the rows they see are identical."""
    with_scopes = holding("read:document", screen(DEPARTMENT_SPAN_SCREEN).read.requires.value)
    without = holding("read:document")

    assert spans_departments(with_scopes, NOW) is Basis.EVERYONE
    assert spans_departments(without, NOW) is Basis.OWN


def test_the_span_decision_is_the_existing_rule_and_not_a_second_one() -> None:
    """Delete this and `spans_departments` can grow arithmetic of its own, which would be a
    second answer to a question `brain.console.workspace.Basis` already answers.

    Asserted against `brain.console.agent_output.basis_over` called with the same screen key,
    which is the general form of `basis_for`, so the two cannot come apart."""
    reader = holding("read:document", screen(DEPARTMENT_SPAN_SCREEN).read.requires.value)

    assert spans_departments(reader, NOW) is basis_over(DEPARTMENT_SPAN_SCREEN, reader, NOW)


# --------------------------------------------------- agents and leash state (M27.3.12)
def test_a_leash_matrix_for_an_agent_the_reader_cannot_see_is_absent() -> None:
    """Delete this and the estate view discloses an agent through its configuration, which is
    `brain.agents.model.A_HIDDEN_AGENT_AND_A_MISSING_AGENT_ARE_ONE_ANSWER` broken by a table.
    The two matrices differ only in which agent they belong to."""
    matrices = (a_matrix(DESK), a_matrix(FINANCE_AGENT))

    shown = leash_estate(matrices, visible={DESK})  # type: ignore[arg-type]

    assert tuple(one.agent_id for one in shown) == (DESK,)


def test_every_visible_agents_matrix_is_shown_with_its_cells_untouched() -> None:
    """The positive half, and the second assertion is the one that matters: delete it and an
    estate view can fill a blank cell from its neighbour, which puts the per-agent default
    back at the rendering layer where `brain.gate.leash` says it must not be.

    The leash configures `client.read` and nothing else, so the two other operations are the
    cells that would be filled in by a helpful edit."""
    shown = leash_estate((a_matrix(DESK),), visible={DESK, FINANCE_AGENT})  # type: ignore[arg-type]

    assert len(shown) == 1
    assert shown[0].rung("client", Operation.READ) is AutonomyTier.AUTONOMOUS
    assert shown[0].rung("client", Operation.WRITE) is AutonomyTier.SHADOW


def test_a_rung_history_for_an_agent_the_reader_cannot_see_is_absent() -> None:
    """Delete this and the promotion history becomes the roster: an agent with no matrix on
    the page still appears, named, because somebody moved its rung."""
    changes = {DESK: (a_promotion_change(),), FINANCE_AGENT: (a_demotion_change(),)}

    shown = rung_estate(changes, visible={DESK})

    assert tuple(agent_id for agent_id, _ in shown) == (DESK,)


def test_a_rung_history_keeps_the_ordering_of_the_module_that_owns_it() -> None:
    """Delete this and the estate view sorts the history itself, and a demotion ends up above
    the promotion it followed. `brain.console.reach_view.rung_history` orders oldest first
    because a reviewer works forwards, and this asserts that ordering rather than restating
    the reason.

    The two changes are two days and one day old, handed in newest first, so a function that
    kept the caller's order would fail here."""
    changes = {DESK: (a_demotion_change(), a_promotion_change())}

    shown = rung_estate(changes, visible={DESK})

    assert tuple(one.became for one in shown[0][1]) == (
        AutonomyTier.AUTONOMOUS,
        AutonomyTier.SHADOW,
    )


def test_an_agent_with_no_rung_change_has_no_heading_in_the_history() -> None:
    """Delete this and an agent that nobody has ever promoted appears with an empty history,
    which is a heading over nothing, and across an estate it is a list of every agent that
    exists rendered from a table about something else."""
    changes: dict[str, tuple[RungChange, ...]] = {DESK: (), FINANCE_AGENT: (a_promotion_change(),)}

    shown = rung_estate(changes, visible={DESK, FINANCE_AGENT})

    assert tuple(agent_id for agent_id, _ in shown) == (FINANCE_AGENT,)


def test_the_approver_of_a_promotion_needs_the_people_screens_own_grant() -> None:
    """Delete this and a column reading who trusted which agent further appears for anybody
    who can open the Agents screen, which is a fact about colleagues rather than about agents.

    The two readers differ only in whether they hold the People screen's capability, and the
    change handed to both is the same promotion."""
    change = a_promotion_change()
    may_name = holding("read:agent", screen(PROMOTION_APPROVER_SCREEN).read.requires.value)
    may_not = holding("read:agent")

    assert approver_of(change, may_name, NOW) == "u_head"
    assert approver_of(change, may_not, NOW) == ""


def test_a_demotion_and_a_withheld_approver_are_the_same_empty_string() -> None:
    """Delete this and a reader can tell a rung that fell from a rung that rose whose approver
    they may not be told about, which is the disclosure the withholding was for.

    `CircuitBreak` names a metric and no person, so there is nothing to withhold on a
    demotion, and the two answers have to be identical for that to stay true."""
    may_name = holding("read:agent", screen(PROMOTION_APPROVER_SCREEN).read.requires.value)

    assert approver_of(a_demotion_change(), may_name, NOW) == ""
    assert approver_of(a_promotion_change(), holding("read:agent"), NOW) == ""


# ------------------------------------------------------- skills and templates (M27.3.13)
def test_the_skill_queue_and_its_summary_count_the_same_list() -> None:
    """**The failure this leaf turns on**, and it is not a field somebody adds: it is two
    correct functions called over two different lists by a renderer doing the obvious thing.
    Delete this and the summary counts the whole queue while the list shows the reader's
    slice, and the difference is how many skills are waiting that they may not read.

    Two submissions in two departments and a reader scoped to one, so the two numbers can
    only agree if the summary was computed after the narrowing."""
    entries = pending((a_waiting_skill("hosting-expiry"), a_waiting_skill("ledger-close")), now=NOW)
    placed = (
        Placed(record=entries[0], where={"department": MAINTENANCE}),
        Placed(record=entries[1], where={"department": FINANCE}),
    )
    reader = holding("read:skill", scope=in_department(MAINTENANCE))

    queue = skill_queue(placed, reader, NOW)

    assert len(queue.entries) == 1
    assert queue.summary.waiting == len(queue.entries)


def test_a_company_wide_reader_sees_every_waiting_skill_and_a_summary_of_all_of_them() -> None:
    """The positive half. Delete it and `skill_queue` is satisfied by a function returning
    nothing, which passes the narrowing test above and leaves the review queue permanently
    empty, so nothing is ever read and nothing is ever approved."""
    entries = pending((a_waiting_skill("hosting-expiry"), a_waiting_skill("ledger-close")), now=NOW)
    placed = tuple(Placed(record=one, where={"department": MAINTENANCE}) for one in entries)

    queue = skill_queue(placed, holding("read:skill"), NOW)

    assert len(queue.entries) == 2
    assert queue.summary.waiting == 2
    assert queue.summary.stale == 0


def test_the_summary_counts_come_from_the_module_that_owns_the_staleness_rule() -> None:
    """Delete this and a staleness threshold is written here, and the copy is the one that
    gets raised the week somebody complains the queue is always red.
    `brain.tools.review.STALE_AFTER` is seven days, and the entry below has waited eight.

    Asserted through the queue's own summary rather than against the constant, so the claim is
    that this surface honours that module's rule rather than that the constant exists."""
    entries = pending(
        (a_waiting_skill("hosting-expiry"),),
        submitted_at={"hosting-expiry": NOW - timedelta(days=8)},
        now=NOW,
    )
    placed = (Placed(record=entries[0], where={}),)

    queue = skill_queue(placed, holding("read:skill"), NOW)

    assert queue.summary.stale == 1


# ---------------------------------------------------------- the knowledge library (M27.3.14)
def test_a_library_row_carries_the_level_and_has_nowhere_to_put_a_predicate() -> None:
    """Delete this and the visibility scope is rendered as its predicate, which is
    `owner_id = u_author` or `department = finance`: a row of the Scopes screen with a
    document's name in front of it.

    Asserted on the field names of the type rather than on one built row, because a row whose
    item happened to be company-wide would pass a test that only looked at values."""
    names = {one.name for one in fields(LibraryRow)}

    assert not names & NAMES_THAT_WOULD_BE_A_PREDICATE
    assert names == {"item_id", "level"}


def test_an_item_outside_the_readers_reach_is_absent_from_the_library() -> None:
    """Delete this and the library shows every item in the company to whoever can open the
    screen, which is the existence plane handed over whole. The two items differ only in the
    department they sit in."""
    items = (
        a_library_item("doc_1", department=MAINTENANCE),
        a_library_item("doc_2", department=FINANCE),
    )
    reader = holding("read:document", scope=in_department(MAINTENANCE))

    rows = library_rows(items, reader, NOW)

    assert tuple(one.item_id for one in rows) == ("doc_1",)
    assert rows[0].level is Visibility.DEPARTMENT


def test_a_company_wide_reader_sees_every_item_with_its_level() -> None:
    """The positive half, and the level is what the leaf calls the per-item visibility scope.
    Delete this and `library_rows` is satisfied by a function returning nothing, and the
    library is empty for the person it was built for."""
    items = (
        a_library_item("doc_1", department=MAINTENANCE),
        a_library_item("doc_2", department=FINANCE),
    )

    rows = library_rows(items, holding("read:document"), NOW)

    assert tuple(one.item_id for one in rows) == ("doc_1", "doc_2")
    assert {one.level for one in rows} == {Visibility.DEPARTMENT}


def test_the_department_grouping_is_withheld_on_the_narrower_basis() -> None:
    """**Withheld and never shortened.** Delete this and a reader without the Scopes screen's
    grant is shown a grouping of the departments they happen to reach, under a heading reading
    every department, with nothing on the screen saying it is four of nine. That is a
    confident answer that is wrong, which `brain.console.workspace.projection` argues is worse
    than no answer.

    The same items and the same reader in both calls, so the basis is the only thing that can
    decide."""
    items = (
        a_library_item("doc_1", department=MAINTENANCE),
        a_library_item("doc_2", department=FINANCE),
    )
    reader = holding("read:document")

    assert departments_represented(items, reader, basis=Basis.OWN, now=NOW) is None
    assert departments_represented(items, reader, basis=Basis.EVERYONE, now=NOW) == (
        FINANCE,
        MAINTENANCE,
    )


def test_the_grouping_never_names_a_department_none_of_the_readers_rows_sits_in() -> None:
    """Delete this and the grouping is built from every item rather than from the ones the
    reader may see, and the wider basis becomes a listing of every department that has a
    document in it, handed to somebody whose rows are one department.

    The reader holds the Scopes screen's grant, so the basis is wide, and their document grant
    is one department, so the rows are narrow. Those are the two things that have to be able to
    differ, and a single-scope reader could not express it."""
    items = (
        a_library_item("doc_1", department=MAINTENANCE),
        a_library_item("doc_2", department=FINANCE),
    )
    reader = EntitlementSet(
        principal_id="u_reader",
        grants=(
            Grant(capability=Capability(value="read:document"), scope=in_department(MAINTENANCE)),
            Grant(
                capability=screen(DEPARTMENT_SPAN_SCREEN).read.requires,
                scope=Scope(clauses=()),
            ),
            Grant(capability=plane_capability(Plane.CONTENT), scope=Scope(clauses=())),
        ),
    )

    assert spans_departments(reader, NOW) is Basis.EVERYONE
    assert departments_represented(items, reader, basis=Basis.EVERYONE, now=NOW) == (MAINTENANCE,)


# ----------------------------------------------------------- the learning review (M27.3.15)
def test_the_three_tiers_come_back_as_three_tuples_and_never_one_list() -> None:
    """Delete this and a tier column appears on one list, and a proposal waiting for a person
    sits next to a change that has already happened with a control beside each meaning
    different things. That is `SplitMemoryView`'s argument one surface over."""
    review = learning_review(
        basis=Basis.EVERYONE,
        visible={DESK},
        tier_one={DESK: (a_tier_one("m_1"),)},
        tier_two={DESK: (a_tier_two("m_2"),)},
        tier_three={DESK: (a_tier_three("m_3", department=MAINTENANCE),)},
    )

    assert tuple(one.memory_id for one in review.tier_one) == ("m_1",)
    assert tuple(one.memory_id for one in review.tier_two) == ("m_2",)
    assert review.tier_three is not None
    assert tuple(one.memory_id for one in review.tier_three) == ("m_3",)


def test_only_the_tier_that_names_a_department_is_withheld_on_the_narrower_basis() -> None:
    """**The precise half of this leaf.** Delete this and either the whole review is withheld,
    which empties a screen for a reader whose rows are perfectly ordinary, or nothing is, and
    the routing table for every access decision in the company is published.

    Tier one and tier two carry a memory id, a change, evidence kinds and an instant, and none
    of those says where anybody sits. The two calls differ only in the basis."""
    kwargs = {
        "visible": {DESK},
        "tier_one": {DESK: (a_tier_one("m_1"),)},
        "tier_two": {DESK: (a_tier_two("m_2"),)},
        "tier_three": {DESK: (a_tier_three("m_3", department=MAINTENANCE),)},
    }

    narrow = learning_review(basis=Basis.OWN, **kwargs)  # type: ignore[arg-type]

    assert narrow.tier_three is None
    assert tuple(one.memory_id for one in narrow.tier_one) == ("m_1",)
    assert tuple(one.memory_id for one in narrow.tier_two) == ("m_2",)


def test_a_learning_review_carries_no_control_over_a_page_of_changes() -> None:
    """Delete this and an undo-all arrives, which is one click applying corrections in
    departments the reader cannot enumerate, at the moment when what it will touch is exactly
    what the screen has been careful not to tell them.

    Asserted on the field names of the type, and on the per-row control still being there,
    because a review with no control at all would pass a check that only looked for a bulk
    one."""
    names = {one.name for one in fields(LearningReview)}

    assert not names & NAMES_THAT_WOULD_BE_A_BULK_CONTROL

    review = learning_review(
        basis=Basis.EVERYONE,
        visible={DESK},
        tier_one={DESK: (a_tier_one("m_1"),)},
        tier_two={},
        tier_three={},
    )

    assert review.tier_one[0].control_writes is Correction.DEMOTED


def test_a_learning_review_covers_the_agents_the_reader_may_see_and_no_others() -> None:
    """Delete this and the review is gathered from every agent in the mapping, so an agent the
    reader cannot see contributes rows to a screen about learning, which discloses the agent
    through what it inferred."""
    review = learning_review(
        basis=Basis.EVERYONE,
        visible={DESK},
        tier_one={DESK: (a_tier_one("m_1"),), FINANCE_AGENT: (a_tier_one("m_9"),)},
        tier_two={},
        tier_three={},
    )

    assert tuple(one.memory_id for one in review.tier_one) == ("m_1",)


def test_the_basis_is_carried_on_the_review_rather_than_left_implicit() -> None:
    """Delete this and a reader shown their own reach reads it as the company's, because a
    listing whose meaning is unstated is read as the whole of it. Saying which discloses
    nothing: the existence of other departments is not the secret, their contents are."""
    review = learning_review(
        basis=Basis.OWN, visible=set(), tier_one={}, tier_two={}, tier_three={}
    )

    assert review.basis is Basis.OWN


# ----------------------------------------------------------------- artifacts (M27.3.16)
def test_an_estate_artifact_listing_is_assembled_from_the_agents_the_reader_can_see() -> None:
    """Delete this and the agent filter is dropped, which is the global pile with an optional
    filter on it, and `brain.console.agent_output.visible_artifacts` says in its own words
    that the filter is the thing that gets omitted.

    Both artifacts belong to somebody else, so the caller branch cannot admit either, and the
    two differ only in which agent produced them."""
    reader = holding("read:artifact", principal_id="u_reader")
    entries = (
        an_artifact("a_1", agent_id=DESK, caller="u_other"),
        an_artifact("a_2", agent_id=FINANCE_AGENT, caller="u_other"),
    )

    shown = artifact_estate(entries, reader, NOW, visible_agents={DESK})

    assert tuple(one.artifact_id for one in shown) == ("a_1",)


def test_a_readers_own_artifact_survives_an_agent_they_cannot_see() -> None:
    """Delete this and a person's own output disappears the day an agent's audience narrows,
    which leaves the only person who knows what the artifact was for unable to find it again.

    The reader may see no agent at all and holds no artifact grant, so their own caller id is
    the only way in and the second artifact is what proves it is the only one."""
    reader = EntitlementSet(principal_id="u_reader", grants=())
    entries = (
        an_artifact("a_1", agent_id=FINANCE_AGENT, caller="u_reader"),
        an_artifact("a_2", agent_id=FINANCE_AGENT, caller="u_other"),
    )

    shown = artifact_estate(entries, reader, NOW, visible_agents=set())

    assert tuple(one.artifact_id for one in shown) == ("a_1",)


def test_an_estate_artifact_listing_is_newest_first_across_every_agent() -> None:
    """Delete this and each agent's run is sorted and the runs are concatenated, which is not
    sorted: a reader looking for what was produced this morning finds it below whatever the
    first agent produced last week.

    **The older artifact belongs to the agent whose id sorts first**, which is the only
    arrangement that can tell the two implementations apart: `visible_artifacts` returns each
    agent's own run already newest first, so with the newer artifact on the earlier agent a
    concatenation and a sort produce the same list, and a mutation removing the sort survives.
    That is exactly what happened when this test was first written the other way round.

    `agent_desk` sorts before `agent_ledger`, so the run for `agent_desk` is concatenated
    first and carries the older artifact."""
    reader = holding("read:artifact", principal_id="u_reader")
    older = an_artifact("a_1", agent_id=DESK, caller="u_other")
    newer = Artifact(
        artifact_id="a_2",
        agent_id=FINANCE_AGENT,
        kind=ArtifactKind.REPORT,
        run_id="run_a_2",
        agent_version="4.2.0",
        caller_id="u_other",
        entitlement_hash=holding("read:client.name", principal_id="u_other").ent_hash(),
        at=NOW,
        data_class=DataClass.BUSINESS_RECORD,
    )

    assert DESK < FINANCE_AGENT

    shown = artifact_estate((older, newer), reader, NOW, visible_agents={DESK, FINANCE_AGENT})

    assert tuple(one.artifact_id for one in shown) == ("a_2", "a_1")


# -------------------------------------------------------------- the memory viewer (M27.3.17)
def test_a_memory_viewer_refuses_to_be_asked_about_nobody() -> None:
    """**The structural half of this leaf.** Delete this and a blank subject means everybody,
    which is a directory of what the system knows about people, arriving through the argument
    somebody left empty rather than through a feature anybody argued for."""
    with pytest.raises(EstateError, match="no subject"):
        subject_memory(
            subject_id="  ",
            entries=(),
            reader=holding("read:memory"),
            now=NOW,
        )


def test_a_memory_viewer_shows_one_subject_and_never_the_person_beside_them() -> None:
    """Delete this and the viewer returns every learning it was handed, so two people's
    memories arrive on one page and the reader cannot tell which is whose.

    Both learnings are readable by this reader, so the subject filter is the only thing that
    can decide."""
    reader = holding("read:client.name", "read:memory", principal_id="u_reader")
    entries = (
        (a_learning("m_1", subject_principal="u_one"), "prefers email"),
        (a_learning("m_2", subject_principal="u_two"), "prefers a call"),
    )

    view = subject_memory(subject_id="u_one", entries=entries, reader=reader, now=NOW)

    assert view.subject_id == "u_one"
    assert tuple(one.memory_id for one in view.memory.extracted) == ("m_1",)


def test_a_memory_viewer_carries_the_change_history_of_that_subject() -> None:
    """The positive half of the history. Delete this and `subject_memory` is satisfied by a
    function returning no revisions, and the viewer's whole reason for existing, that a wrong
    inference can be traced to what replaced what, is gone.

    Both revisions are the same subject's and the second replaced the first, so the diff is
    the thing under test rather than the filtering."""
    reader = holding("read:client.name", "read:memory", principal_id="u_reader")
    first = a_learning("m_1", subject_principal="u_one", at=NOW - timedelta(days=2))
    second = a_learning("m_2", subject_principal="u_one", replaced_id="m_1", at=NOW)
    entries = ((first, "prefers email"), (second, "prefers a call"))

    view = subject_memory(subject_id="u_one", entries=entries, reader=reader, now=NOW)

    assert tuple(one.memory_id for one in view.history) == ("m_1", "m_2")
    assert view.history[1].diff != ()


# ------------------------------------------------------------------------- the diagnostic
def test_the_deployment_check_is_clean_for_the_module_as_it_stands() -> None:
    """Delete this and `estate_gaps` can be broken by an edit to the module it checks without
    anything failing, which is the state a diagnostic spends most of its life in."""
    assert estate_gaps() == ()


def test_the_diagnostic_names_a_library_row_that_would_carry_a_predicate() -> None:
    """Delete this and a department column arrives on the library row, added by somebody who
    wanted the screen grouped, and the grouping decision is bypassed one field at a time."""
    leaky = make_dataclass("LeakyLibraryRow", [("item_id", str), ("department", str)])

    findings = estate_gaps(rows=(), library_row=leaky)

    assert any("department" in one for one in findings)


def test_the_diagnostic_names_a_review_that_would_carry_a_bulk_control() -> None:
    """Delete this and an undo-all is added to the learning review by somebody clearing a
    backlog, and it applies corrections in departments the reader cannot enumerate."""
    leaky = make_dataclass("LeakyReview", [("basis", str), ("undo_all", bool)])

    findings = estate_gaps(rows=(), review_type=leaky)

    assert any("undo_all" in one for one in findings)


def test_the_diagnostic_names_a_listing_that_could_be_asked_for_the_whole_estate() -> None:
    """**The check that keeps the per-agent rule alive.** Delete this and a listing here grows
    an `all_agents` parameter, which is the global pile arriving as a keyword argument added
    to save a loop.

    Handed a constructed function rather than relying on the module's own, because a check
    that can only run against the healthy tree has nothing to report and every mutation in it
    survives."""

    def widened(rows: tuple[str, ...], *, all_agents: bool = False) -> tuple[str, ...]:
        return rows

    findings = estate_gaps(rows=(), signatures=(widened,))

    assert len(findings) == 1
    assert "all_agents" in findings[0]


def test_the_diagnostic_names_a_row_that_would_count_what_it_hid() -> None:
    """Delete this and a hidden count arrives on one of these four row types, which is the
    disclosure by subtraction the whole design refuses. Reused from
    `brain.ops.jobs.hidden_count_fields` rather than restated."""
    leaky = make_dataclass("LeakyEstateRow", [("item_id", str), ("hidden_count", int)])

    findings = estate_gaps(rows=(leaky,))

    assert any("hidden_count" in one for one in findings)


def test_the_diagnostic_names_a_screen_key_the_registry_does_not_have() -> None:
    """Delete this and a decision here rests on a capability nobody registered, so the grant
    that governs it is one no administrator reviews."""
    findings = estate_gaps(rows=(), span_screen="a_screen_nobody_registered")

    assert len(findings) == 1
    assert "a_screen_nobody_registered" in findings[0]


def test_the_pinned_screen_keys_name_the_screens_this_module_reads() -> None:
    """Delete this and a screen key here can be repointed at another screen, and every
    decision that reads its requirement would start asking for a different capability while
    still passing.

    Each pair is asserted against the capability string as written, which is outside both the
    constant and the registry entry, so moving either one fails."""
    assert screen(DEPARTMENT_SPAN_SCREEN).read.requires.value == "read:scope"
    assert screen(PROMOTION_APPROVER_SCREEN).read.requires.value == "read:grant"


def test_no_listing_here_asks_for_everybody_at_once() -> None:
    """The deployment half of the signature check, asserted over the module's own functions
    rather than over a constructed one, so the two tests together say both that the check
    works and that it currently passes."""
    assert estate_gaps(rows=()) == ()
    assert "all_agents" in NAMES_THAT_WOULD_ASK_FOR_EVERYBODY


def test_the_estate_count_is_the_number_of_leaves_the_module_claims() -> None:
    """Delete this and `ESTATE_COUNT` becomes a number that agrees with itself. It is pinned
    against the module's own `Task ids:` lines, which is the record the traceability sweep
    reads, so the constant cannot drift from the claim."""
    source = Path(str(estate_module.__file__)).read_text(encoding="utf-8")
    claimed = {one for line in TASK_LINE_RE.findall(source) for one in TASK_ID_RE.findall(line)}

    assert len(claimed) == ESTATE_COUNT
    assert all(one.startswith("M27.3.") for one in claimed)


def test_nothing_in_this_module_computes_a_reach() -> None:
    """Delete this and a third implementation of `E_run(caller, agent)` appears in the module
    that gathers six surfaces together, which is exactly where somebody would need one.

    Read out of the source through `brain.console.workspace.intersections_in`, which parses
    rather than searching for the word, because this module's own docstring says `intersect`
    and a text search would report itself."""
    from brain.console.workspace import intersections_in

    source = Path(str(estate_module.__file__)).read_text(encoding="utf-8")

    assert intersections_in(source) == ()
