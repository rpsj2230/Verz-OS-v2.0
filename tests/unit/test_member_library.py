"""A member's own library, held to the two rules that decide what a personal surface may do.

The first rule is that ownership is not entitlement. `brain.console.own_things.own_knowledge`
narrows by owner and deliberately does not narrow by level, which is right for a console
listing what somebody answers for; a personal library is what they may open, and the two come
apart when a person changes department. The discriminating fixture is an item they own, scoped
to a department they are no longer in, and it must be absent (M40.3.1.5).

The second is that sharing does not grant. A share makes something already reachable findable
and can never make something reachable, and the fixture that proves it is a colleague who
could open an artifact on Monday, is refused on Tuesday, and whose `Share` row is byte for byte
unchanged in between (M40.3.3.3). Beside it sits the case
`brain.console.agent_output` uses for the same rule: a stranger whose grants hash identically
to what produced the artifact and who is still refused, because a check written against the
hash would let them through and would look correct doing it.

Real `KnowledgeItem`s, real `EntitlementSet`s, real `ImportedSkill`s with real digests, real
`Artifact`s built through `brain.console.agent_output.record`, and the real retention horizons
throughout. Nothing here builds the value the function under test produces: the badge cases go
through `brain.knowledge.item.badge`, the review states go through
`ImportedSkill.approved_by` and `with_content`, and the horizon cases are computed from
`brain.ops.retention.horizon_for` rather than from a number written here.

Task ids: M40.3.1.1, M40.3.1.2, M40.3.1.3, M40.3.1.4, M40.3.1.5, M40.3.2.1, M40.3.2.2
Task ids: M40.3.2.3, M40.3.2.4, M40.3.3.1, M40.3.3.2, M40.3.3.3
"""

from __future__ import annotations

import hashlib
import inspect
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from brain.agents.model import AgentAudience, AgentAuthority, AgentRecord
from brain.console.agent_output import (
    ARTIFACT_CAPABILITY,
    Artifact,
    ArtifactInput,
    ArtifactKind,
    record,
)
from brain.console.agent_tabs import ItemRetrieval, Review
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.field_policy import Classification
from brain.core.scope import Clause, Op, Scope
from brain.knowledge.item import KnowledgeItem, KnowledgeState, VerificationState
from brain.knowledge.visibility import (
    KnowledgeVisibility,
    Visibility,
    VisibilityError,
)
from brain.member_library import (
    ORIGIN_SOURCE,
    AuthoredUse,
    AuthorUsage,
    LibraryEntry,
    LibraryError,
    Origin,
    PersonalSkill,
    PromotionRequest,
    Share,
    SkillRow,
    Submission,
    add_skill,
    attach_refusals,
    authored_usage,
    library_gaps,
    library_notes,
    may_redownload,
    my_library,
    my_skills,
    open_share,
    origin_of,
    produced_for_me,
    promotion_tier,
    reachable_own_items,
    reaches,
    replace,
    request_promotion,
    retire,
    share,
    submit_for_review,
    upload,
)
from brain.memory.tiers import Change, Tier, blast_radius
from brain.ops.retention import DataClass, horizon_for
from brain.tools.skills import ImportedSkill, Skill, SkillSource, SkillState, SourceKind

NOW = datetime(2027, 2, 9, 9, 0, tzinfo=UTC)
LATER = NOW + timedelta(days=90)

#: Three people, so a personal surface has somebody to leave out and somebody to share with.
ME = "u_me"
THEM = "u_them"
STRANGER = "u_stranger"

WEB = "web"
SALES = "sales"

AGENT = "support_triage"


# --------------------------------------------------------------------------- fixtures
def an_item(
    item_id: str,
    *,
    owner_id: str = ME,
    level: Visibility = Visibility.PERSONAL,
    department: str = "",
    state: KnowledgeState = KnowledgeState.DRAFT,
    verified_at: datetime | None = None,
    verified_by: str = "",
    review_by: datetime | None = None,
) -> KnowledgeItem:
    """One real knowledge item, built through its own constructor and every validator."""
    return KnowledgeItem(
        item_id=item_id,
        content="what the item says",
        title=f"item {item_id}",
        visibility=KnowledgeVisibility(level=level, owner_id=owner_id, department=department),
        owner_id=owner_id,
        state=state,
        verified_by=verified_by,
        verified_at=verified_at,
        review_by=review_by,
    )


def holding(*capabilities: str, principal: str = ME) -> EntitlementSet:
    """A caller holding these capabilities company-wide."""
    return EntitlementSet(
        principal_id=principal,
        grants=tuple(
            Grant(capability=Capability(value=one), scope=Scope(clauses=())) for one in capabilities
        ),
    )


def holding_over_agent(agent_id: str, *, principal: str) -> EntitlementSet:
    """A reader whose artifact grant reaches one agent's output and nothing else."""
    return EntitlementSet(
        principal_id=principal,
        grants=(
            Grant(
                capability=ARTIFACT_CAPABILITY,
                scope=Scope(clauses=(Clause(field="agent_id", op=Op.EQ, value=agent_id),)),
            ),
            Grant(
                capability=Capability(value="read:console.existence"),
                scope=Scope(clauses=()),
            ),
        ),
    )


