"""The three listings, held to what each one refuses to show.

A per-agent tab that must not become a window onto other people's conversations, a department
view that must not become a window onto the people in the department, and a queue that must
not become a place where a gated change is decided. All three are pages of rows, and a page of
rows is where "DENIED and ABSENT are indistinguishable" is broken by adding a total.

Real `EntitlementSet`s throughout. The per-agent tab is the case that turns on
`EntitlementSet.intersect` running in the right direction with the real `Capability.covers`,
so both directions of the narrowing are tested separately: a ceiling that drops a capability
the caller holds, and a caller who holds less than the ceiling admits. A single test would
pass with either side of the intersection deleted.

Every hiding test has a sibling proving the permitted rows still come through.

Task ids: M16.5.2, M16.5.3, M16.5.4
"""

from __future__ import annotations

from dataclasses import fields as dataclass_fields
from datetime import UTC, datetime, timedelta

import pytest

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.memory import review as review_module
from brain.memory.correction import Demotion
from brain.memory.digest import COUNTING_FIELD_NAMES, Learning, MemoryItem, undo
from brain.memory.formation import Formation, clause_place
from brain.memory.review import (
    DEPARTMENT_CHANGES,
    QUEUE_ALARM_AT,
    REVIEW_MINUTES_PER_ITEM,
    REVIEW_SITTING_MINUTES,
    AgentMemoryView,
    DepartmentMemoryView,
    QueueAlarm,
    QueueItem,
    ReviewQueue,
    agent_memory,
    delete,
    department_memory,
    queue_alarm,
    review_gaps,
    review_queue,
)
from brain.memory.signals import Signal
from brain.memory.tiers import CHANGES_WHAT_ANYBODY_MAY_SEE, Change, Tier, propose

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
WEB = clause_place(department="web")
FINANCE = clause_place(department="finance")
ANYWHERE = Scope.unrestricted()
DESK = "a_service_desk"


def holder(
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
    agent_id: str | None = DESK,
    replaced_id: str | None = None,
    evidence: frozenset[Signal] = frozenset({Signal.REASKED}),
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
        agent_id=agent_id,
        replaced_id=replaced_id,
    )


def queued(how_many: int) -> tuple[QueueItem, ...]:
    return tuple(
        QueueItem(
            memory_id=f"m_{n}",
            change=Change.COMPANY_KNOWLEDGE,
            tier=Tier.GATED,
            subject=f"subject:{n}",
            evidence=(Signal.REASKED,),
            confidence=1.0,
            scope=WEB,
            learned_at=NOW,
        )
        for n in range(how_many)
    )


# ------------------------------------------------------------ M16.5.2 the per-agent tab
def test_a_caller_sees_in_an_agent_tab_what_their_own_reach_admits() -> None:
    """**The positive case, and without it every refusal in this file is satisfied by an
    `agent_memory` that returns nothing.**

    A tab showing nobody anything is not a permission win, it is a feature that does not work,
    and it would pass every hiding test here.

    Delete this and the whole file is green for a listing that is always empty."""
    view = agent_memory(
        now=NOW,
        caller=holder("read:client.name"),
        agent_ceiling=holder("read:client.name", scope=ANYWHERE, principal_id="agent"),
        agent_id=DESK,
        learnings=[learning("m_one"), learning("m_two")],
    )

    assert {one.memory_id for one in view.items} == {"m_one", "m_two"}
    assert view.agent_id == DESK
    assert view.reader_id == "p_reader"


def test_an_agent_tab_shows_no_more_than_the_agent_ceiling_admits() -> None:
    """**`E_run(caller, agent) = E(caller) intersect agent_ceiling`, in the surface where
    forgetting it is a page of somebody else's memories.**

    The caller holds two capabilities and the agent's ceiling admits one. An agent is a lens
    and never a principal, so the tab shows what the run reaches rather than what the caller
    reaches, and the memory formed under the capability the ceiling drops is not there.

    Isolated from its sibling below: this one fails if the intersection is replaced by the
    caller's own set, and that one fails if it is replaced by the ceiling. One test would pass
    with either half deleted.

    Delete this and a memory tab shows every caller everything the agent ever learnt, narrowed
    only by what they personally hold, which is not the run's reach and is wider than it every
    time an agent is deliberately restricted."""
    view = agent_memory(
        now=NOW,
        caller=holder("read:client.name", "read:client.contract_value"),
        agent_ceiling=holder("read:client.name", scope=ANYWHERE, principal_id="agent"),
        agent_id=DESK,
        learnings=[
            learning("m_name", capability="read:client.name"),
            learning("m_value", capability="read:client.contract_value"),
        ],
    )

    assert tuple(one.memory_id for one in view.items) == ("m_name",)


