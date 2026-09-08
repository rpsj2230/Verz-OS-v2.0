"""The digest, held to the three things an email must not do.

It must not carry a gated change, because an undo button beside a scope widening is a person
approving one by pressing something that says undo. It must not say how much it did not show,
because a filtered list beside a total is a subtraction. And it must not do anything the
second time it is clicked, because an email is clicked twice and clicked late.

Real `EntitlementSet`s and real `Proposal`s throughout, never a stand-in. The rule under test
is composed from `intersect`, `scope_for` and `Scope.matches` by way of `formation.may_recall`,
and a fake implementing those would be a test of the fake. Every hiding test has a sibling
proving the permitted rows still come through, because a listing tested only by what it hides
is satisfied by a function that returns nothing.

Task ids: M16.5.1
"""

from __future__ import annotations

from dataclasses import fields as dataclass_fields
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.memory import digest as digest_module
from brain.memory.correction import Correction, Demotion, Supersession
from brain.memory.digest import (
    COUNTING_FIELD_NAMES,
    DIGEST_PERIOD,
    DIGEST_TIERS,
    Learning,
    MemoryItem,
    Undo,
    WeeklyDigest,
    digest_gaps,
    evidence_from,
    may_digest,
    undo,
    weekly_digest,
)
from brain.memory.formation import RECALL_FLOOR, Formation, clause_place, confidence_now
from brain.memory.signals import Observation, Signal
from brain.memory.tiers import BLAST_RADIUS, CHANGES_WHAT_ANYBODY_MAY_SEE, Change, Tier, propose

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
WEB = clause_place(department="web")
FINANCE = clause_place(department="finance")
REPO = Path(__file__).resolve().parents[2]


def reader(
    *capabilities: str,
    scope: Scope = WEB,
    principal_id: str = "p_reader",
) -> EntitlementSet:
    return EntitlementSet(
        principal_id=principal_id,
        grants=tuple(Grant(capability=Capability(value=one), scope=scope) for one in capabilities),
    )


def learning(
    memory_id: str,
    change: Change = Change.PREFERENCE,
    *,
    at: datetime = NOW,
    scope: Scope = WEB,
    capability: str = "read:client.name",
    evidence: frozenset[Signal] = frozenset(),
    replaced_id: str | None = None,
    agent_id: str | None = None,
) -> Learning:
    return Learning(
        memory_id=memory_id,
        proposal=propose(change, subject=f"subject:{memory_id}"),
        formation=Formation(
            principal_id="p_writer",
            capabilities=(Capability(value=capability),),
            scope=scope,
            ent_hash="0" * 32,
            formed_at=at,
        ),
        evidence=evidence,
        replaced_id=replaced_id,
        agent_id=agent_id,
    )


def ids(digest: WeeklyDigest) -> tuple[str, ...]:
    return tuple(one.memory_id for one in digest.entries)


# ----------------------------------------------------------------- what the digest carries
def test_tier_one_and_tier_two_learning_reaches_a_reader_who_still_holds_it() -> None:
    """**The positive case, and without it every refusal below is satisfied by a
    `weekly_digest` that returns nothing.**

    Both tiers, because the digest is tier one *and* tier two: an implementation narrowed to
    tier one would pass every hiding test in this file while silently dropping every fast-path
    rule and procedural shortcut the system promoted this week, which are the learnings most
    worth a person's attention because they answer without a model.

    Delete this and the whole file is green for a digest that shows nobody anything."""
    week = weekly_digest(
        now=NOW,
        reader=reader("read:client.name"),
        learnings=[
            learning("m_pref", Change.PREFERENCE),
            learning("m_rule", Change.FAST_PATH_RULE),
        ],
    )

    assert set(ids(week)) == {"m_pref", "m_rule"}
    assert {one.tier for one in week.entries} == {Tier.AUTOMATIC, Tier.PROMOTED}
    assert week.reader_id == "p_reader"


