"""A stored document's lifecycle as rules: who may act, what a version, a verification, a hand-over,
a promotion and a solution may be, and what a task says. No server.

The acts themselves, against the tables and the triggers `0120` builds, are
`tests/unit/test_knowledge_lifecycle_db.py`'s. What is held here is every rule those acts ask, over
values built in memory, with each refusal beside the case it still admits.

The clock is 2999, for the reason CLAUDE.md records.

Task ids: M7.4.4, M7.4.5, M7.4.6, M7.6.2, M7.7.2
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType

import pytest

from brain.core.department import department_scope
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.gate.leash import ApprovalState
from brain.knowledge.item import (
    A_NEW_VERSION_REACHES_NOBODY_THE_OLD_ONE_DID_NOT,
    KnowledgeError,
    KnowledgeItem,
    KnowledgeState,
    assert_supersedable,
    badge,
    supersede,
)
from brain.knowledge.kinds import KnowledgeKind
from brain.knowledge.lifecycle import (
    DISMISSABLE,
    STEWARD_REFUSED,
    Authority,
    LifecycleError,
    Outcome,
    StewardTask,
    StoredItem,
    TaskKind,
    assert_may_hand_over,
    assert_may_propose,
    authority_for,
    successor_place,
    task_sentence,
    verification_for,
)
from brain.knowledge.lifecycle_store import DECIDING_SETTING
from brain.knowledge.promotion import (
    PROMOTION_AGENT,
    PROMOTION_ARGS,
    PROMOTION_TOOL,
    PROMOTION_WINDOW,
    PromotionError,
    PromotionStatus,
    asked_by,
    is_promotion,
    promoted_item,
    raise_promotion,
    status_of,
)
from brain.knowledge.search import KNOWLEDGE_READ, KNOWLEDGE_UPLOAD, Reach
from brain.knowledge.solutions import (
    SOLUTION_HEADING,
    SOLVED_HEADING,
    SolutionNotOffered,
    SolutionState,
    approved_item,
    capture,
    decided,
    may_decide,
)
from brain.knowledge.verification import disclose
from brain.knowledge.visibility import (
    PROMOTION_CAPABILITY,
    KnowledgeVisibility,
    PromotionProposal,
    Visibility,
    VisibilityError,
    approve_promotion,
    propose_promotion,
)
from brain.member_library import LibraryError, assert_replaceable

NOW = datetime(2999, 6, 1, 9, 0, tzinfo=UTC)
DAY = timedelta(days=1)
REGISTRY = ("finance", "web")
MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "versions"
LIFECYCLE_MIGRATION = MIGRATION / "0120_knowledge_lifecycle.py"


def migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("m0120_rules", LIFECYCLE_MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stored(
    item_id: str = "upload.v1",
    *,
    owner: str = "u_steward",
    visibility: KnowledgeVisibility | None = None,
    state: KnowledgeState = KnowledgeState.PUBLISHED,
    verified: bool = True,
    review_by: datetime | None = NOW + 90 * DAY,
) -> StoredItem:
    return StoredItem(
        item_id=item_id,
        title="Site handover",
        owner_id=owner,
        visibility=visibility or KnowledgeVisibility.of_department("web", owner_id=owner),
        state=state,
        kind=KnowledgeKind.SOP,
        verified_by="u_verifier" if verified else "",
        verified_at=NOW - DAY if verified else None,
        review_by=review_by,
    )


def reach(principal: str, *grants: tuple[Capability, Scope]) -> EntitlementSet:
    return EntitlementSet(
        principal_id=principal,
        grants=tuple(Grant(capability=one, scope=scope) for one, scope in grants),
    )


def authority(principal: str, *grants: tuple[Capability, Scope]) -> Authority:
    return authority_for(reach(principal, *grants), departments=REGISTRY, now=NOW)


WEB = department_scope("web")
FINANCE = department_scope("finance")


# ------------------------------------------------------------------ who may act
def test_a_steward_who_reads_the_document_may_act_and_one_who_left_the_department_may_not() -> None:
    """`owner_id` never moves and a department does. Delete this and a steward who moved to finance
    goes on verifying, replacing and publishing web's documents."""
    item = stored()
    stays = authority("u_steward", (KNOWLEDGE_READ, WEB))
    left = authority("u_steward", (KNOWLEDGE_READ, FINANCE))

    assert stays.may_act(item) and stays.stewards(item)
    assert not left.may_act(item) and not left.may_see(item)