def test_an_agent_tab_shows_no_more_than_the_caller_themselves_holds() -> None:
    """The other half of the same intersection. The agent's ceiling is broad and the caller is
    not, and the tab is the caller's reach rather than the agent's.

    This is the direction that produces the disclosure: an agent installed with a wide ceiling
    has learnt things from conversations with people who hold more than this caller does, and
    a tab keyed on the agent rather than on the run would list them.

    Delete this and replacing the intersection with the ceiling passes, and the tab becomes a
    list of what the agent knows rather than what this person may be told."""
    view = agent_memory(
        now=NOW,
        caller=holder("read:client.name"),
        agent_ceiling=holder(
            "read:client.name",
            "read:client.contract_value",
            scope=ANYWHERE,
            principal_id="agent",
        ),
        agent_id=DESK,
        learnings=[
            learning("m_name", capability="read:client.name"),
            learning("m_value", capability="read:client.contract_value"),
        ],
    )

    assert tuple(one.memory_id for one in view.items) == ("m_name",)


def test_an_agent_tab_lists_only_what_that_agent_learnt() -> None:
    """A tab is per agent, so a learning from another agent's runs is not in it and a learning
    from a plain conversation belongs to no tab at all.

    The absence of a no-agent learning is not a refusal and nothing anywhere reports it: it is
    simply not part of what this agent learnt.

    Delete this and every agent's tab shows every agent's learnings, and the per-agent
    ceiling stops meaning anything even though the intersection is still computed."""
    view = agent_memory(
        now=NOW,
        caller=holder("read:client.name"),
        agent_ceiling=holder("read:client.name", scope=ANYWHERE, principal_id="agent"),
        agent_id=DESK,
        learnings=[
            learning("m_mine", agent_id=DESK),
            learning("m_theirs", agent_id="a_finance_bot"),
            learning("m_no_agent", agent_id=None),
        ],
    )

    assert tuple(one.memory_id for one in view.items) == ("m_mine",)


def test_a_memory_listing_is_most_confident_first_in_an_order_that_does_not_move() -> None:
    """A listing whose order changes between two readings is one nobody can work through:
    somebody halfway down loses their place every time the page reloads. So the order is a
    property of the listing rather than of whatever the caller happened to pass in.

    Most confident first, because a person scanning a page of things the system believes wants
    the ones it is surest of at the top; ties break on the time it was learnt and then on the
    id, which is the same three-part key `correction.newest_first` uses for the same reason.

    The confidences here come from real decay rather than being set by hand, because
    `may_recall` is what produces the number the sort reads and a test that supplied it would
    not be testing this ordering at all.

    Delete this and the sort key can be changed or removed with the file green, because every
    other listing test in it asserts on a set or on a single row."""
    view = agent_memory(
        now=NOW,
        caller=holder("read:client.name"),
        agent_ceiling=holder("read:client.name", scope=ANYWHERE, principal_id="agent"),
        agent_id=DESK,
        learnings=[
            learning("m_faded", at=NOW - timedelta(days=10)),
            learning("m_surest", at=NOW),
            learning("m_tie_b", at=NOW - timedelta(days=5)),
            learning("m_tie_a", at=NOW - timedelta(days=5)),
        ],
    )

    assert tuple(one.memory_id for one in view.items) == (
        "m_surest",
        "m_tie_a",
        "m_tie_b",
        "m_faded",
    )
    assert [one.confidence for one in view.items] == sorted(
        (one.confidence for one in view.items), reverse=True
    )


def test_the_delete_control_writes_the_same_mark_the_digest_undo_writes() -> None:
    """**The control says delete and the system writes a mark, and there is one implementation
    of that rather than two.**

    Two implementations is two things that can disagree about what a delete means, and the one
    that ends up meaning delete is the one written by somebody who read the button rather than
    `brain.memory.correction`.

    Asserted as equality against `digest.undo` rather than by checking the shape of what
    `delete` returns, because a second implementation that happens to produce the same shape
    today is exactly what this is guarding against.

    Delete this and `delete` grows a body of its own, and the first change made to it will be
    the one that makes it live up to its name."""
    replacing = learning("m_new", replaced_id="m_old")
    alone = learning("m_alone")

    assert delete(replacing, at=NOW) == undo(replacing, at=NOW)
    assert delete(alone, at=NOW) == undo(alone, at=NOW)
    assert delete(alone, at=NOW).took_effect is True

    written = delete(alone, at=NOW).correction
    assert isinstance(written, Demotion), "a learning that replaced nothing is demoted"

    assert delete(alone, at=NOW, demotions=[written]).took_effect is False