def an_artifact(
    artifact_id: str,
    *,
    caller: str = ME,
    agent_id: str = AGENT,
    at: datetime = NOW,
    data_class: DataClass = DataClass.BUSINESS_RECORD,
) -> Artifact:
    """One real artifact, built through `record` so every field the record needs is set."""
    return record(
        artifact_id=artifact_id,
        agent_id=agent_id,
        kind=ArtifactKind.REPORT,
        run_id=f"run_{artifact_id}",
        agent_version="4.2.0",
        caller_id=caller,
        reach=holding("read:client.name", principal=caller),
        at=at,
        inputs=[
            ArtifactInput(
                label="ticket",
                data_class=data_class,
                classification=Classification.INTERNAL,
            )
        ],
    )


def a_skill(name: str = "hosting_expiry", body: str = "Check the renewal date.") -> Skill:
    """One real skill, so a digest is over bytes rather than over a string written here."""
    return Skill(
        name=name,
        version="1.0.0",
        description="Look up when a client's hosting renews and say which plan it is on.",
        body=body,
    )


def a_source(kind: SourceKind = SourceKind.UPLOAD, *, body: str = "x") -> SkillSource:
    """A pinned import of each kind, using the pin that kind actually requires."""
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    if kind is SourceKind.GITHUB:
        return SkillSource(kind=kind, location="acme/skills", commit="a" * 40)
    if kind is SourceKind.URL:
        return SkillSource(
            kind=kind, location="https://example.test/skill.md", content_digest=digest
        )
    return SkillSource(kind=kind, location="skill.md", content_digest=digest)


def an_agent(*, owner_id: str, agent_id: str = AGENT) -> AgentRecord:
    """One agent stewarded by somebody, which is what a personal skill is checked against."""
    return AgentRecord(
        agent_id=agent_id,
        display_name="Support triage",
        persona="Answers support questions in the house voice.",
        audience=AgentAudience(level=Visibility.PERSONAL, owner_id=owner_id),
        authority=AgentAuthority(),
        created_by=owner_id,
    )


# --- ownership is not entitlement (M40.3.1.5, M40.3.1.1) -------------------------------


def test_an_item_you_own_in_a_department_you_have_left_is_not_in_your_library() -> None:
    """**M40.3.1.5.** The leaf says a personal library never shows an item outside this
    person's entitlement, including their own department's restricted rows, and the case that
    makes it real is the one ownership alone gets wrong: `owner_id` never moves and a
    department does, so an item somebody uploaded into Sales and then left is theirs and out
    of their reach.

    Both directions, because a filter tested only by what it removes is satisfied by one that
    removes everything: the same person's Web item, their personal item and a company item all
    survive, and only the Sales one goes. The item somebody else owns goes too, which is the
    ownership half.

    Delete this and a personal library becomes a list of everything a person ever uploaded,
    including the rows their current grants would refuse them on every other screen.
    """
    mine_here = an_item("k_web", level=Visibility.DEPARTMENT, department=WEB)
    mine_elsewhere = an_item("k_sales", level=Visibility.DEPARTMENT, department=SALES)
    mine_personal = an_item("k_personal")
    mine_published = an_item(
        "k_company",
        level=Visibility.COMPANY,
        state=KnowledgeState.PUBLISHED,
        verified_by=THEM,
        verified_at=NOW,
        review_by=LATER,
    )
    theirs = an_item("k_theirs", owner_id=THEM, level=Visibility.COMPANY)

    kept = reachable_own_items(
        [mine_here, mine_elsewhere, mine_personal, mine_published, theirs],
        principal_id=ME,
        departments=[WEB],
    )

    assert [one.item_id for one in kept] == ["k_web", "k_personal", "k_company"]
    assert reaches(mine_elsewhere, ME, [WEB]) is False
    assert reaches(mine_elsewhere, ME, [WEB, SALES]) is True


def test_a_library_row_says_what_the_badge_says_about_the_same_item() -> None:
    """**M40.3.1.1.** Visibility scope, verification date and review due, and the verification
    verdict is `brain.knowledge.item.badge`'s rather than a second comparison of `review_by`
    against `now`. A second reading is how a document comes to be due on one screen and
    current on another, and the reader has no way to tell which is right.

    All three states in one pass, driven by real items rather than by constructing the badge:
    nobody has vouched for the first, the second is verified and inside its cycle, and the
    third is verified and past it. The third is the one that would be wrong if the comparison
    were written here.

    Delete this and a personal library can render every item as verified.
    """
    unverified = an_item("k_1", review_by=LATER)
    fresh = an_item("k_2", verified_by=THEM, verified_at=NOW, review_by=LATER)
    overdue = an_item("k_3", verified_by=THEM, verified_at=NOW - timedelta(days=400), review_by=NOW)

    rows = my_library([unverified, fresh, overdue], principal_id=ME, now=NOW)

    assert [one.verification for one in rows] == [
        VerificationState.UNVERIFIED,
        VerificationState.VERIFIED,
        VerificationState.DUE,
    ]
    assert [one.visibility for one in rows] == [Visibility.PERSONAL] * 3
    assert rows[1].verified_at == NOW
    assert rows[2].review_by == NOW
    assert all(isinstance(one, LibraryEntry) for one in rows)


# --- upload, replace, retire (M40.3.1.2) -----------------------------------------------