def test_an_administrator_where_it_sits_may_act_without_reading_it_and_nowhere_else() -> None:
    """K1's line: `admin:knowledge` over a department is adding there, not reading there. Delete
    this and an administrator of finance acts on web's documents, or web's administrator is locked
    out of documents they may add beside."""
    item = stored()
    web_admin = authority("u_admin", (KNOWLEDGE_UPLOAD, WEB))
    finance_admin = authority("u_admin", (KNOWLEDGE_UPLOAD, FINANCE))

    assert web_admin.may_act(item) and web_admin.may_see(item)
    assert not web_admin.may_read(item)
    assert not finance_admin.may_act(item) and not finance_admin.may_see(item)


def test_a_personal_document_is_its_owners_alone_whatever_anybody_administers() -> None:
    """Anybody else acting on a personal document learns it exists. Delete this and an administrator
    holding `admin:knowledge` everywhere acts on everybody's private notes."""
    mine = stored(visibility=KnowledgeVisibility.personal("u_steward"))
    everywhere = authority("u_admin", (KNOWLEDGE_UPLOAD, Scope.unrestricted()))
    owner = authority("u_steward", (KNOWLEDGE_READ, WEB))

    assert not everywhere.may_act(mine) and not everywhere.may_see(mine)
    assert owner.may_act(mine)


def test_a_replaced_version_is_acted_on_by_nobody_and_seen_where_it_was_read() -> None:
    """A superseded version is history: nobody verifies or replaces it, and it is shown to exactly
    the people its own place admitted. Delete this and an old version can be re-published by
    verifying it, or shown to a department that never read it."""
    old = stored(state=KnowledgeState.SUPERSEDED)
    web = authority("u_reader", (KNOWLEDGE_READ, WEB))
    finance = authority("u_reader", (KNOWLEDGE_READ, FINANCE))

    assert not web.may_act(old)
    assert web.may_see(old) and web.may_read(old)
    assert not finance.may_see(old)


def test_a_reach_belonging_to_somebody_else_is_refused_as_an_authority() -> None:
    """Delete this and one person's reach decides what another may do to a document."""
    with pytest.raises(LifecycleError):
        Authority(principal_id="u_one", reads=Reach(principal_id="u_two", departments=("web",)))


def test_the_store_reach_is_the_read_and_the_add_together_and_deciding_is_the_add_alone() -> None:
    """The second wall is told read and add for rows and add alone for deciding a solution. Delete
    this and a department reader could decide a solution, or an administrator be shown nothing."""
    both = authority("u_admin", (KNOWLEDGE_READ, WEB), (KNOWLEDGE_UPLOAD, FINANCE))

    assert set(both.store_reach().departments) == {"web", "finance"}
    assert both.deciding_setting() == "finance"
    assert DECIDING_SETTING == migration().DECIDING_SETTING


# ------------------------------------------------------------------ verification (M7.4.6)
def test_a_verification_needs_a_review_date_ahead_of_it() -> None:
    """Delete this and a verification with a date behind it opens a task the day it is written."""
    item = stored(verified=False, review_by=None)

    done = verification_for(item, by="u_steward", at=NOW, review_by=NOW + 30 * DAY)
    assert (done.verified_by, done.verified_at, done.review_by) == (
        "u_steward",
        NOW,
        NOW + 30 * DAY,
    )
    with pytest.raises(LifecycleError, match="ahead of today"):
        verification_for(item, by="u_steward", at=NOW, review_by=NOW)
    with pytest.raises(LifecycleError, match="naive"):
        verification_for(item, by="u_steward", at=NOW, review_by=datetime(2999, 7, 1))