def test_a_memory_row_says_which_mark_its_control_would_write() -> None:
    """The control is a mark either way and which mark depends on whether there is anything to
    restore, so the row says which rather than leaving a renderer to guess and label them both
    the same.

    `Correction` has two members and deliberately no third, so this field is structurally
    unable to express a removal.

    Delete this and a renderer labels a demotion "restores the previous version", which is a
    promise the system cannot keep."""
    view = agent_memory(
        now=NOW,
        caller=holder("read:client.name"),
        agent_ceiling=holder("read:client.name", scope=ANYWHERE, principal_id="agent"),
        agent_id=DESK,
        learnings=[learning("m_new", replaced_id="m_old"), learning("m_alone")],
    )
    writes = {one.memory_id: one.control_writes for one in view.items}

    assert writes["m_new"].value == "superseded"
    assert writes["m_alone"].value == "demoted"


# ------------------------------------------------------ M16.5.3 the department admin view
def test_a_department_view_is_not_a_wider_lens_on_its_members_conversations() -> None:
    """**M16.5.3, and the line it is drawn on.**

    A department head may see what the system learnt about the department. What it learnt from
    each of their reports' conversations is a different thing, and a view unioning the second
    is a performance review assembled out of a memory tab.

    The two cannot be told apart by reading a memory and nothing here reads one, so the line
    is the change kind: only `tiers.CHANGES_WHAT_ANYBODY_MAY_SEE`. A preference formed inside
    this very department is absent, which is the honest cost, stated rather than worked
    around.

    Delete this and the filter widens to "everything formed in this department", which is the
    version somebody will ask for, and it is a page listing how each of a manager's reports
    likes their answers shaped."""
    view = department_memory(
        now=NOW,
        caller=holder("read:client.name", scope=ANYWHERE),
        department="web",
        learnings=[
            learning("m_knowledge", Change.COMPANY_KNOWLEDGE, scope=WEB),
            learning("m_preference", Change.PREFERENCE, scope=WEB),
            learning("m_shortcut", Change.PROCEDURAL_SHORTCUT, scope=WEB),
            learning("m_signal", Change.NEGATIVE_SIGNAL, scope=WEB),
        ],
    )

    assert tuple(one.memory_id for one in view.items) == ("m_knowledge",)
    assert DEPARTMENT_CHANGES <= CHANGES_WHAT_ANYBODY_MAY_SEE


def test_a_department_view_shows_only_the_department_it_was_asked_about() -> None:
    """The department is a place the reader is checked against, not a label on the row. A
    caller who reaches the whole company still sees one department at a time here, because the
    view is about that department.

    The permitted row is asserted in the same call, so a `department_memory` that shows nothing
    cannot pass.

    Delete this and `where` can be dropped from the recall check, at which point `may_recall`
    falls back to each memory's own place, every memory matches its own department, and the
    web view lists finance."""
    view = department_memory(
        now=NOW,
        caller=holder("read:client.name", scope=ANYWHERE),
        department="web",
        learnings=[
            learning("m_web", Change.COMPANY_KNOWLEDGE, scope=WEB),
            learning("m_finance", Change.COMPANY_KNOWLEDGE, scope=FINANCE),
        ],
    )

    assert tuple(one.memory_id for one in view.items) == ("m_web",)
    assert view.department == "web"


def test_a_department_view_needs_a_department() -> None:
    """An unnamed department is every department, and a view called with a blank string would
    quietly become the company-wide listing this module refuses to build.

    Delete this and a missing value in a route parameter widens the view instead of failing
    it."""
    with pytest.raises(ValueError, match="unnamed one is every department"):
        department_memory(
            now=NOW,
            caller=holder("read:client.name", scope=ANYWHERE),
            department="",
            learnings=[],
        )