def test_an_upload_carries_a_review_cycle_and_cannot_be_given_one_already_behind_us() -> None:
    """**M40.3.1.2.** The leaf says the review cycle is set at upload time, and a cycle in the
    past is the version of that which passes every type check and opens a re-verification task
    on the day the document is written. The second time that happens the notification stops
    being read, which is `brain.knowledge.visibility.propose_promotion`'s own argument.

    The boundary is asserted on both sides of the same instant rather than at some comfortable
    distance from it, because a cycle equal to `now` is due immediately and is exactly what a
    form supplies when somebody types today's date.

    The widening half is `admit_upload`'s and is not restated in the module: an uploader in Web
    asking for company visibility is refused there, and this proves the refusal is still
    reachable through this door rather than having been swallowed.

    Delete this and an upload can arrive with no cycle at all, which is not overdue, it is
    outside the sweep entirely.
    """
    good = upload(
        item_id="k_1",
        content="what it says",
        owner_id=ME,
        review_by=LATER,
        now=NOW,
        uploader_department=WEB,
    )
    assert good.review_by == LATER
    assert good.state is KnowledgeState.DRAFT
    assert good.visibility.level is Visibility.DEPARTMENT

    for behind in (NOW, NOW - timedelta(seconds=1)):
        with pytest.raises(LibraryError, match="not in the future"):
            upload(
                item_id="k_2",
                content="what it says",
                owner_id=ME,
                review_by=behind,
                now=NOW,
                uploader_department=WEB,
            )

    with pytest.raises(VisibilityError):
        upload(
            item_id="k_3",
            content="what it says",
            owner_id=ME,
            review_by=LATER,
            now=NOW,
            requested=Visibility.COMPANY,
            uploader_department=WEB,
        )


def test_a_replacement_with_no_review_cycle_is_refused_before_it_leaves_the_sweep() -> None:
    """**M40.3.1.2.** Version one carries a date and version two is uploaded in a hurry.
    `brain.knowledge.item.due_for_reverification` skips an item whose `review_by` is `None`,
    correctly, so the replacement does not become overdue, it leaves the sweep, and the console
    shows a newer document with no date beside it. The absence reads as freshness.

    The positive case is the same pair with a date, and it asserts what `supersede` returns:
    the predecessor marked and the successor pointing back. The widening refusal is that
    module's and is exercised here to prove it is still reachable, because supersession being
    the promotion path is the failure it exists to prevent.

    Delete this and the one field that keeps a document under review can be dropped by
    uploading a new version of it.
    """
    current = an_item("k_1", level=Visibility.DEPARTMENT, department=WEB, review_by=LATER)
    without = an_item("k_2", level=Visibility.DEPARTMENT, department=WEB)
    with pytest.raises(LibraryError, match="leaves the re-verification sweep"):
        replace(current, without)

    wider = an_item("k_3", level=Visibility.COMPANY, review_by=LATER)
    with pytest.raises(VisibilityError):
        replace(current, wider)

    good = an_item("k_4", level=Visibility.DEPARTMENT, department=WEB, review_by=LATER)
    was, now_is = replace(current, good)
    assert was.state is KnowledgeState.SUPERSEDED
    assert now_is.supersedes == "k_1"
    assert now_is.review_by == LATER


def test_retiring_keeps_the_row_and_refuses_a_withdrawal_of_something_replaced() -> None:
    """**M40.3.1.2.** Retire is a withdrawal that keeps the row, because an answer given last
    month is only explainable while the thing it was drawn from still exists.

    Two refusals with different reasons and both are tested, because a function that refused
    everything would satisfy either one alone. An already-archived item, since a second
    withdrawal in a history that only had one reads as somebody having done it twice; and a
    superseded item, since a reader following the successor would arrive from a version that
    says it was withdrawn.

    Delete this and retire becomes an operation that can be applied twice, or applied to the
    old half of a supersession, and the state column stops meaning anything.
    """
    live = an_item("k_1", review_by=LATER)
    gone = retire(live)
    assert gone.state is KnowledgeState.ARCHIVED
    assert gone.content == live.content

    with pytest.raises(LibraryError, match="already archived"):
        retire(gone)
    with pytest.raises(LibraryError, match="already been replaced"):
        retire(an_item("k_2", state=KnowledgeState.SUPERSEDED))


# --- who reads it (M40.3.1.3) ----------------------------------------------------------


def test_a_usage_count_names_the_document_and_never_the_person_who_read_it() -> None:
    """**M40.3.1.3.** An author asking whether anything reads what they wrote is asking for a
    figure that moves when other people work, which is normally somebody else's activity. It
    is admissible here precisely because nothing on the shape attributes it: the counts run
    over every agent and every reader, and no field anywhere holds a principal.

    The window is asserted at both bounds, because the retrieval that falls a second outside
    it is the one a half-open guess gets wrong, and the unread list is asserted as the exact
    complement, because a pruning list that is not the complement is the list somebody prunes
    from.

    Delete this and the author's page can grow a breakdown by reader, which is the same rows
    with a name attached.
    """
    mine = [an_item("k_1"), an_item("k_2"), an_item("k_3")]
    reads = [
        ItemRetrieval(agent_id="a_1", item_id="k_1", principal_id=THEM, at=NOW),
        ItemRetrieval(agent_id="a_2", item_id="k_1", principal_id=STRANGER, at=NOW),
        ItemRetrieval(agent_id="a_1", item_id="k_2", principal_id=THEM, at=NOW),
        ItemRetrieval(
            agent_id="a_1", item_id="k_2", principal_id=THEM, at=NOW - timedelta(seconds=1)
        ),
        ItemRetrieval(agent_id="a_1", item_id="k_9", principal_id=THEM, at=NOW),
    ]

    usage = authored_usage(reads, within=mine, author_id=ME, since=NOW, until=NOW)

    assert usage.read == (
        AuthoredUse(item_id="k_1", retrievals=2),
        AuthoredUse(item_id="k_2", retrievals=1),
    )
    assert usage.unread == ("k_3",)
    assert usage.author_id == ME
    for holder in (AuthoredUse, AuthorUsage):
        assert not {
            name for name in holder.__dataclass_fields__ if "principal" in name or "reader" in name
        }