def test_a_replaced_document_is_not_verified() -> None:
    """A badge on a replaced version vouches for text no answer uses. Delete this and it is shown as
    verified beside the one that replaced it."""
    with pytest.raises(LifecycleError, match="superseded"):
        verification_for(
            stored(state=KnowledgeState.SUPERSEDED), by="u_s", at=NOW, review_by=NOW + DAY
        )


def test_a_stored_row_goes_through_the_same_badge_and_disclosure_as_a_document() -> None:
    """The rules read a record. Delete this and a stored row needs its text to be badged, or is
    badged by a second copy of the rule."""
    item = stored()
    shown = disclose(item, reader=reach("u_other"), now=NOW)

    assert badge(item, now=NOW).state.value == "verified"
    assert shown.state.value == "verified" and not shown.names_the_verifier
    assert disclose(item, reader=reach("u_verifier"), now=NOW).names_the_verifier


# ------------------------------------------------------------------ a new version (M7.4.5)
def test_a_new_version_is_placed_where_the_old_one_sits_and_stewarded_as_it_was() -> None:
    """Stewardship is of the document. Delete this and a new version lands wherever the uploader
    chose, stewarded by whoever uploaded it."""
    place = successor_place(stored())
    assert (place.level, place.department, place.owner_id) == (
        Visibility.DEPARTMENT,
        "web",
        "u_steward",
    )
    personal = successor_place(stored(visibility=KnowledgeVisibility.personal("u_steward")))
    assert (personal.level, personal.owner_id) == (Visibility.PERSONAL, "u_steward")


def test_a_new_version_of_company_knowledge_starts_in_its_department_or_is_refused() -> None:
    """Company scope needs a verified text and a second person, and a new version has neither.
    Delete this and a new version of the handbook is published to everybody unread."""
    wide = KnowledgeVisibility(level=Visibility.COMPANY, owner_id="u_steward", department="web")
    placed = successor_place(stored(visibility=wide))
    assert (placed.level, placed.department) == (Visibility.DEPARTMENT, "web")
    with pytest.raises(LifecycleError, match="no department"):
        successor_place(stored(visibility=KnowledgeVisibility.company(owner_id="u_steward")))


def _version(visibility: KnowledgeVisibility, item_id: str = "upload.v2") -> KnowledgeItem:
    return KnowledgeItem(
        item_id=item_id,
        content="The new text.",
        title="Site handover",
        visibility=visibility,
        owner_id=visibility.owner_id or "u_steward",
        state=KnowledgeState.PUBLISHED,
        review_by=NOW + 90 * DAY,
    )


def test_a_successor_in_another_department_is_refused_and_one_in_the_same_is_not() -> None:
    """Same level, different audience: finance would read what replaced web's document. Delete this
    and supersession moves documents between departments with nobody deciding it."""
    before = stored()
    same = _version(KnowledgeVisibility.of_department("web", owner_id="u_steward"))
    other = _version(KnowledgeVisibility.of_department("finance", owner_id="u_steward"))

    assert_supersedable(before, same)
    with pytest.raises(VisibilityError) as refused:
        assert_supersedable(before, other)
    assert A_NEW_VERSION_REACHES_NOBODY_THE_OLD_ONE_DID_NOT in str(refused.value)


def test_a_personal_successor_for_somebody_else_is_refused() -> None:
    """Delete this and one person's private note is replaced into another person's."""
    before = stored(visibility=KnowledgeVisibility.personal("u_steward"))
    with pytest.raises(VisibilityError):
        assert_supersedable(before, _version(KnowledgeVisibility.personal("u_other")))
    assert_supersedable(before, _version(KnowledgeVisibility.personal("u_steward")))