def test_review_gaps_reports_a_department_view_that_has_widened(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**Written because a diagnostic nobody has watched report anything is a diagnostic
    nobody can rely on.**

    `DEPARTMENT_CHANGES` is the same object as `CHANGES_WHAT_ANYBODY_MAY_SEE` today, so the
    subset check in `review_gaps` is satisfied trivially and would be green whether it existed
    or not. What it is for is the day somebody writes the set out by hand to add one member,
    which is how this view widens: one change at a time, each individually reasonable.

    Patched rather than edited, so the module is left as it is and the test says what a
    widened view looks like.

    Delete this and the subset check can be removed with the file green, and the first person
    to add `PREFERENCE` to the department view does it without anything objecting."""
    widened = DEPARTMENT_CHANGES | {Change.PREFERENCE}
    monkeypatch.setattr("brain.memory.review.DEPARTMENT_CHANGES", widened)

    gaps = review_gaps()

    assert any("preference" in one for one in gaps), gaps
    assert any("learnt from individuals" in one for one in gaps), gaps

    view = department_memory(
        now=NOW,
        caller=holder("read:client.name", scope=ANYWHERE),
        department="web",
        learnings=[learning("m_preference", Change.PREFERENCE, scope=WEB)],
    )
    assert view.items, "the patch did not reach department_memory, so the gap is untested"


# --------------------------------------------------------- M16.5.4 the tier-three queue
def test_the_review_queue_holds_the_gated_changes_and_nothing_else() -> None:
    """Tier three is what waits for a person. A tier-one learning has already taken effect and
    a tier-two one is waiting on independent agreement rather than on anybody, so putting
    either here buries the decisions that need somebody under the ones that do not.

    Both directions in one call: the gated rows are present and the others are not.

    Delete this and the queue becomes a list of everything the system learnt, and the access
    decisions in it stop being found."""
    queue = review_queue(
        now=NOW,
        caller=holder("read:client.name", scope=ANYWHERE),
        learnings=[
            learning("m_widen", Change.SCOPE_WIDENING, scope=WEB),
            learning("m_leash", Change.LEASH_INCREASE, scope=WEB),
            learning("m_preference", Change.PREFERENCE, scope=WEB),
            learning("m_rule", Change.FAST_PATH_RULE, scope=WEB),
            learning("m_session", Change.SESSION_CONTEXT, scope=WEB),
        ],
    )

    assert {one.memory_id for one in queue.items} == {"m_widen", "m_leash"}
    assert {one.tier for one in queue.items} == {Tier.GATED}


def test_the_review_queue_comes_back_oldest_first() -> None:
    """The opposite of the digest and for the opposite reason. A queue is worked from the top
    and abandoned partway down, so newest-first starves the item that has been waiting
    longest, which is the one whose delay is already the problem.

    Ties break on the memory id, so a page that is reloaded looks the same and somebody
    halfway down keeps their place.

    Delete this and the order becomes the caller's, and the oldest gated change is never
    reached by anybody."""
    queue = review_queue(
        now=NOW,
        caller=holder("read:client.name", scope=ANYWHERE),
        learnings=[
            learning("m_newest", Change.COMPANY_KNOWLEDGE, at=NOW),
            learning("m_oldest", Change.COMPANY_KNOWLEDGE, at=NOW - timedelta(days=10)),
            learning("m_tie_b", Change.COMPANY_KNOWLEDGE, at=NOW - timedelta(days=5)),
            learning("m_tie_a", Change.COMPANY_KNOWLEDGE, at=NOW - timedelta(days=5)),
        ],
    )

    assert tuple(one.memory_id for one in queue.items) == (
        "m_oldest",
        "m_tie_a",
        "m_tie_b",
        "m_newest",
    )


def test_the_alarm_is_raised_on_the_rows_this_reader_can_see() -> None:
    """**An alarm computed on the true queue and shown beside a short list is a subtraction.**

    A reader with two visible rows and a raised alarm has been told there are at least a dozen
    more, which is the count of hidden items this system refuses everywhere. So the alarm reads
    the filtered list.

    The cost is asserted in the same test rather than hidden: the reader who reaches the whole
    estate does get the alarm, which is where the operational value actually lives.

    Delete this and the alarm is computed before the entitlement filter, because that is the
    obvious place for it, and every department head learns roughly how many access decisions
    about other departments are outstanding."""
    elsewhere = [
        learning(f"m_fin_{n}", Change.COMPANY_KNOWLEDGE, scope=FINANCE)
        for n in range(QUEUE_ALARM_AT + 1)
    ]
    here = [learning("m_web_1", Change.COMPANY_KNOWLEDGE, scope=WEB)]

    narrow = review_queue(
        now=NOW,
        caller=holder("read:client.name", scope=WEB),
        learnings=[*elsewhere, *here],
    )
    wide = review_queue(
        now=NOW,
        caller=holder("read:client.name", scope=ANYWHERE, principal_id="p_operator"),
        learnings=[*elsewhere, *here],
    )

    assert tuple(one.memory_id for one in narrow.items) == ("m_web_1",)
    assert narrow.alarm.raised is False
    assert wide.alarm.raised is True


def test_the_alarm_fires_when_the_queue_passes_one_sitting_of_review() -> None:
    """**The threshold is anchored to something outside itself, which is what makes the figure
    right rather than round.**

    What makes a tier-three queue worth an alarm is not that it reached some number: it is
    that it has grown past what a person works through in one sitting, because a queue longer
    than that is a queue that is not being worked through, and a tier-three queue that is not
    being worked through is a set of access decisions nobody is making.

    So the constant is checked against the two figures it comes from, one item's review time
    and one sitting's length, from both sides. A test asserting `QUEUE_ALARM_AT == 15` while
    importing `QUEUE_ALARM_AT` would be green for every value it could hold.

    Strictly greater, because a queue that is exactly one sitting long is one somebody can
    still clear this afternoon.

    Delete this and the threshold drifts to whatever produces a quiet dashboard, and the alarm
    stops meaning that the queue is not being worked through."""
    assert QUEUE_ALARM_AT * REVIEW_MINUTES_PER_ITEM <= REVIEW_SITTING_MINUTES
    assert (QUEUE_ALARM_AT + 1) * REVIEW_MINUTES_PER_ITEM > REVIEW_SITTING_MINUTES

    assert queue_alarm(queued(QUEUE_ALARM_AT)).raised is False
    assert queue_alarm(queued(QUEUE_ALARM_AT + 1)).raised is True
    assert queue_alarm(()).raised is False


def test_review_gaps_reports_an_alarm_that_no_longer_means_one_sitting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The watched half of the check above. `review_gaps` reads the three figures and reports
    when they stop relating, and a diagnostic nobody has seen return a row is one nobody can
    rely on.

    The patch reaches `review_gaps`, which reads the module global, and deliberately not
    `queue_alarm`, whose default is bound at definition like every other default in this
    repository. What is under test is the diagnostic, not the arithmetic.

    Delete this and the relation check can be removed and `review_gaps` goes on returning an
    empty tuple."""
    monkeypatch.setattr("brain.memory.review.QUEUE_ALARM_AT", QUEUE_ALARM_AT * 3)

    gaps = review_gaps()

    assert any("one sitting of review" in one for one in gaps), gaps


def test_nothing_here_can_approve_a_gated_change() -> None:
    """`tiers.propose` returns a proposal and there is no `apply`; a gated change is approved
    by a surface that does not exist. This is not that surface, and the pressure to make it
    one arrives the first time somebody sits in front of the queue and cannot act on it.

    Asserted over the module's public callables rather than over behaviour, because behaviour
    today says nothing about whether an `approve_widening` can be added tomorrow, and it would
    arrive looking like an obvious omission.

    Delete this and the queue grows a button, and the button is the thing the whole tier split
    exists to keep out of a page of rows."""
    for name, value in vars(review_module).items():
        if name.startswith("_") or not callable(value):
            continue
        for forbidden in ("approve", "apply", "grant", "widen", "allow", "permit"):
            assert forbidden not in name.lower(), f"{name} could be read as deciding"

    assert review_gaps() == ()


def test_a_queued_change_carries_no_control_a_person_could_press() -> None:
    """A gated change has not been applied, so there is nothing to delete, and a control drawn
    beside a scope widening is a person deciding it by pressing something that says delete.

    Asserted as the difference between the two row shapes, because that difference is the
    design: `MemoryItem` carries a control and `QueueItem` deliberately does not.

    Delete this and the queue is rendered from `MemoryItem` for convenience, and the tab's
    delete button appears next to a capability addition."""
    on_a_queue_row = {one.name for one in dataclass_fields(QueueItem)}
    on_a_memory_row = {one.name for one in dataclass_fields(MemoryItem)}

    assert "control_writes" in on_a_memory_row
    assert "control_writes" not in on_a_queue_row
    assert on_a_queue_row == on_a_memory_row - {"control_writes"}


def test_a_queued_change_carries_the_evidence_that_prompted_it() -> None:
    """**Written because a mutation survived: blanking the evidence on a queue row broke
    nothing.**

    The test above compares the two row shapes by field name, which passes for a `_queue_item`
    that fills every one of them with nothing. M16.5.4 is where a person decides an access
    question, and deciding one without the evidence that prompted it is the version of this
    surface that looks complete and is useless: the reader sees that the system wants to widen
    somebody's reach and nothing about why.

    Asserted against the memory row built from the same learning, so the queue and the tab
    cannot drift in what they say about it, which is the reason `_queue_item` is built from
    `MemoryItem` rather than assembled separately.

    The learning is formed well in the past on purpose. A queue row built at the moment of
    formation has a confidence of exactly one, so a `_queue_item` hard-coding one would be
    indistinguishable from a `_queue_item` copying the decayed value, and a mutation putting a
    literal there survived this test until the date was moved.

    Delete this and a queue row can carry an empty tuple in every field but the id, and the
    shape test above stays green."""
    prompted = frozenset({Signal.REASKED, Signal.ESCALATED})
    one = learning(
        "m_widen",
        Change.SCOPE_WIDENING,
        scope=WEB,
        evidence=prompted,
        at=NOW - timedelta(days=10),
    )
    caller = holder("read:client.name", scope=ANYWHERE)

    queue = review_queue(now=NOW, caller=caller, learnings=[one])
    tab = agent_memory(
        now=NOW,
        caller=caller,
        agent_ceiling=holder("read:client.name", scope=ANYWHERE, principal_id="agent"),
        agent_id=DESK,
        learnings=[one],
    )

    assert queue.items[0].evidence == tuple(sorted(prompted))
    assert queue.items[0].evidence == tab.items[0].evidence
    assert queue.items[0].subject == tab.items[0].subject
    assert queue.items[0].confidence == tab.items[0].confidence
    assert queue.items[0].confidence < 1.0, "the row was built before any decay could show"
    assert queue.items[0].learned_at == NOW - timedelta(days=10)


def test_no_listing_shape_carries_a_count_of_what_it_did_not_show() -> None:
    """**The rule that applies to all three views at once, and the field is where it leaks.**

    "Showing three of forty" tells a department head there are thirty-seven learnings about
    their own department they may not read. Asserted on the dataclass fields rather than on
    rendered text, because the field is what a later renderer finds and uses.

    `QueueAlarm` is in the list on purpose: an alarm with a length on it is the same
    subtraction wearing an operational hat, and it is the field an operator will ask for by
    name.

    Delete this and `waiting` appears on the alarm, and it will be added by somebody who wants
    the dashboard to say how bad it is."""
    for model in (QueueItem, QueueAlarm, ReviewQueue, AgentMemoryView, DepartmentMemoryView):
        for one in dataclass_fields(model):
            assert one.name not in COUNTING_FIELD_NAMES, f"{model.__name__} carries {one.name}"
            assert one.type not in ("int", "int | None"), (
                f"{model.__name__}.{one.name} is an integer, which on a filtered listing is a "
                "count of something"
            )

    assert not any(char.isdigit() for char in queue_alarm(queued(QUEUE_ALARM_AT + 1)).reason)
    assert not any(char.isdigit() for char in queue_alarm(()).reason)


def test_review_gaps_reports_a_control_that_could_decide_and_a_total_that_should_not_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**Two branches of `review_gaps` that no other test has watched report anything.**

    The rest of this file calls `review_gaps` on a healthy module and asserts an empty tuple,
    which passes whether either branch exists or not: the name scan finds nothing today, and
    the field scan duplicates an assertion made directly above it. Both are worth keeping,
    because the person they are for is the one who adds `approve_widening` in six months and
    the one who puts a length on the alarm, and neither of those diffs is watched by anything
    that runs against the module as it stands.

    A callable is injected into the module's own globals rather than defined in it, so the
    check is exercised against the thing it actually reads.

    Delete this and both branches can be removed and `review_gaps` goes on returning an empty
    tuple, which is what everything else in this file asserts."""
    monkeypatch.setitem(vars(review_module), "approve_widening", lambda: None)
    monkeypatch.setattr("brain.memory.review.COUNTING_FIELD_NAMES", frozenset({"confidence"}))

    gaps = review_gaps()

    assert any("could be read as deciding" in one for one in gaps), gaps
    assert any("QueueItem carries confidence" in one for one in gaps), gaps