# --- asking for company visibility (M40.3.1.4) -----------------------------------------


def test_a_promotion_request_waits_at_the_tier_its_blast_radius_gives_it() -> None:
    """**M40.3.1.4.** "Routed as a tier three decision" is a claim about what has to happen
    before the item is published, and the honest way to hold it is to read the tier out of
    `brain.memory.tiers.BLAST_RADIUS` rather than to write three into a field.

    The tier is asserted against `Tier.GATED` and against `blast_radius`' answer for
    `COMPANY_KNOWLEDGE`, which is the comparison that survives the constant being mutated: a
    request that carried its own number would agree with itself for every value it could hold.

    A request built at any other tier is refused at construction, so a caller assembling the
    dataclass directly cannot lower it either, which is `brain.memory.tiers.Proposal`'s
    construction and the reason it works.

    Delete this and a member's publish button can be lowered to something agreement promotes.
    """
    mine = an_item("k_1", level=Visibility.DEPARTMENT, department=WEB)

    asked = request_promotion(
        mine, proposer_id=ME, review_by=LATER, reason="the handbook page", now=NOW
    )

    assert asked.tier is Tier.GATED
    assert asked.tier is promotion_tier()
    assert asked.proposal.to_level is Visibility.COMPANY
    assert asked.proposal.owner_id == ME
    assert not {
        name
        for name in PromotionRequest.__dataclass_fields__
        if name in {"approver", "approved_at", "decision"}
    }

    with pytest.raises(LibraryError, match="the tier is not"):
        PromotionRequest(proposal=asked.proposal, tier=Tier.PROMOTED)


def test_a_promotion_cannot_be_asked_for_by_somebody_who_does_not_steward_the_item() -> None:
    """**M40.3.1.4.** `brain.knowledge.visibility.propose_promotion` takes an item id and a
    proposer and cannot check the two against each other, because it never sees the item. A
    member control that took the id from a form would therefore propose a widening of somebody
    else's document, and the approval that followed would look entirely correct: there is a
    proposal, there is an approver, and neither of them is the steward.

    The positive half is the same call by the steward, so this is not passing because the
    function refuses everybody.

    Delete this and one person's publish button reaches another person's library.
    """
    theirs = an_item("k_1", owner_id=THEM, level=Visibility.DEPARTMENT, department=WEB)

    with pytest.raises(LibraryError, match="does not steward"):
        request_promotion(theirs, proposer_id=ME, review_by=LATER, reason="publish it", now=NOW)

    allowed = request_promotion(
        theirs, proposer_id=THEM, review_by=LATER, reason="publish it", now=NOW
    )
    assert allowed.proposal.proposer_id == THEM


# --- personal skills (M40.3.2) ---------------------------------------------------------


def test_a_personal_skill_reads_as_approved_only_while_the_bytes_are_unchanged() -> None:
    """**M40.3.2.1.** `brain.tools.skills.SkillState` has three members and none of them
    distinguishes a skill that was approved from one that was approved and then edited: the
    column still says approved while `is_executable` is false. A personal library showing the
    column would tell somebody their skill is ready when nobody has read what is there.

    Driven through `approved_by` rather than by setting a state, and the CHANGED row is built
    with the approval digest of the bytes that were reviewed beside a different body, which is
    the shape that actually reaches a library: `with_content` clears the review, so the row
    that says approved while the bytes have moved is one edited anywhere else. Both are
    asserted, because they are different rows and only one of them is a defect.

    The narrowing is asserted in the same test because it is the other half of the row: a
    colleague's skill in the same list is absent.

    Delete this and a personal library can offer a skill nobody has reviewed as ready to use.
    """
    mine = ImportedSkill(skill=a_skill(), source=a_source())
    approved = mine.approved_by(THEM, NOW)
    resubmitted = approved.with_content(a_skill(body="Check the renewal date and the plan."))
    edited = ImportedSkill(
        skill=a_skill(body="Check the renewal date and the plan."),
        source=a_source(),
        state=SkillState.APPROVED,
        reviewer=THEM,
        reviewed_at=NOW,
        approved_digest=approved.approved_digest,
    )

    rows = my_skills(
        [
            PersonalSkill(owner_id=ME, imported=mine),
            PersonalSkill(owner_id=THEM, imported=approved),
        ],
        principal_id=ME,
    )
    assert rows == (
        SkillRow(
            name="hosting_expiry",
            version="1.0.0",
            origin=Origin.STUDIO,
            location="skill.md",
            review=Review.PENDING,
        ),
    )

    mine_approved = my_skills([PersonalSkill(owner_id=ME, imported=approved)], principal_id=ME)
    mine_edited = my_skills([PersonalSkill(owner_id=ME, imported=edited)], principal_id=ME)
    mine_again = my_skills([PersonalSkill(owner_id=ME, imported=resubmitted)], principal_id=ME)
    assert mine_approved[0].review is Review.APPROVED
    assert mine_edited[0].review is Review.CHANGED
    assert mine_again[0].review is Review.PENDING