def test_a_withdrawn_document_is_not_brought_back_as_a_version() -> None:
    """Archived had nothing replacing it. Delete this and a withdrawal is undone by an upload."""
    with pytest.raises(KnowledgeError, match="withdrawn"):
        assert_supersedable(
            stored(state=KnowledgeState.ARCHIVED),
            _version(KnowledgeVisibility.of_department("web", owner_id="u_steward")),
        )


def test_the_member_rule_and_the_store_rule_are_one_and_the_review_date_is_required() -> None:
    """`assert_replaceable` is what the new-version route asks and what `replace` asks. Delete this
    and the console's replacement can drop the review cycle the member path requires."""
    before = stored()
    undated = _version(KnowledgeVisibility.of_department("web", owner_id="u_steward"))
    undated = undated.model_copy(update={"review_by": None})
    with pytest.raises(LibraryError):
        assert_replaceable(before, undated)
    assert_replaceable(
        before, _version(KnowledgeVisibility.of_department("web", owner_id="u_steward"))
    )


def test_supersede_still_returns_both_and_refuses_the_move_it_now_refuses() -> None:
    """The document form of the rule. Delete this and `supersede` and `assert_supersedable` part."""
    web = KnowledgeVisibility.of_department("web", owner_id="u_steward")
    old = _version(web, "k_v1")
    new = _version(web, "k_v2")
    replaced, current = supersede(old, new)
    assert (replaced.state, current.supersedes) == (KnowledgeState.SUPERSEDED, "k_v1")
    with pytest.raises(VisibilityError):
        supersede(old, _version(KnowledgeVisibility.of_department("finance"), "k_v3"))


# ------------------------------------------------------------------ handing over (M7.7.2)
def test_a_document_is_handed_to_somebody_who_reads_it_or_administers_it() -> None:
    """Delete this and a steward can be named who the sweep never asks."""
    item = stored()
    assert_may_hand_over(item, to="u_reader", theirs=authority("u_reader", (KNOWLEDGE_READ, WEB)))
    assert_may_hand_over(item, to="u_admin", theirs=authority("u_admin", (KNOWLEDGE_UPLOAD, WEB)))


def test_a_steward_who_could_not_reach_it_is_refused_in_one_sentence_whoever_they_are() -> None:
    """The refusal is the same for somebody in another department, somebody with nothing, and a
    reach offered for somebody else. Delete this and naming a steward asks who reads what."""
    item = stored()
    said = []
    for theirs, to in (
        (authority("u_finance", (KNOWLEDGE_READ, FINANCE)), "u_finance"),
        (authority("u_nobody"), "u_nobody"),
        (authority("u_reader", (KNOWLEDGE_READ, WEB)), "u_somebody_else"),
        (None, "u_ghost"),
    ):
        with pytest.raises(LifecycleError) as refused:
            assert_may_hand_over(item, to=to, theirs=theirs)
        said.append(str(refused.value))
    assert said == [STEWARD_REFUSED] * 4


def test_a_personal_or_unpublished_document_and_its_own_steward_are_not_handed_over() -> None:
    """Delete this and a private note acquires a second reader, or a hand-over to nobody new."""
    reader = authority("u_steward", (KNOWLEDGE_READ, WEB))
    with pytest.raises(LifecycleError, match="owner's alone"):
        assert_may_hand_over(
            stored(visibility=KnowledgeVisibility.personal("u_steward")),
            to="u_reader",
            theirs=authority("u_reader", (KNOWLEDGE_READ, WEB)),
        )
    with pytest.raises(LifecycleError, match="already"):
        assert_may_hand_over(stored(), to="u_steward", theirs=reader)


# ------------------------------------------------------------------ promotion (M7.4.4)
def _proposal(proposer: str = "u_steward") -> PromotionProposal:
    return propose_promotion(
        item_id="upload.v1",
        from_level=Visibility.DEPARTMENT,
        to_level=Visibility.COMPANY,
        proposer_id=proposer,
        owner_id="u_steward",
        review_by=NOW + 180 * DAY,
        reason="every team quotes from this",
        now=NOW,
    )