def test_a_gated_learning_is_never_in_an_email_with_an_undo_button_in_it() -> None:
    """**M16.5.1 is tier one and two, and the gap between two and three is the whole point.**

    Tier three changes who may see what and `tiers.propose` has nowhere to approve one. Put a
    scope widening in a weekly email and the undo button next to it is a control a person
    presses without knowing they have decided an access question, which is exactly the mixing
    the tier split exists to prevent.

    The permitted row is asserted in the same call, so this cannot be satisfied by an empty
    digest.

    Delete this and a capability addition arrives by email with a one-click control beside
    it."""
    week = weekly_digest(
        now=NOW,
        reader=reader("read:client.name"),
        learnings=[
            learning("m_pref", Change.PREFERENCE),
            learning("m_widen", Change.SCOPE_WIDENING),
            learning("m_capability", Change.CAPABILITY_ADDITION),
        ],
    )

    assert ids(week) == ("m_pref",)
    assert may_digest(learning("m_widen", Change.SCOPE_WIDENING)) is False


def test_a_session_learning_is_reported_to_nobody() -> None:
    """Tier zero never leaves the conversation, so nothing outside it can be wrong because of
    it, and telling somebody about a change confined to the conversation they are having is
    noise that trains them to ignore the notices that matter.

    This is the test that isolates the *lower* bound of the tier filter: a session learning is
    not in `CHANGES_WHAT_ANYBODY_MAY_SEE`, so the access guard does not catch it and only the
    tier does.

    Delete this and the digest fills with rows nobody can act on, and the ones that matter
    stop being read.

    Delete this and removing the tier check survives, because every other exclusion in this
    file is also caught by the access guard."""
    week = weekly_digest(
        now=NOW,
        reader=reader("read:client.name"),
        learnings=[
            learning("m_session", Change.SESSION_CONTEXT),
            learning("m_pref", Change.PREFERENCE),
        ],
    )

    assert ids(week) == ("m_pref",)