def test_a_skill_filed_under_a_route_its_pin_contradicts_is_refused_at_the_door() -> None:
    """**M40.3.2.2.** Three routes, and each is a different pin: bytes with no address, a
    commit, and an https address with a digest. A row claiming a skill was written in the
    studio while carrying a repository pin is a provenance the reviewer reads wrongly, and it
    is one argument out of place rather than an attack.

    The mapping is asserted exhaustive over `Origin` and injective, because a route with no
    kind behind it would be rendered as whichever the lookup returned first, and two routes
    sharing a kind would make `origin_of` answer for the wrong one.

    Delete this and the studio button can file a pasted URL.
    """
    assert set(ORIGIN_SOURCE) == set(Origin)
    assert len(set(ORIGIN_SOURCE.values())) == len(Origin)
    for route, kind in ORIGIN_SOURCE.items():
        assert origin_of(a_source(kind)) is route

    imported = ImportedSkill(skill=a_skill(), source=a_source(SourceKind.URL))
    with pytest.raises(LibraryError, match="contradicts"):
        add_skill(owner_id=ME, imported=imported, origin=Origin.STUDIO)

    ok = add_skill(owner_id=ME, imported=imported, origin=Origin.URL)
    assert ok.owner_id == ME
    assert not set(inspect.signature(add_skill).parameters) & {
        "url",
        "repo",
        "repository",
        "commit",
    }


def test_a_personal_skill_belonging_to_nobody_is_refused_however_it_is_spelled() -> None:
    """**M40.3.2.2.** A personal scope with a blank owner is `Scope()`, which is the
    unrestricted scope, so the narrowest level in the system becomes the widest through an
    empty form field. `brain.knowledge.visibility.scope_for` refuses that and `PersonalSkill`
    has to refuse it too, because it holds the owner rather than a scope.

    Both spellings, and the second is the one a form supplies: a text input somebody tabbed
    past yields `" "` rather than `""`, and a bare falsiness check passes it.

    Delete this and one whitespace character puts a personal skill in everybody's library.
    """
    imported = ImportedSkill(skill=a_skill(), source=a_source())
    for blank in ("", " ", "\t"):
        with pytest.raises(LibraryError, match="belonging to nobody"):
            PersonalSkill(owner_id=blank, imported=imported)
    assert PersonalSkill(owner_id=ME, imported=imported).owner_id == ME


def test_a_skill_a_reviewer_has_already_decided_cannot_be_submitted_again() -> None:
    """**M40.3.2.3.** `ImportedSkill._decided` refuses a second decision because the record of
    who approved what is the entire product of a review. The matching rule on the asking side
    is that a decided skill is not resubmitted: an author who disagrees with a rejection edits
    the skill, and `with_content` clears the review, which is what puts new bytes in the queue.

    Both decided states, because a rejection and an approval reach the queue from different
    directions and only one of them is obviously wrong to resubmit.

    The type is asserted to carry no reviewer and no decision, because submitting is asking,
    and a field is all it would take for the two to become one act by one person.

    Delete this and the queue order in `brain.tools.review.pending`, which is time waited and
    nothing else, can be reset by pressing submit again.
    """
    mine = PersonalSkill(owner_id=ME, imported=ImportedSkill(skill=a_skill(), source=a_source()))
    offered = submit_for_review(mine, at=NOW)
    assert offered == Submission(owner_id=ME, skill_name="hosting_expiry", submitted_at=NOW)
    assert not {
        name
        for name in Submission.__dataclass_fields__
        if name in {"reviewer", "decision", "approved_at"}
    }

    for state in (SkillState.APPROVED, SkillState.REJECTED):
        decided = (
            mine.imported.approved_by(THEM, NOW)
            if state is SkillState.APPROVED
            else mine.imported.rejected_by(THEM, NOW)
        )
        with pytest.raises(LibraryError, match="cannot be submitted again"):
            submit_for_review(PersonalSkill(owner_id=ME, imported=decided), at=NOW)


def test_a_submission_needs_a_name_and_an_aware_instant_to_take_a_place_in_a_queue() -> None:
    """**M40.3.2.3.** `brain.tools.review.pending` orders by how long something has waited and
    has no priority field, deliberately, so the instant on a submission is the only thing
    deciding where it sits. A naive one is wrong by the host's offset from UTC, in whichever
    direction the machine happens to sit, and a submission naming no skill is a queue entry a
    reviewer cannot open.

    Whitespace as well as empty, because the name arrives from a form.

    Delete this and a queue ordered by waiting time can be jumped by a machine in the wrong
    timezone.
    """
    for blank in ("", " "):
        with pytest.raises(LibraryError, match="naming no skill"):
            Submission(owner_id=ME, skill_name=blank, submitted_at=NOW)
    with pytest.raises(LibraryError, match="naive instant"):
        Submission(owner_id=ME, skill_name="hosting_expiry", submitted_at=NOW.replace(tzinfo=None))
    assert Submission(owner_id=ME, skill_name="x", submitted_at=NOW).skill_name == "x"