def test_an_unverified_or_company_wide_document_is_not_proposed() -> None:
    """Company scope refuses an unverified published item, so the proposal is refused before a
    Super Admin reads a card they could never approve. Delete this and the Approvals screen fills
    with cards whose approval raises."""
    assert_may_propose(stored())
    with pytest.raises(LifecycleError, match="not been verified"):
        assert_may_propose(stored(verified=False, review_by=None))
    with pytest.raises(VisibilityError):
        assert_may_propose(stored(visibility=KnowledgeVisibility.company(owner_id="u_steward")))


def test_a_promotion_is_a_suspension_the_gates_approvers_are_offered_and_nobody_else() -> None:
    """The card requires the gate's capability over the document's department, so the Approvals
    screen offers it to exactly the people `approve_promotion` admits. Delete this and a promotion
    is offered to an approver of agent actions, or to nobody."""
    proposal = _proposal()
    raised = raise_promotion(
        proposal,
        title="Site handover",
        kind=KnowledgeKind.SOP,
        department="web",
        reach=reach("u_steward"),
        trace_id="t-promotion",
        now=NOW,
    )

    assert is_promotion(raised) and promoted_item(raised) == "upload.v1"
    assert raised.action.tool.required_capability == PROMOTION_CAPABILITY.value
    assert raised.action.row == {"department": "web"}
    assert raised.expires_at - raised.raised_at == PROMOTION_WINDOW
    assert raised.principal_id == "u_steward"
    super_admin = reach("u_super", (PROMOTION_CAPABILITY, Scope.unrestricted()))
    approve_promotion(proposal, approver_id="u_super", entitlement=super_admin, now=NOW)


def test_a_promotion_is_never_offered_to_its_asker_and_is_to_another_holder_of_the_approval() -> (
    None
):
    """**Found by the install acceptance check on 2026-09-29.** A steward holding
    approve:knowledge.visibility over their own department was offered their own card, and
    approving it met `0120`'s refusal as a fault. Now the queue, the card and the decision all
    leave it out for them, while a second holder of the same grant is offered it and may decide it;
    and an agent's action is still offered to the person it runs for, which is Assisted. Delete
    this and the asker's card comes back as a button that can only fail."""
    from brain.audit.ledger import AuditChain
    from brain.audit.record import ApprovalVerdict, AuditRecorder
    from brain.console.approvals import ApprovalError, card, decide
    from brain.console.role_surfaces import pending_for

    approves_web = (PROMOTION_CAPABILITY, WEB)
    steward = reach("u_steward", approves_web)
    other = reach("u_other", approves_web)
    raised = raise_promotion(
        _proposal(),
        title="Site handover",
        kind=KnowledgeKind.SOP,
        department="web",
        reach=steward,
        trace_id="t-promotion",
        now=NOW,
    )

    assert asked_by(raised, "u_steward") and not asked_by(raised, "u_other")
    assert pending_for(steward, [raised], NOW) == ()
    assert card(raised, steward, NOW) is None
    recorder = AuditRecorder(
        AuditChain(), actor_id="u_steward", ent_hash="e" * 32, trace_id="t", clock=lambda: NOW
    )
    with pytest.raises(ApprovalError):
        decide(raised, steward, recorder, verdict=ApprovalVerdict.APPROVED, now=NOW)
    assert pending_for(other, [raised], NOW) == (raised,)
    assert card(raised, other, NOW) is not None

    agents = raised.model_copy(
        update={"action": raised.action.model_copy(update={"agent_id": "agent_web"})}
    )
    assert not is_promotion(agents) and not asked_by(agents, "u_steward")
    assert pending_for(steward, [agents], NOW) == (agents,)


def test_the_card_names_the_document_and_why_and_never_carries_text() -> None:
    """Delete this and an approver decides on an id, or reads the document's words off a card."""
    raised = raise_promotion(
        _proposal(),
        title="Site handover",
        kind=KnowledgeKind.SOP,
        department="web",
        reach=reach("u_steward"),
        trace_id="t-promotion",
        now=NOW,
    )
    lines = raised.artefact.splitlines()
    assert "Document: Site handover" in lines
    assert "Kind: SOP" in lines
    assert "Readable now by: the web department" in lines
    assert "Reason: every team quotes from this" in lines