def test_a_change_that_widens_access_stays_out_whatever_its_blast_radius_claims(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**The second, independent refusal, and the one that isolates it.**

    `may_digest` refuses a change in `CHANGES_WHAT_ANYBODY_MAY_SEE` before it looks at the
    tier at all. With `BLAST_RADIUS` intact both guards catch a scope widening, so removing
    either one survives; with one row of the map lowered, only the access guard is left.

    A lowered row is not a hypothetical. `BLAST_RADIUS` is a thirteen-line table edited by
    hand, and `tier_gaps` reports the mistake rather than preventing it, so a run between the
    edit and the sweep is a run in which a scope widening is tier one.

    The map is patched rather than edited, so the module is left as it is and the test says
    what a broken row looks like rather than requiring one.

    Delete this and the access guard can be removed with the file green, and the day a row is
    mistyped a capability addition is mailed to everybody who reaches it."""
    lowered = dict(BLAST_RADIUS)
    lowered[Change.SCOPE_WIDENING] = Tier.AUTOMATIC
    monkeypatch.setattr("brain.memory.tiers.BLAST_RADIUS", lowered)

    mis_tiered = learning("m_widen", Change.SCOPE_WIDENING)
    assert mis_tiered.proposal.tier is Tier.AUTOMATIC, "the patch did not take"

    week = weekly_digest(
        now=NOW,
        reader=reader("read:client.name"),
        learnings=[mis_tiered, learning("m_pref", Change.PREFERENCE)],
    )

    assert ids(week) == ("m_pref",)
    assert any("one button away" in one for one in digest_gaps()), digest_gaps()


def test_every_change_the_digest_admits_is_one_that_changes_nobody_reach() -> None:
    """The property behind the tier filter, checked against a list written out by hand rather
    than against the tier set it is derived from.

    `CHANGES_WHAT_ANYBODY_MAY_SEE` is deliberately not derived from `BLAST_RADIUS`, so this
    compares the digest's admission against something that has to be edited on purpose. A
    version of this test that recomputed the tier set and compared it with itself would be
    green for every value the set could hold.

    Delete this and the two can drift past each other with nothing reporting it."""
    for change in Change:
        if change in CHANGES_WHAT_ANYBODY_MAY_SEE:
            assert not may_digest(learning("m", change)), f"{change.value} reaches an email"

    assert Tier.GATED not in DIGEST_TIERS
    assert Tier.SESSION not in DIGEST_TIERS
    assert digest_gaps() == ()


def test_the_digest_window_is_half_open_so_nothing_arrives_in_two_emails() -> None:
    """A closed interval puts a learning formed exactly on the boundary into two consecutive
    digests, and the second is an undo button for something the reader already decided about,
    which reads as the system having learnt the same thing twice.

    The future case is here too: clock skew between a writer and a reader is ordinary, and a
    digest whose first entry has not happened yet is the strangest possible thing to hand
    somebody on a Monday.

    Delete this and the boundary moves whenever the arithmetic is rewritten, and nobody
    notices until a reader complains about seeing the same row twice."""
    week = weekly_digest(
        now=NOW,
        reader=reader("read:client.name"),
        learnings=[
            learning("m_on_the_edge", at=NOW - DIGEST_PERIOD),
            learning("m_just_inside", at=NOW - DIGEST_PERIOD + timedelta(seconds=1)),
            learning("m_now", at=NOW),
            learning("m_last_week", at=NOW - DIGEST_PERIOD - timedelta(days=1)),
            learning("m_future", at=NOW + timedelta(hours=1)),
        ],
    )

    assert set(ids(week)) == {"m_just_inside", "m_now"}
    assert week.covers_from == NOW - DIGEST_PERIOD
    assert week.covers_to == NOW


def test_a_reader_is_not_told_a_learning_they_no_longer_reach_exists() -> None:
    """A digest is a disclosure and is entitled like any other. A learning formed under
    finance's capabilities, mailed to somebody who reaches only web, is the failure
    `brain.memory.formation` exists to prevent arriving through an email instead of an answer.

    The web row is asserted in the same call, so a `weekly_digest` that refuses everybody
    cannot pass.

    Delete this and the entitlement filter can be removed, and the digest becomes a weekly
    list of what the system learnt from everybody's conversations."""
    week = weekly_digest(
        now=NOW,
        reader=reader("read:client.name", scope=WEB),
        learnings=[
            learning("m_web", scope=WEB),
            learning("m_finance", scope=FINANCE),
            learning("m_other_capability", capability="read:client.contract_value"),
        ],
    )

    assert ids(week) == ("m_web",)


def test_the_digest_is_newest_first_in_an_order_that_does_not_move() -> None:
    """A digest is read from the top and abandoned partway down, so the thing most likely to
    still be wrong goes where it will be read. Ties break on the memory id, so two learnings
    written in one transaction come back in a fixed order rather than whichever the store
    returned.

    Delete this and the order becomes the caller's, which is not an order, and a reader who
    reopens the email loses their place."""
    week = weekly_digest(
        now=NOW,
        reader=reader("read:client.name"),
        learnings=[
            learning("m_older", at=NOW - timedelta(days=2)),
            learning("m_newest", at=NOW),
            learning("m_tie_b", at=NOW - timedelta(days=1)),
            learning("m_tie_a", at=NOW - timedelta(days=1)),
        ],
    )

    assert ids(week) == ("m_newest", "m_tie_a", "m_tie_b", "m_older")


# ------------------------------------------------------------------- what it does not carry
def test_no_shape_in_the_digest_carries_a_count_of_what_it_did_not_show() -> None:
    """**"Showing twelve of forty" tells the reader there are twenty-eight memories about them
    they may not see, which is twenty-eight facts they did not have.**

    Asserted on the dataclass fields rather than on rendered text, because the field is what a
    later renderer finds and uses: a total that exists on the model is a total that appears on
    the page the first time somebody is asked to make the digest feel complete.

    The integer check is the general form of the same rule. `tier` is the one integer-valued
    field on these shapes and it is an ordering rather than a count, so it is named here
    instead of being allowed by accident.

    Delete this and `total` arrives, and it will be added by somebody making the email look
    finished."""
    for model in (Learning, MemoryItem, WeeklyDigest, Undo):
        for one in dataclass_fields(model):
            assert one.name not in COUNTING_FIELD_NAMES, f"{model.__name__} carries {one.name}"
            assert one.type not in ("int", "int | None"), (
                f"{model.__name__}.{one.name} is an integer, which on a filtered listing is a "
                "count of something"
            )

    assert {one.name for one in dataclass_fields(MemoryItem)} & {"tier"} == {"tier"}
    assert digest_gaps() == ()


def test_evidence_names_what_was_noticed_and_never_whose_conversation_it_was() -> None:
    """An `Observation` carries a conversation id, a message id and the principal it happened
    for, so somebody can go back and read what was said under that conversation's own
    permissions. In a listing rendered for a different reader those three fields are the
    disclosure: the conversation id says a conversation exists and the principal id says whose
    it was, which turns a memory tab into a note about who the system learns from.

    A set rather than a sequence, so four re-asks are one piece of evidence that answers were
    re-asked rather than a count of how many times somebody had to ask again.

    Built from real `Observation`s rather than from a set of signals, because the producer is
    what is under test: a test handing `evidence_from` the kinds it is supposed to extract
    would be a test of `frozenset`.

    Delete this and the conversation ids travel into the listing, and the first renderer to
    find them will link them, because a link is obviously useful."""
    observations = [
        Observation(
            signal=Signal.REASKED,
            conversation_id="c_private",
            message_id="msg_1",
            principal_id="p_someone_else",
            at=NOW,
        ),
        Observation(
            signal=Signal.REASKED,
            conversation_id="c_other",
            message_id="msg_2",
            principal_id="p_someone_else",
            at=NOW,
        ),
        Observation(
            signal=Signal.CONTRADICTED,
            conversation_id="c_third",
            message_id="msg_3",
            principal_id="p_third",
            at=NOW,
        ),
    ]

    evidence = evidence_from(observations)

    assert evidence == frozenset({Signal.REASKED, Signal.CONTRADICTED})
    rendered = repr(
        weekly_digest(
            now=NOW,
            reader=reader("read:client.name"),
            learnings=[learning("m_pref", evidence=evidence)],
        )
    )
    for leaked in ("c_private", "c_other", "c_third", "msg_1", "p_someone_else", "p_third"):
        assert leaked not in rendered, f"{leaked} reached the listing"


# ------------------------------------------------------------------------------- one click
def test_undoing_a_learning_that_replaced_something_restores_what_it_replaced() -> None:
    """Undo is a mark and the mark is a `Supersession` read in the other direction: the new
    memory is superseded *by* the one it replaced, so the earlier statement comes back and the
    later one stops being recalled.

    Nothing is removed. `brain.memory.correction` argues the case at length and this is the
    surface where the argument is most easily lost, because the button says undo.

    Delete this and undo restores nothing, which is a control that silently discards a
    memory."""
    result = undo(learning("m_new", replaced_id="m_old"), at=NOW)

    assert isinstance(result.correction, Supersession)
    assert result.correction.superseded_id == "m_new"
    assert result.correction.by_id == "m_old"
    assert result.correction.prompted_by is Signal.REJECTED
    assert result.took_effect is True


def test_undoing_a_learning_that_replaced_nothing_marks_it_rather_than_removing_it() -> None:
    """There is nothing to restore, so the honest correction is a demotion: zero confidence
    at once, flagged, and still on the record.

    Immediate rather than scored down, which is `THE_SOURCE_DOES_NOT_WAIT_FOR_A_THRESHOLD`
    applied to the one source more authoritative than the database, which is the person the
    system learnt it from telling it not to.

    The field carries `Proposal.subject`, which is an opaque reference rather than a value,
    because `Demotion` refuses a blank field and the subject is the only thing a learning
    knows about itself.

    Delete this and the branch for a learning with nothing behind it either raises or removes
    something, and both are wrong in ways nobody sees until somebody presses the button."""
    one = learning("m_alone")
    result = undo(one, at=NOW)

    assert isinstance(result.correction, Demotion)
    assert result.correction.memory_id == "m_alone"
    assert result.correction.field == one.proposal.subject
    assert result.correction.confidence == 0.0
    assert result.correction.confidence < RECALL_FLOOR


def test_undoing_twice_does_nothing_the_second_time() -> None:
    """An email gets clicked twice by somebody who does not remember the first click. A second
    correction written then is a second row saying the same thing at best, and at worst it is
    the row that reverses the first.

    Delete this and the undo control is safe exactly once, which is not a property anybody can
    rely on in an artefact that is forwarded."""
    one = learning("m_alone")
    first = undo(one, at=NOW)
    assert isinstance(first.correction, Demotion)

    second = undo(one, at=NOW + timedelta(minutes=1), demotions=[first.correction])

    assert second.correction is None
    assert second.took_effect is False
    assert second.memory_id == "m_alone"


def test_a_late_undo_does_not_reverse_the_correction_that_got_there_first() -> None:
    """**The case the idempotency is actually for.** The click arrives a week after the email,
    by which time something else has superseded the same memory. Undoing then must not undo
    *that*: the memory that did the superseding is not named anywhere in the result and no
    correction is written about it.

    Delete this and a click on a week-old email brings a corrected memory back into recall,
    which presents as the system changing its mind on its own."""
    one = learning("m_new", replaced_id="m_old")
    something_else = Supersession(
        superseded_id="m_new",
        by_id="m_newer_still",
        prompted_by=Signal.CONTRADICTED,
        at=NOW,
    )

    late = undo(one, at=NOW + timedelta(days=7), supersessions=[something_else])

    assert late.correction is None
    assert "m_newer_still" not in late.reason
    assert "m_old" not in late.reason


def test_nothing_in_the_digest_module_removes_a_memory() -> None:
    """Deleting is the one operation that makes the previous behaviour unexplainable, and a
    digest is where it arrives, because the button says undo and undo sounds like it makes
    something go away.

    Checked over the module's own public names, because the property is about the whole module
    rather than about one function, and because the first thing anybody writes when asked to
    make undo feel final is the thing that removes the row.

    Delete this and `discard` arrives, and it will be described as what the user expected.

    A supersession restores rather than removes, which the two branches above pin; this pins
    that there is no third branch."""
    public = {name for name in dir(digest_module) if not name.startswith("_")}

    for forbidden in ("delete", "remove", "forget", "purge", "clear", "drop", "erase"):
        assert forbidden not in public, f"the module exposes {forbidden}"

    assert {one.value for one in Correction} == {"superseded", "demoted"}
    assert {one.name for one in dataclass_fields(Undo)} == {"memory_id", "correction", "reason"}


def test_a_learning_cannot_claim_to_have_replaced_itself() -> None:
    """Undoing it would write a supersession that is a loop the recall path would follow, and
    a correction nobody can undo because the memory that would restore it is the one that
    replaced it.

    Refused where the record is built rather than where the correction is written, because by
    then the mistake is a field somebody set hours earlier and the traceback names
    `correction` instead.

    Delete this and a record built from a variable that was not reassigned reaches `undo`, and
    `Supersession` refuses it in front of a person who has just pressed a button."""
    with pytest.raises(ValueError, match="cannot have replaced itself"):
        learning("m_same", replaced_id="m_same")


# ------------------------------------------------------------------------ the week itself
def test_the_digest_period_is_short_enough_that_undo_still_does_something(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**The period is anchored outside itself, which is what makes a week a decision rather
    than a habit.**

    A digest reporting learnings that have already decayed below `formation.RECALL_FLOOR` is a
    list of undo buttons that change nothing anybody would notice, so a memory formed at the
    start of the window has to still be reachable at the end of it. That property reads
    `HALF_LIFE_DAYS` and `RECALL_FLOOR` from another module, so it cannot be satisfied by
    moving `DIGEST_PERIOD` and the assertion together.

    The second half watches the diagnostic actually report something. A `digest_gaps` nobody
    has seen return a row is a `digest_gaps` nobody can rely on, and this check is the one
    that would otherwise be green whether it existed or not.

    Delete this and the period can be lengthened to a month for convenience, and the oldest
    entries in every email will be for memories the system stopped using before it sent it."""
    assert confidence_now(1.0, formed_at=NOW - DIGEST_PERIOD, now=NOW) >= RECALL_FLOOR

    monkeypatch.setattr("brain.memory.digest.DIGEST_PERIOD", timedelta(days=90))

    gaps = digest_gaps()

    assert any("below the retrieval floor" in one for one in gaps), gaps
    assert any("changes nothing" in one for one in gaps), gaps


def test_digest_gaps_reports_a_tier_boundary_and_a_total_that_should_not_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**Two branches of `digest_gaps` that no other test in this file has ever watched
    report anything, which makes them two branches nobody can rely on.**

    Every other test calls `digest_gaps` on a healthy module and asserts an empty tuple, which
    passes whether the branches are there or not: the field check duplicates an assertion made
    directly above it, and the tier-boundary check cannot fire while `DIGEST_TIERS` is
    derived. Both are worth keeping, because a later editor writing the tier set out by hand
    or adding a field is exactly who they are for, and neither would be caught by the test
    that looks at the shipped module.

    The names are patched rather than edited, so this says what a broken module looks like
    instead of requiring one.

    Delete this and the two checks can both be removed with the file green."""
    monkeypatch.setattr("brain.memory.digest.DIGEST_TIERS", frozenset(Tier))
    monkeypatch.setattr("brain.memory.digest.COUNTING_FIELD_NAMES", frozenset({"confidence"}))

    gaps = digest_gaps()

    assert any("include the gate or the session" in one for one in gaps), gaps
    assert any("MemoryItem carries confidence" in one for one in gaps), gaps


def _callers_of(*surfaces: str) -> list[str]:
    """Every module outside `brain.memory` that imports one of these surfaces, as dotted names.

    By import line rather than by call site, because the first thing a caller does is import,
    and a module that has imported a listing and not yet called it is already the state this
    guard exists to notice.

    Dotted module names rather than a path and a line number, so that editing a docstring in a
    caller does not fail this test with a message about a line that moved.
    """
    found = {
        ".".join(path.relative_to(REPO / "src").with_suffix("").parts)
        for path in (REPO / "src").rglob("*.py")
        if "memory" not in path.parts[-2:]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith(("import ", "from ")) and any(one in line for one in surfaces)
    }
    return sorted(found)


def test_the_one_surface_with_a_caller_reads_the_agent_tab_at_the_run_reach() -> None:
    """**The successor to the gap this file used to record**, and it is here rather than in
    the caller's own test file on purpose: the guard belongs beside the thing being guarded,
    so a second caller written by somebody who never opens `tests/unit/test_reach_view.py`
    still lands on it.

    `brain.memory.digest` had no caller anywhere in `src` until `brain.console.reach_view`
    arrived. What that module has to get right is the argument rather than the listing: an
    agent tab is read at `E_run(caller, agent) = E(caller) intersect agent_ceiling`, so a
    memory formed under a capability the agent's ceiling does not cover is absent from the
    agent's tab however much the caller reaches on their own.

    Driven through the real `separate_memory`, `run_reach` and `may_recall` rather than
    asserted about a signature, because the failure being guarded is a caller that passes the
    caller's own entitlement set where the run's belongs, and that failure has the right
    signature.

    Delete this and the day somebody wires a second memory tab they will wire the half they
    can see, which is the listing rather than the entitlement argument it takes."""
    from brain.agents.model import AgentAudience, AgentAuthority, AgentRecord, entitlement_ceiling
    from brain.console.reach_view import run_reach, separate_memory
    from brain.knowledge.visibility import Visibility

    agent = AgentRecord(
        agent_id="support_triage",
        display_name="Support triage",
        persona="Answers support questions in the house voice.",
        audience=AgentAudience(level=Visibility.PERSONAL, owner_id="p_reader"),
        authority=AgentAuthority(
            scope=Scope.unrestricted(),
            capabilities=(Capability(value="read:client.name"),),
        ),
        created_by="p_reader",
    )
    caller = reader("read:client.name", "read:ticket.status")
    outside_the_ceiling = learning(
        "m_1", capability="read:ticket.status", agent_id="support_triage"
    )
    view = separate_memory(
        now=NOW,
        caller=caller,
        record=agent,
        subject_id="p_writer",
        learnings=[outside_the_ceiling],
    )

    assert run_reach(caller, agent) == caller.intersect(entitlement_ceiling(agent))
    assert view.per_agent == ()
    assert [one.memory_id for one in view.per_person] == ["m_1"]


def test_no_second_caller_of_a_memory_listing_has_arrived_unargued() -> None:
    """**The honest gap, still asserted, and now narrowed to what is genuinely uncalled.**

    `weekly_digest`, `agent_memory`, `department_memory` and `review_queue` are correct,
    tested and reachable by nothing: there is no route on the router in `brain.api_routes`, no
    scheduled job that would send a digest, and no producer anywhere that assembles a
    `Learning`, so `undo` still returns a `Supersession` that nothing can write down.

    What changed is that `brain.memory.digest`'s shapes now have exactly one importer, which
    the test above holds to passing the run's reach rather than the caller's. The set is
    pinned rather than counted, so a second importer fails here and has to be argued and given
    a sibling of that test rather than being absorbed into a number.

    **`brain.console.own_things` is the second importer and it arrived on 2026-09-08**, for
    M33.3.1.4, "their own memory with a delete control". It is the first caller of
    `brain.memory.review` anywhere. The test below is its sibling and the argument is that it
    is not a reach question at all: a personal memory tab is narrowed by authorship, so that
    module takes no `EntitlementSet` and cannot be wired at the wrong reach because it has
    none. What it does take is a principal, and the delete control refuses somebody else's.

    **`brain.console.govern_estate` is the third importer and it arrived on 2026-09-08**, for
    M27.3.17, the governance memory viewer. Its sibling is below and the argument is the third
    of the three: it does take an `EntitlementSet`, and it reads at the caller's own reach
    rather than at the run's, because a governance memory screen is about a person and not
    about an agent. `separate_memory` already reaches that answer for its own per-person half,
    in that module's words: narrowing a person's memory by an agent's ceiling would hide a
    memory from its own subject for a reason that has nothing to do with them.

    Delete this and the gap stops being visible, and a listing gets wired at the wrong reach
    by somebody who saw that a caller already existed and assumed the question was settled."""
    assert _callers_of("brain.memory.review") == ["brain.console.own_things"]
    assert _callers_of("brain.memory.digest") == [
        "brain.console.govern_estate",
        "brain.console.own_things",
        "brain.console.reach_view",
    ]


def test_the_governance_memory_viewer_reads_one_subject_at_the_callers_own_reach() -> None:
    """The sibling the pin above demands, for the third importer of these shapes.

    **Two claims, and the second is the one a screen gets wrong.** It reads at the caller's
    own reach and never at `E_run`, which is `separate_memory`'s decision for its per-person
    half: a governance screen about what is remembered about a person is not the agent's
    memory, and narrowing it by an agent's ceiling would hide a memory from its own subject
    for a reason that has nothing to do with them. And it computes no reach of its own; the
    recall verdict is `brain.memory.formation.may_recall`, reached through
    `brain.console.reach_view`.

    Asserted on the signature as well as on the behaviour. The signature is where the wrong
    version arrives, as an `AgentRecord` parameter added so the viewer can be opened from an
    agent's tab, and behaviour alone would keep passing on the day it does.

    Delete this and the pin above can be widened to admit a caller nobody argued for, which is
    the thing that pin exists to make impossible."""
    import inspect

    from brain.console.govern_estate import subject_memory

    taken = inspect.signature(subject_memory).parameters

    assert "subject_id" in taken
    assert "reader" in taken
    assert not any(name in taken for name in ("record", "agent_id", "ceiling", "run"))

    theirs = learning("m_theirs")

    view = subject_memory(
        subject_id=theirs.formation.principal_id,
        entries=((theirs, "prefers email"),),
        reader=reader("read:client.name"),
        now=NOW,
    )

    assert [one.memory_id for one in view.memory.extracted] == ["m_theirs"]
    assert view.subject_id == theirs.formation.principal_id


def test_the_personal_memory_tab_narrows_by_authorship_and_holds_no_reach_at_all() -> None:
    """The sibling the test above demands, for the second importer of these shapes.

    **The argument is an absence.** `brain.console.reach_view.separate_memory` reads an agent
    tab and therefore has a reach to get right, which the test above holds it to.
    `brain.console.own_things.own_memory` reads a person's own tab, and a person's own tab is
    narrowed by who was asking when each memory formed, which is `Formation.principal_id`.
    That field's own comment says it is recorded for the audit question and never permits a
    recall, so the module takes no `EntitlementSet`: there is no parameter a reach could
    arrive through and nothing to get wrong. Recall is still `formation.may_recall`.

    Asserted on the signature as well as on the behaviour, because behaviour alone would keep
    passing on the day somebody adds an entitlement parameter and starts filtering by it.

    Delete this and the pin above can be widened to admit a caller nobody argued for, which
    is the thing that pin exists to make impossible."""
    import inspect

    from brain.console.own_things import OwnThingsError, delete_own_memory, own_memory

    for one in (own_memory, delete_own_memory):
        taken = inspect.signature(one).parameters
        assert "principal_id" in taken, one.__name__
        assert not any("entitle" in name or name == "caller" for name in taken), one.__name__

    theirs = learning("m_theirs")
    mine = Learning(
        memory_id="m_mine",
        proposal=theirs.proposal,
        formation=Formation(
            principal_id="p_reader",
            capabilities=theirs.formation.capabilities,
            scope=theirs.formation.scope,
            ent_hash=theirs.formation.ent_hash,
            formed_at=theirs.formation.formed_at,
        ),
    )

    assert own_memory([mine, theirs], principal_id="p_reader") == (mine,)
    with pytest.raises(OwnThingsError, match="may not delete"):
        delete_own_memory(theirs, principal_id="p_reader", at=NOW)