def test_a_personal_skill_reaches_only_its_owners_agents_until_the_library_takes_it() -> None:
    """**M40.3.2.4.** Two gates and they are different gates. `brain.tools.skills.pin_skill`
    refuses anything a named person has not approved against the bytes that are there, which
    is about the skill; the leaf is about the audience, and it says a personal skill stays on
    its owner's own agents until the department library accepts it.

    Four cases, which is the cross product that matters: unapproved on your own agent,
    approved on your own agent, approved on a colleague's, and approved on a colleague's once
    the library holds it. Only the second and fourth are empty.

    Stewardship rather than authorship, and the colleague's agent is `created_by` its
    colleague as well, so this is not passing on the author field by accident.

    Delete this and a skill nobody outside one person has read can be attached to a
    department's agent.
    """
    mine = ImportedSkill(skill=a_skill(), source=a_source())
    approved = PersonalSkill(owner_id=ME, imported=mine.approved_by(THEM, NOW))
    pending = PersonalSkill(owner_id=ME, imported=mine)
    my_agent = an_agent(owner_id=ME)
    their_agent = an_agent(owner_id=THEM, agent_id="finance_desk")

    assert attach_refusals(pending, my_agent) != ()
    assert attach_refusals(approved, my_agent) == ()
    assert attach_refusals(approved, their_agent) != ()
    assert attach_refusals(approved, their_agent, in_library=True) == ()
    assert attach_refusals(pending, their_agent, in_library=True) != ()


# --- what agents produced for me (M40.3.3.1, M40.3.3.2) --------------------------------


def test_a_personal_output_list_is_narrowed_by_the_person_and_has_no_agent_to_widen_to() -> None:
    """**M40.3.3.1.** "Everything produced for this person by any agent" is
    `brain.console.agent_output.visible_artifacts`' rule turned ninety degrees: that function
    requires an agent id because a listing that could be asked for the whole estate is the
    global pile with an optional filter on it, and here the required narrowing is the person.

    Three things are asserted. Two agents' output for this person appears, so "any agent" is
    real. Somebody else's artifact is absent, whatever the reader holds. And an artifact past
    its horizon is absent, computed from `brain.ops.retention.horizon_for` rather than from a
    number here, which is what actually removes a row from a page of your own things.

    Delete this and the personal page acquires an agent parameter with a default meaning all
    of them, which is the pile again.
    """
    mine_one = an_artifact("a_1", agent_id="agent_one")
    mine_two = an_artifact("a_2", agent_id="agent_two", at=NOW + timedelta(hours=1))
    theirs = an_artifact("a_3", caller=THEM)
    ageing = an_artifact("a_4", data_class=DataClass.PAYLOAD, at=NOW)

    window = horizon_for(DataClass.PAYLOAD).days
    assert window is not None
    reader = holding(principal=ME)

    inside = produced_for_me(
        [mine_one, mine_two, theirs, ageing], principal_id=ME, reader=reader, now=NOW
    )
    assert [one.artifact_id for one in inside] == ["a_2", "a_4", "a_1"]

    after = produced_for_me(
        [mine_one, mine_two, theirs, ageing],
        principal_id=ME,
        reader=reader,
        now=NOW + timedelta(days=window),
    )
    assert [one.artifact_id for one in after] == ["a_2", "a_1"]
    assert "agent_id" not in set(inspect.signature(produced_for_me).parameters)


def test_a_personal_listing_assembled_from_somebody_elses_reach_is_refused() -> None:
    """**M40.3.3.1.** A caller passing a name in one argument and a reach in another can pass
    two different people, and the page would then be assembled from grants belonging to
    somebody who was never asked. It is the mistake that happens once, in a handler with the
    wrong variable in scope, and it is invisible afterwards because both answers are
    internally consistent.

    `brain.knowledge.visibility.approve_promotion` makes the same check about an approver and
    for the same reason. The positive half is the matching pair, so this is not passing
    because the function refuses everything.

    Delete this and one person's page can be rendered out of another person's entitlements.
    """
    mine = an_artifact("a_1")
    with pytest.raises(LibraryError, match="belongs to"):
        produced_for_me([mine], principal_id=ME, reader=holding(principal=THEM), now=NOW)
    assert produced_for_me([mine], principal_id=ME, reader=holding(principal=ME), now=NOW) == (
        mine,
    )


def test_a_re_download_is_decided_now_and_a_control_reaches_only_its_own_page() -> None:
    """**M40.3.3.2.** The download is re-checked at the moment it is asked for, through
    `brain.console.agent_output.may_download`, and there is no parameter a link, a token or a
    signature could arrive through: a signed URL is a bearer token wearing a text field, and
    it survives being pasted into a ticket.

    The narrowing is the addition a member control needs and a console check does not. A
    reader holding an artifact grant over the whole agent may legitimately see somebody else's
    output on the console, and that must not let them operate their own page's download
    control on it, because the row was never on their page.

    The horizon case is the one that actually removes a row for a person downloading their own
    output, and it is computed from `brain.ops.retention` rather than from a number here.

    Delete this and the personal control becomes `may_download` with a friendlier name, which
    answers yes for every artifact its caller holds a grant over.
    """
    mine = an_artifact("a_1", data_class=DataClass.PAYLOAD)
    theirs = an_artifact("a_2", caller=THEM)
    window = horizon_for(DataClass.PAYLOAD).days
    assert window is not None

    assert may_redownload(mine, holding(principal=ME), NOW, principal_id=ME) is True
    assert (
        may_redownload(mine, holding(principal=ME), NOW + timedelta(days=window), principal_id=ME)
        is False
    )
    assert (
        may_redownload(theirs, holding_over_agent(AGENT, principal=ME), NOW, principal_id=ME)
        is False
    )
    with pytest.raises(LibraryError, match="belongs to"):
        may_redownload(mine, holding(principal=THEM), NOW, principal_id=ME)
    assert not set(inspect.signature(may_redownload).parameters) & {
        "link",
        "url",
        "token",
        "signature",
    }