def test_a_promotion_raised_under_somebody_elses_reach_is_refused() -> None:
    """Delete this and a card names somebody who never asked."""
    with pytest.raises(PromotionError):
        raise_promotion(
            _proposal(),
            title="t",
            kind=None,
            department="web",
            reach=reach("u_other"),
            trace_id="t-promotion",
            now=NOW,
        )


def test_the_trigger_reads_the_arguments_the_action_carries_and_names_the_same_act() -> None:
    """`0120`'s trigger reads the action's arguments by name. Delete this and a renamed argument
    makes every approved promotion raise, or apply to the wrong document."""
    built = migration()
    assert set(built.PROMOTION_ARGS_READ) <= set(PROMOTION_ARGS)
    assert built.PROMOTION_AGENT == PROMOTION_AGENT
    assert PROMOTION_TOOL.required_capability == built.PROMOTION_CAPABILITY
    raised = raise_promotion(
        _proposal(),
        title="t",
        kind=None,
        department="web",
        reach=reach("u_steward"),
        trace_id="t-promotion",
        now=NOW,
    )
    assert set(raised.action.args) == set(PROMOTION_ARGS)


def test_a_promotion_reads_as_waiting_approved_rejected_or_lapsed() -> None:
    """Delete this and a lapsed card reads as still waiting for ever."""
    raised = raise_promotion(
        _proposal(),
        title="t",
        kind=None,
        department="web",
        reach=reach("u_steward"),
        trace_id="t-promotion",
        now=NOW,
    )
    assert status_of(raised, now=NOW) is PromotionStatus.WAITING
    assert status_of(raised, now=NOW + PROMOTION_WINDOW) is PromotionStatus.LAPSED
    approved = raised.approved_by("u_super", NOW + DAY / 2)
    assert status_of(approved, now=NOW + 2 * DAY) is PromotionStatus.APPROVED
    assert approved.state is ApprovalState.APPROVED
    assert status_of(raised.rejected_by("u_super", NOW), now=NOW) is PromotionStatus.REJECTED


# ------------------------------------------------------------------ solutions (M7.6.2)
def test_a_solution_is_captured_only_where_the_capturer_reaches() -> None:
    """Delete this and the capture form is a way to ask which departments exist."""
    reader = authority("u_reader", (KNOWLEDGE_READ, WEB))
    kept = capture(
        problem="Checkout fails after the plugin update",
        answer="Clear the object cache.",
        department="web",
        conversation_ref="conv.123",
        by=reader,
        now=NOW,
    )
    assert (kept.state, kept.captured_by, kept.department) == (
        SolutionState.PENDING,
        "u_reader",
        "web",
    )
    with pytest.raises(SolutionNotOffered):
        capture(
            problem="p", answer="a", department="finance", conversation_ref="", by=reader, now=NOW
        )
    with pytest.raises(LifecycleError, match="reference"):
        capture(
            problem="p", answer="a", department="web", conversation_ref="a b", by=reader, now=NOW
        )


def test_the_capturer_never_decides_and_an_administrator_where_it_goes_does() -> None:
    """Delete this and a solution becomes knowledge on its capturer's own word."""
    both = authority("u_admin", (KNOWLEDGE_READ, WEB), (KNOWLEDGE_UPLOAD, WEB))
    own = capture(problem="p", answer="a", department="web", conversation_ref="", by=both, now=NOW)
    theirs = capture(
        problem="p",
        answer="a",
        department="web",
        conversation_ref="",
        by=authority("u_reader", (KNOWLEDGE_READ, WEB)),
        now=NOW,
    )

    assert not may_decide(own, both)
    assert may_decide(theirs, both)
    assert not may_decide(theirs, authority("u_other", (KNOWLEDGE_UPLOAD, FINANCE)))
    with pytest.raises(SolutionNotOffered):
        decided(own, by=both, outcome=SolutionState.APPROVED, at=NOW)