# --- sharing (M40.3.3.3) ---------------------------------------------------------------


def test_a_share_is_refused_where_the_colleague_does_not_already_reach_the_artifact() -> None:
    """**M40.3.3.3.** The leaf, stated the only way it can be enforced at share time: an
    artifact is handed over where the colleague's own entitlement already covers it, and
    refused otherwise.

    Refused rather than accepted-and-useless, which is
    `brain.knowledge.visibility.admit_upload`'s argument: somebody who asked for one thing and
    silently received another believes they did it and never checks. The refusal names neither
    the capability nor the scope.

    The sharer's own reach is checked first, so somebody probing with an artifact id they have
    no business holding is refused before anything about the colleague is evaluated. That
    ordering is asserted by giving the sharer nothing and the colleague everything, and
    reading which message comes back.

    Delete this and a share becomes a pointer to something the recipient cannot open, which
    the sharer believes they sent.
    """
    made = an_artifact("a_1")
    mine = holding(principal=ME)
    reaching = holding_over_agent(AGENT, principal=THEM)
    nothing = holding(principal=THEM)

    handed = share(made, sharer=mine, colleague=reaching, now=NOW)
    assert handed == Share(artifact_id="a_1", shared_by=ME, shared_with=THEM, at=NOW)

    with pytest.raises(LibraryError, match="does not already reach"):
        share(made, sharer=mine, colleague=nothing, now=NOW)

    with pytest.raises(LibraryError, match="nothing for them to pass on"):
        share(made, sharer=holding(principal=STRANGER), colleague=reaching, now=NOW)


def test_a_share_is_admitted_once_and_the_read_is_decided_on_every_open() -> None:
    """**M40.3.3.3.** The question the whole leaf turns on. A share makes something already
    reachable findable and can never make something reachable, so the admission at share time
    confers nothing and the read is decided again on every open.

    The fixture is one colleague across three moments and one unchanged `Share` row. On Monday
    they hold an artifact grant and the open succeeds. On Tuesday the grant is gone and the
    same row, compared field by field to prove it did not move, opens nothing. Past the
    horizon the answer is False for the same reason it is for the artifact's own producer,
    because retention is not a permission and outranks one.

    The widening direction is asserted too, and it is the half that shows the share is inert
    rather than merely weak: a colleague who gains the grant later could already have had the
    artifact, so the share adds nothing to what `may_download` says on its own.

    Delete this and the obvious optimisation, treating the share as the permission it was
    checked against, passes every other test in this file.
    """
    made = an_artifact("a_1", data_class=DataClass.PAYLOAD)
    reaching = holding_over_agent(AGENT, principal=THEM)
    handed = share(made, sharer=holding(principal=ME), colleague=reaching, now=NOW)

    assert open_share(handed, made, recipient=reaching, now=NOW) is True

    narrowed = holding(principal=THEM)
    assert open_share(handed, made, recipient=narrowed, now=NOW) is False
    assert handed == Share(artifact_id="a_1", shared_by=ME, shared_with=THEM, at=NOW)

    window = horizon_for(DataClass.PAYLOAD).days
    assert window is not None
    assert open_share(handed, made, recipient=reaching, now=NOW + timedelta(days=window)) is False


def test_a_stranger_whose_grants_hash_to_the_record_is_still_refused_a_share() -> None:
    """**M40.3.3.3.** The discriminating case `brain.console.agent_output` uses for the same
    rule, carried onto the sharing path because sharing is where somebody would be tempted to
    compare the recipient against what produced the artifact.

    The stranger holds exactly the grants the producing run held, so their `ent_hash` equals
    the one on the record, and they still reach nothing: they hold no artifact grant and it is
    not their artifact. A check written against the hash would admit them and would look
    entirely correct doing it, on this path as on the download path.

    Delete this and "the recipient was as entitled as the producer" becomes a reasonable
    implementation of a rule about the recipient's own reach.
    """
    made = an_artifact("a_1")
    same_grants = holding("read:client.name", principal=STRANGER)
    assert same_grants.ent_hash() == made.entitlement_hash

    with pytest.raises(LibraryError, match="does not already reach"):
        share(made, sharer=holding(principal=ME), colleague=same_grants, now=NOW)


def test_a_share_carries_nothing_a_read_could_consult() -> None:
    """**M40.3.3.3.** The structural half of "sharing does not grant". A rule that a share is
    inert holds until somebody adds a field to save a lookup, and the field arrives with a
    name like `entitlement_hash` or `token` on it, added by whoever is making the open path
    faster rather than by anybody being careless.

    Asserted on the declared fields rather than on the paragraph, and the diagnostic is driven
    with a doctored type as well, so the check itself is exercised rather than merely being
    green against a healthy module.

    Delete this and the next reader adds the producing run's hash to the row and compares it.
    """
    assert set(Share.__dataclass_fields__) == {"artifact_id", "shared_by", "shared_with", "at"}

    @dataclass(frozen=True)
    class Doctored:
        artifact_id: str = ""
        entitlement_hash: str = ""
        token: str = ""

    findings = library_gaps(share_type=Doctored)
    assert len(findings) == 2
    assert all("would put a permission on a share" in one for one in findings)


def test_a_share_cannot_be_opened_by_whoever_happens_to_be_holding_it() -> None:
    """**M40.3.3.3.** A share is not a bearer token, and the two ways it would become one are
    a recipient who is not the person it was made out to, and an artifact that is not the one
    it names. Both are caller faults rather than answers, so both raise: reporting either as a
    False would hide it behind a screen that reads as working.

    The artifact mismatch is the subtler of the two. A page rendering one row's permission
    beside another row's bytes is a permission decision about the wrong file, and it arrives
    as a loop that reused a variable.

    Delete this and the verdict reached about one artifact can be shown beside another.
    """
    made = an_artifact("a_1")
    other = an_artifact("a_2")
    reaching = holding_over_agent(AGENT, principal=THEM)
    handed = share(made, sharer=holding(principal=ME), colleague=reaching, now=NOW)

    with pytest.raises(LibraryError, match="names 'a_1'"):
        open_share(handed, other, recipient=reaching, now=NOW)
    with pytest.raises(LibraryError, match="not a bearer token"):
        open_share(handed, made, recipient=holding_over_agent(AGENT, principal=STRANGER), now=NOW)


def test_a_share_naming_nobody_or_naming_one_person_twice_is_refused() -> None:
    """**M40.3.3.3.** Three identifiers and each of them arrives from a form, so each is
    checked for whitespace as well as for emptiness: a bare falsiness check passes `" "`, and
    a share with a space for a recipient is a row on somebody's page addressed to nobody.

    Sharing with yourself is refused separately, because it is not a permission failure: it is
    a bookmark wearing the word shared, and it renders on a page as somebody else having been
    given something.

    The instant is checked too, since a share is ordered against the artifact's own horizon
    and a naive one is out by the host's offset.

    Delete this and one tabbed-past form field produces a share nobody can open and nobody can
    find.
    """
    for name in ("artifact_id", "shared_by", "shared_with"):
        for blank in ("", " "):
            fields = {"artifact_id": "a_1", "shared_by": ME, "shared_with": THEM, "at": NOW}
            fields[name] = blank
            with pytest.raises(LibraryError, match=f"no {name}"):
                Share(**fields)  # type: ignore[arg-type]

    with pytest.raises(LibraryError, match="with themselves"):
        Share(artifact_id="a_1", shared_by=ME, shared_with=ME, at=NOW)
    with pytest.raises(LibraryError, match="no timezone"):
        Share(artifact_id="a_1", shared_by=ME, shared_with=THEM, at=NOW.replace(tzinfo=None))


# --- the diagnostic and the note -------------------------------------------------------


def test_the_diagnostic_reports_every_way_this_surface_could_widen_or_decide() -> None:
    """The deployment check is green and that proves nothing, which is why every branch is
    driven with a constructed input as well. `brain.ops.starter.starter_gaps` records the same
    argument: a diagnostic that can only read the healthy module has nothing to report, so
    switching off any of its refusals survives every mutation.

    Six branches beyond the share one already covered: a hidden count, a request that carries
    its own answer, a sharing path that reaches several people at once, a download that could
    be handed a link, a route with no import kind behind it, and a promotion whose blast
    radius has stopped being gated.

    The last of those is here because a mutation survived without it. The tier check read the
    module's own constant, so its only failing state was a tree where `BLAST_RADIUS` had
    already been lowered, which no fixture can build; handed a change that is genuinely not
    gated, the branch is reachable and switching it off is visible.

    Delete this and `library_gaps` becomes a function that returns an empty tuple.
    """
    assert library_gaps() == ()

    @dataclass(frozen=True)
    class Counting:
        total: int = 0

    @dataclass(frozen=True)
    class Deciding:
        approver_id: str = ""

    def bulk(one: object, *, colleagues: list[str]) -> None:
        """A sharing path over a list, which is the oracle in one call."""

    def linked(one: object, *, token: str) -> bool:
        """A download check a stored link could decide."""
        return bool(token)

    assert library_gaps(surface=[Counting]) == (
        "Counting.total would tell a reader how much they were not shown",
    )
    assert len(library_gaps(request_types=[Deciding])) == 1
    assert "colleagues" in library_gaps(sharing=[bulk])[0]
    assert "token" in library_gaps(download=linked)[0]
    assert len(library_gaps(origins={})) == len(Origin)
    assert blast_radius(Change.PREFERENCE) is not Tier.GATED
    assert library_gaps(promotion_change=Change.PREFERENCE) == (
        "preference no longer waits for a person, so asking for a document to be published "
        "company-wide would be granted by whatever counts agreement",
    )


def test_the_producers_own_download_is_admitted_before_any_grant_is_read() -> None:
    """The finding `library_notes` reports, held as a test so it cannot quietly stop being
    true in either direction.

    `brain.console.agent_output.may_see` returns True when the artifact's `caller_id` is the
    reader, before it looks at a grant, and `may_download` is the expiry check and then
    `may_see`. So somebody whose grants were revoked entirely can still fetch what their own
    run produced until the retention horizon passes, and every surface built on that check,
    including this one, inherits it. It is a deliberate decision in that module, argued as
    findability, and this is the assertion that makes it visible from here.

    Delete this and either the note goes stale silently, or the branch changes and nothing
    tells the reader of this module that their re-download check started doing more work.
    """
    made = an_artifact("a_1", data_class=DataClass.PAYLOAD)
    revoked = EntitlementSet(principal_id=ME, grants=())
    assert may_redownload(made, revoked, NOW, principal_id=ME) is True

    window = horizon_for(DataClass.PAYLOAD).days
    assert window is not None
    assert may_redownload(made, revoked, NOW + timedelta(days=window), principal_id=ME) is False
    assert len(library_notes()) == 1
    assert "caller branch" in library_notes()[0]