def test_an_approved_solution_is_a_verified_document_of_its_kind_opening_with_what_it_solved() -> (
    None
):
    """What it solved, who approved and when, retrieved like any verified item. Delete this and an
    approved solution is stored unverified, as an ordinary kind, or without its problem."""
    approver = authority("u_admin", (KNOWLEDGE_UPLOAD, WEB))
    waiting = capture(
        problem="Checkout fails after the plugin update\nOn every store",
        answer="Clear the object cache.",
        department="web",
        conversation_ref="",
        by=authority("u_reader", (KNOWLEDGE_READ, WEB)),
        now=NOW,
    )
    item = approved_item(waiting, by=approver, review_by=NOW + 365 * DAY, now=NOW)

    assert item.kind is KnowledgeKind.APPROVED_SOLUTION
    assert (item.verified_by, item.verified_at, item.review_by) == (
        "u_admin",
        NOW,
        NOW + 365 * DAY,
    )
    assert (item.owner_id, item.state, item.visibility.department) == (
        "u_admin",
        KnowledgeState.PUBLISHED,
        "web",
    )
    assert item.item_id == waiting.solution_id
    assert item.title == "Checkout fails after the plugin update"
    assert item.content.startswith(SOLVED_HEADING)
    assert SOLUTION_HEADING in item.content and "Clear the object cache." in item.content
    with pytest.raises(LifecycleError):
        approved_item(waiting, by=approver, review_by=NOW, now=NOW)


# ------------------------------------------------------------------ tasks
def test_every_task_kind_says_one_document_and_no_count() -> None:
    """Delete this and a task says how many others there are, or a review task names no date."""
    due = StewardTask(
        task_id="reverification.x",
        kind=TaskKind.REVERIFY,
        item_id="upload.v1",
        opened_at=NOW,
        due_at=NOW - DAY,
    )
    said = task_sentence(due, title="Site handover")
    assert said.startswith("Site handover was due for review on 2999-05-31.")
    assert not any(ch.isdigit() for ch in said.replace("2999-05-31", ""))
    for kind in (TaskKind.PROMOTION_DECIDED, TaskKind.SOLUTION_DECIDED):
        for outcome in Outcome:
            one = StewardTask(
                task_id="decided.x", kind=kind, item_id="i", opened_at=NOW, outcome=outcome
            )
            assert "Site handover" in task_sentence(one, title="Site handover")
    named = StewardTask(task_id="s", kind=TaskKind.STEWARD_NAMED, item_id="i", opened_at=NOW)
    assert "steward of Site handover" in task_sentence(named, title="Site handover")


def _newest_task_kinds() -> tuple[str, ...]:
    """The task kinds the newest migration declaring them leaves the table holding."""
    import importlib.util

    newest: tuple[str, ...] = ()
    for path in sorted(MIGRATION.glob("*.py")):
        if "TASK_KINDS" not in path.read_text(encoding="utf-8"):
            continue
        spec = importlib.util.spec_from_file_location(f"m_{path.stem}", path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        newest = tuple(getattr(module, "TASK_KINDS", newest))
    return newest


def test_a_review_task_is_not_dismissed_and_the_kinds_are_the_tables() -> None:
    """A review is closed by verifying. Delete this and the task list can be emptied by pressing a
    button while every document stays overdue, or the table refuse a kind the code opens."""
    built = migration()
    assert TaskKind.REVERIFY not in DISMISSABLE
    # The kinds are widened by `0198`, so the newest migration that declares them is the one
    # the table holds.
    assert tuple(sorted(one.value for one in TaskKind)) == _newest_task_kinds()
    assert TaskKind.CORRECTION_PROPOSED not in DISMISSABLE
    assert tuple(sorted(one.value for one in Outcome)) == built.OUTCOMES
    assert tuple(sorted(one.value for one in SolutionState)) == built.SOLUTION_STATES
