"""A memory formed from an answered turn: stated or extracted, the person's own, and never twice.

`brain.memory.turn` decides what a turn proposes over values, and
`brain.ops.memory_store.StoredFormations` reads what the person has and writes the proposal with its
learning record. The first half here holds the rules; the second builds the memory tables through
the migrations that ship and writes a turn through the store. **The second half skips when there is
no server**, and CI always has one.

Task ids: M16.1.2, M16.1.3, M38.2.2.4, M16.7.12, M16.6.3
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.gate.abstain import Abstention, AbstentionReason
from brain.gate.answer import Answered
from brain.memory.correction import Demotion, Supersession
from brain.memory.digest import Learning
from brain.memory.formation import (
    HALF_LIFE_DAYS,
    RECALL_FLOOR,
    MemoryKind,
    confidence_now,
    may_recall,
    place_of,
)
from brain.memory.recall import recall
from brain.memory.signals import Signal
from brain.memory.tiers import Change, Tier
from brain.memory.turn import (
    EXTRACTED_CONFIDENCE,
    MAX_CAPABILITY_TAGS,
    STATED_CONFIDENCE,
    Held,
    NotFormed,
    Turn,
    TurnError,
    candidate,
    is_answered,
    key_of,
    memory_id,
    propose_memories,
    recall_place,
    requirement_of,
    turn_of,
    worth_forming,
)
from brain.ops.memory_store import StoredFormations, StoredRecall
from brain.session import make_session_factory
from brain.tables import memory as memory_table
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_memory_store import through_0061

#: Far from any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
NOW = datetime(2999, 1, 3, 10, 30, tzinfo=UTC)

PERSON = "u_person"
WEB = Scope.department("web")


def reach(*capabilities: str, pid: str = PERSON, scope: Scope | None = None) -> EntitlementSet:
    return EntitlementSet(
        principal_id=pid,
        grants=tuple(
            Grant(capability=Capability(value=one), scope=scope or Scope.unrestricted())
            for one in capabilities
        ),
    )


def a_turn(
    said: str,
    *,
    answered: bool = True,
    held: EntitlementSet | None = None,
    refused: bool = False,
    department: str | None = None,
) -> Turn:
    return Turn(
        trace_id="trace-one",
        principal_id=PERSON,
        said=said,
        answered=answered,
        reach=held or reach("read:client.name", scope=WEB),
        at=NOW,
        agent_id="desk",
        refused=refused,
        department=department,
    )


def formed(said: str, **kw: object) -> list[Learning]:
    return [one.learning for one in propose_memories(a_turn(said, **kw), []).formed]  # type: ignore[arg-type]


# ------------------------------------------------------------------ the words
def test_a_stated_memory_is_persistent_at_full_confidence_and_keeps_what_follows_the_opener() -> (
    None
):
    """Delete this and "remember that" would be inferred and decay, or keep its own opener as if
    the person had asked to remember the word "remember"."""
    proposals = propose_memories(
        a_turn("Remember that I work from the Penang office on Fridays."), []
    )
    [one] = proposals.formed
    assert one.statement == "I work from the Penang office on Fridays"
    assert one.learning.formation.kind is MemoryKind.PERSISTENT
    assert one.learning.formed_confidence == STATED_CONFIDENCE


def test_a_preference_said_in_passing_is_extracted_at_a_confidence_that_decays() -> None:
    """Recalled at once, gone within a few half-lives with nothing reinforcing it. Delete this and
    an inference would be kept as though the person had asked for it, for ever."""
    [one] = formed("I prefer short answers with the figure first. What is the balance?")
    assert one.formation.kind is MemoryKind.ADAPTIVE
    assert RECALL_FLOOR < EXTRACTED_CONFIDENCE < STATED_CONFIDENCE
    later = NOW + timedelta(days=2 * HALF_LIFE_DAYS)
    assert confidence_now(EXTRACTED_CONFIDENCE, formed_at=NOW, now=later) < RECALL_FLOOR


def test_a_turn_with_nothing_to_remember_or_one_the_lane_refused_forms_nothing() -> None:
    """Delete this and every question would be kept, or the words beside a refusal would be."""
    assert propose_memories(a_turn("What is the balance on Acme?"), []).skipped == (
        NotFormed.NOTHING_TO_REMEMBER,
    )
    refused = propose_memories(
        a_turn(
            "Remember that I prefer email. I prefer short answers.", answered=False, refused=True
        ),
        [],
    )
    assert (refused.formed, refused.skipped) == ((), (NotFormed.REFUSED,))


def test_a_stated_memory_is_kept_when_the_lane_found_nothing_and_an_inference_is_not() -> None:
    """**The owner's install formed no memory from "remember that ...", ever.** The lane abstains
    on a sentence that asks nothing it can find, and until 2026-09-29 a stated memory waited for an
    answered turn, so it never formed. Now it forms from any turn the lane did not refuse, and an
    inference still waits for an answer.

    Delete this and "remember that" goes back to being a sentence the system says it could not
    find, or an inference is kept from a question nobody was helped with."""
    proposals = propose_memories(
        a_turn("Remember that I prefer email. I prefer short answers.", answered=False), []
    )
    assert [one.statement for one in proposals.formed] == ["I prefer email"]
    assert [one.learning.formation.kind for one in proposals.formed] == [MemoryKind.PERSISTENT]
    assert proposals.skipped == (NotFormed.NOT_ANSWERED,)

    answered = propose_memories(
        a_turn("Remember that I prefer email. I prefer short answers.", answered=True), []
    )
    assert [one.statement for one in answered.formed] == [
        "I prefer email",
        "I prefer short answers",
    ]


def test_a_turn_cannot_be_both_answered_and_refused() -> None:
    """Delete this and a turn could say both, and formation would pick whichever it read first."""
    with pytest.raises(TurnError, match="both answered and refused"):
        a_turn("Remember that I prefer email.", answered=True, refused=True)


def test_a_memory_names_the_person_and_the_department_they_said_it_in() -> None:
    """**A person whose every grant is scoped to their department read none of their own memories
    on a screen (M16.7.12).** The Memory screen and My workspace ask recall about the place a memory
    names, and a department-scoped grant matches no place that names no department. With the
    department in the formation's scope the place is reached by that department's grants and by a
    company-wide one, and not by another department's, and an answer asked from another department
    recalls nothing of it.

    Delete this and a formation can go back to naming the person alone, and every reader without a
    company-wide grant finds nothing about themselves on the Memory screen or My workspace."""
    theirs = reach("read:client.name", scope=WEB)
    [one] = formed("Remember that I work from Penang on Fridays.", held=theirs, department="web")
    assert place_of(one.formation.scope) == {"principal_id": PERSON, "department": "web"}

    assert may_recall(one.formation, theirs, now=NOW)
    assert may_recall(one.formation, theirs, now=NOW, where=recall_place(PERSON, "web"))
    assert may_recall(one.formation, reach("read:client.name"), now=NOW)
    ops = reach("read:client.name", scope=Scope.department("ops"))
    assert not may_recall(one.formation, ops, now=NOW)
    assert not may_recall(one.formation, ops, now=NOW, where=recall_place(PERSON, "ops"))
    assert not may_recall(one.formation, theirs, now=NOW, where=recall_place("u_other", "web"))

    [unplaced] = formed("Remember that I work from Penang on Fridays.", held=theirs)
    assert place_of(unplaced.formation.scope) == {"principal_id": PERSON}
    assert not may_recall(unplaced.formation, theirs, now=NOW)


def test_only_words_that_could_become_a_memory_are_worth_forming() -> None:
    """The check the answer route makes before opening any connection. Delete this and every
    question would take a lock on its asker and read their memories, or a stated memory could be
    judged not worth forming and never reach the store."""
    assert worth_forming("What is the balance? Remember that I prefer email.")
    assert worth_forming("I'd rather have the figure first.")
    assert not worth_forming("What is the balance on Acme?")
    assert not worth_forming("Can you remember the balance?")


def test_the_turn_an_outcome_is_follows_the_lane_and_a_referral_is_a_refusal() -> None:
    """`turn_of` is what the route builds: answered from the outcome, refused for a model's
    refusal or a referral, the run's principal, and nothing at all for words that ask nothing.

    Delete this and a referred question's words could be remembered, or a refusal read as found
    nothing and its stated memory kept."""
    held = reach("read:client.name", scope=WEB)
    answered = Answered(frames=("data: ok",), from_cache=True)
    nothing = Answered(
        frames=("data: no",), abstention=Abstention(reason=AbstentionReason.NOTHING_RETRIEVED)
    )
    declined = Answered(
        frames=("data: no",), abstention=Abstention(reason=AbstentionReason.REFUSED)
    )

    def made(
        outcome: Answered, *, referred: bool = False, said: str = "Remember that I am in."
    ) -> Turn | None:
        return turn_of(
            trace_id="trace-one",
            said=said,
            outcome=outcome,
            referred=referred,
            reach=held,
            at=NOW,
            agent_id=None,
            department="web",
        )

    one = made(answered)
    assert one is not None and (one.answered, one.refused, one.department) == (True, False, "web")
    assert one.principal_id == held.principal_id
    found = made(nothing)
    assert found is not None and (found.answered, found.refused) == (False, False)
    refusal = made(declined)
    assert refusal is not None and (refusal.answered, refusal.refused) == (False, True)
    referral = made(answered, referred=True)
    assert referral is not None and (referral.answered, referral.refused) == (False, True)
    assert made(answered, said="What is the balance?") is None
    assert (
        turn_of(
            trace_id=" ",
            said="Remember that I am in.",
            outcome=answered,
            referred=False,
            reach=held,
            at=NOW,
            agent_id=None,
            department=None,
        )
        is None
    )


def test_a_claim_about_the_company_forms_nothing_because_a_person_has_to_decide_it() -> None:
    """Delete this and "remember that the Acme contract renews in March" would be kept as a
    preference at tier one, which is company knowledge nobody approved."""
    proposals = propose_memories(a_turn("Remember that the Acme contract renews in March."), [])
    assert (proposals.formed, proposals.skipped) == ((), (NotFormed.NOT_ABOUT_THE_PERSON,))


def test_what_is_formed_is_a_tier_one_preference_about_that_memory_by_that_agent() -> None:
    """Delete this and a formation could propose a change at a tier nobody checked."""
    [one] = formed("Please always show me the total first.")
    assert (one.proposal.change, one.proposal.tier) == (Change.PREFERENCE, Tier.AUTOMATIC)
    assert one.proposal.subject == f"memory:{one.memory_id}"
    assert one.agent_id == "desk"
    assert one.evidence == frozenset()


def test_a_sentence_too_long_or_empty_after_its_opener_is_not_a_memory() -> None:
    """Delete this and a pasted paragraph would become a memory, or "remember that." an empty
    one."""
    assert candidate("Remember that.") is None
    assert candidate("I prefer " + "very " * 80 + "short answers") is None
    assert candidate("i'd rather have it in a table") == (
        MemoryKind.ADAPTIVE,
        "i'd rather have it in a table",
    )


# ------------------------------------------------------------------ whose, and at what reach
def test_a_memory_is_formed_in_the_persons_own_scope_at_the_reach_the_turn_was_answered_at() -> (
    None
):
    """The formation names the person, carries the reach's capabilities and its digest, and is
    recalled to that person at that reach and to nobody else, however much they hold.

    Delete this and something a person said would be recalled while acting for a colleague."""
    held = reach("read:client.name", "read:invoice.total", scope=WEB)
    [one] = formed("Remember that I am on leave in August.", held=held)
    formation = one.formation
    assert formation.principal_id == PERSON
    assert [one.value for one in formation.capabilities] == [
        "read:client.name",
        "read:invoice.total",
    ]
    assert formation.ent_hash == held.ent_hash()

    mine = recall([one], held, now=NOW, where=recall_place(PERSON, "web"))
    assert [found.memory_id for found in mine] == [one.memory_id]

    everything = reach("read:client.name", "read:invoice.total", pid="u_colleague")
    assert recall([one], everything, now=NOW, where=recall_place("u_colleague", "web")) == ()
    narrower = reach("read:client.name", scope=WEB)
    assert recall([one], narrower, now=NOW, where=recall_place(PERSON, "web")) == ()


def test_a_reach_holding_nothing_or_too_much_to_tag_forms_nothing() -> None:
    """Delete this and a formation could carry no requirement, which everybody covers, or one cut
    down to fit, which is narrower than what the words were said under."""
    empty = propose_memories(a_turn("Remember that I prefer email.", held=reach()), [])
    assert empty.skipped == (NotFormed.NO_REACH,)
    wide = reach(*(f"read:thing{n}.name" for n in range(MAX_CAPABILITY_TAGS + 1)))
    too_wide = propose_memories(a_turn("Remember that I prefer email.", held=wide), [])
    assert too_wide.skipped == (NotFormed.REACH_TOO_WIDE_TO_TAG,)
    exactly = reach(*(f"read:thing{n}.name" for n in range(MAX_CAPABILITY_TAGS)))
    assert (
        len(propose_memories(a_turn("Remember that I prefer email.", held=exactly), []).formed) == 1
    )
    assert MAX_CAPABILITY_TAGS == memory_table.MAX_CAPABILITY_TAGS


def test_a_capability_a_held_wildcard_covers_is_not_tagged_twice() -> None:
    """Delete this and a reach holding both a wildcard and a column under it would spend a tag on
    a requirement that says nothing more."""
    found = requirement_of(reach("read:client.*", "read:client.name", "read:invoice.total"), NOW)
    assert found is not None
    assert [one.value for one in found] == ["read:client.*", "read:invoice.total"]


def test_a_turn_handed_somebody_elses_reach_is_refused() -> None:
    """Delete this and a memory could be formed at a reach the person never held."""
    with pytest.raises(TurnError, match="reach of"):
        a_turn("Remember that I prefer email.", held=reach("read:client.name", pid="u_other"))


# ------------------------------------------------------------------ what the person already has
def held_memory(statement: str, kind: MemoryKind, memory: str = "m_old") -> Held:
    return Held(memory_id=memory, kind=kind, statement=statement)


def test_a_statement_the_person_already_has_standing_is_not_formed_twice() -> None:
    """Delete this and every restatement would be a second memory recalled beside the first."""
    already = [held_memory("I prefer short answers", MemoryKind.ADAPTIVE)]
    proposals = propose_memories(a_turn("I prefer short answers!"), already)
    assert (proposals.formed, proposals.skipped) == ((), (NotFormed.ALREADY_REMEMBERED,))
    twice = propose_memories(a_turn("I prefer short answers. I prefer short answers."), [])
    assert len(twice.formed) == 1
    assert twice.skipped == (NotFormed.ALREADY_REMEMBERED,)


def test_a_corrected_inference_is_not_inferred_again_and_a_statement_of_it_is_still_kept() -> None:
    """Undone by a demotion, the next conversation's same inference forms nothing; the person saying
    it outright forms a stated memory. A supersession marks the same way.

    Delete this and an undo on the Learning screen would be undone by the next conversation."""
    already = [held_memory("I prefer short answers", MemoryKind.ADAPTIVE)]
    demoted = [Demotion(memory_id="m_old", field="answer.length", at=NOW - timedelta(days=1))]

    inferred = propose_memories(a_turn("I prefer short answers."), already, demotions=demoted)
    assert (inferred.formed, inferred.skipped) == ((), (NotFormed.CORRECTED,))

    stated = propose_memories(
        a_turn("Remember that I prefer short answers."), already, demotions=demoted
    )
    [kept] = stated.formed
    assert kept.learning.formation.kind is MemoryKind.PERSISTENT

    superseded = [
        Supersession(superseded_id="m_old", by_id="m_new", prompted_by=Signal.CONTRADICTED, at=NOW)
    ]
    again = propose_memories(a_turn("I prefer short answers."), already, supersessions=superseded)
    assert again.skipped == (NotFormed.CORRECTED,)


def test_a_memory_id_is_derived_from_the_turn_and_the_words() -> None:
    """Delete this and a turn formed twice would propose two ids, and the second would not find
    the first."""
    turn = a_turn("I prefer short answers.")
    one = memory_id(turn, MemoryKind.ADAPTIVE, "I prefer short answers")
    assert len(one) == 26
    assert one == memory_id(turn, MemoryKind.ADAPTIVE, "i prefer SHORT answers")
    assert one != memory_id(turn, MemoryKind.PERSISTENT, "I prefer short answers")
    assert key_of("I'd prefer   short, answers!") == "i'd prefer short answers"


def test_an_outcome_is_answered_exactly_when_nothing_was_abstained() -> None:
    """Delete this and a refusal's words would be treated as an answered turn."""
    assert is_answered(Answered(frames=("data: ok",), from_cache=True))
    declined = Answered(
        frames=("data: no",), abstention=Abstention(reason=AbstentionReason.NOTHING_RETRIEVED)
    )
    assert not is_answered(declined)


# ------------------------------------------------------------------ the store, on a server
def rows(url: str) -> Sequence[tuple[object, ...]]:
    return sql(
        url,
        "SELECT m.id, m.kind, m.statement, m.principal_id, l.change, l.tier, l.agent_id"
        " FROM (SELECT id, kind, statement, principal_id FROM mem.persistent"
        " UNION ALL SELECT id, kind, statement, principal_id FROM mem.adaptive) m"
        " JOIN mem.learning l ON l.memory_id = m.id ORDER BY m.statement",
    )


def form(url: str, turn: Turn) -> object:
    async def go() -> object:
        built = app_engine(url)
        try:
            return await StoredFormations(make_session_factory(built)).form(turn)
        finally:
            await built.dispose()

    return run(go)


def test_a_turn_writes_each_memory_with_its_learning_record_and_a_repeat_writes_nothing() -> None:
    """As the application role: a stated and an extracted memory, each beside its learning record,
    and the same turn formed again writes nothing new.

    Delete this and a memory could reach the table with no revision record the Memory screen reads,
    or the same words twice."""
    with through_0061("brain_memory_turn_store") as url:
        turn = a_turn("Remember that I work from Penang on Fridays. I prefer short answers.")
        first = form(url, turn)
        second = form(url, turn)
        found = rows(url)

    assert [(one[1], one[2], one[3], one[4], one[5], one[6]) for one in found] == [
        ("adaptive", "I prefer short answers", PERSON, "preference", 1, "desk"),
        ("persistent", "I work from Penang on Fridays", PERSON, "preference", 1, "desk"),
    ]
    assert len(first.memory_ids) == 2  # type: ignore[attr-defined]
    assert second.memory_ids == ()  # type: ignore[attr-defined]
    assert set(second.skipped) == {NotFormed.ALREADY_REMEMBERED}  # type: ignore[attr-defined]


def test_a_stored_correction_stops_the_next_inference_of_the_same_words() -> None:
    """The undo the Learning screen writes, read back by the next formation from the table.

    Delete this and the store could read the person's memories without their corrections, so an
    undo would last until the person next spoke."""
    with through_0061("brain_memory_turn_corrected") as url:
        first = form(url, a_turn("I prefer short answers."))
        [made] = first.memory_ids  # type: ignore[attr-defined]
        sql(
            url,
            "INSERT INTO mem.correction (memory_id, correction, field, recorded_by, at)"
            " VALUES (%s, 'demoted', 'answer.length', 'u_admin', %s)",
            made,
            NOW,
        )
        later = Turn(
            trace_id="trace-two",
            principal_id=PERSON,
            said="I prefer short answers.",
            answered=True,
            reach=reach("read:client.name", scope=WEB),
            at=NOW + timedelta(hours=1),
        )
        again = form(url, later)
        count = sql(url, "SELECT count(*) FROM mem.adaptive")

    assert again.skipped == (NotFormed.CORRECTED,)  # type: ignore[attr-defined]
    assert count == [(1,)]


def test_a_formation_that_fails_does_not_take_the_answer_with_it() -> None:
    """Delete this and a database that refused a memory would turn an answered question into a
    fault the person sees."""

    def broken() -> object:
        msg = "no database"
        raise RuntimeError(msg)

    formations = StoredFormations(broken)  # type: ignore[arg-type]
    assert run(lambda: formations.after_turn(a_turn("I prefer short answers."))) is None


# ------------------------------------------------------------------ recalling for an answer
def recalled(url: str, reader: EntitlementSet, where: dict[str, object], now: datetime) -> object:
    async def go() -> object:
        built = app_engine(url)
        try:
            return await StoredRecall(make_session_factory(built)).recalled(
                reader, where=where, now=now
            )
        finally:
            await built.dispose()

    return run(go)


def test_an_answer_recalls_the_askers_own_memories_most_confident_first_and_nothing_else() -> None:
    """**What a model is shown about the asker, read from the tables as the application role
    (M16.6.3).** Their stated memory and their inference, stated first because it is certain; not
    somebody else's; not the inference once it has decayed below the floor, while the statement
    stays; nothing once they have moved to another department; and not a memory a correction took
    out of recall.

    Delete this and the hints could be read from the whole table, keep a decayed guess, follow a
    person into their new department, or ignore an undo."""
    theirs = reach("read:client.name", scope=WEB)
    here = recall_place(PERSON, "web")
    with through_0061("brain_memory_turn_recall") as url:
        form(
            url,
            a_turn(
                "Remember that I work from Penang on Fridays. I prefer short answers.",
                held=theirs,
                department="web",
            ),
        )
        other = reach("read:client.name", pid="u_other", scope=WEB)
        form(
            url,
            Turn(
                trace_id="trace-other",
                principal_id="u_other",
                said="Remember that I work from Ipoh.",
                answered=True,
                reach=other,
                at=NOW,
                department="web",
            ),
        )
        now = recalled(url, theirs, here, NOW)
        decayed = recalled(url, theirs, here, NOW + timedelta(days=3 * HALF_LIFE_DAYS))
        moved = recalled(
            url,
            reach("read:client.name", scope=Scope.department("ops")),
            recall_place(PERSON, "ops"),
            NOW,
        )
        [(stated_id,)] = sql(url, "SELECT id FROM mem.persistent WHERE principal_id = %s", PERSON)
        sql(
            url,
            "INSERT INTO mem.correction (memory_id, correction, field, recorded_by, at)"
            " VALUES (%s, 'demoted', 'statement', 'u_person', %s)",
            stated_id,
            NOW,
        )
        undone = recalled(url, theirs, here, NOW + timedelta(hours=1))
        theirs_other = recalled(url, other, recall_place("u_other", "web"), NOW)

    assert now == ("I work from Penang on Fridays", "I prefer short answers")
    assert decayed == ("I work from Penang on Fridays",)
    assert moved == ()
    assert undone == ("I prefer short answers",)
    assert theirs_other == ("I work from Ipoh",)


def test_a_recall_that_fails_is_an_answer_with_no_hints() -> None:
    """Delete this and a database that could not be read for hints would fail the question."""

    def broken() -> object:
        msg = "no database"
        raise RuntimeError(msg)

    recall_store = StoredRecall(broken)  # type: ignore[arg-type]
    found = run(
        lambda: recall_store.hints(
            reach("read:client.name"), where={"principal_id": PERSON}, now=NOW, trace_id="t"
        )
    )
    assert found == ()


def test_formation_opens_no_connection_for_words_that_ask_nothing_or_a_refused_turn() -> None:
    """Delete this and every question on an install would take a lock on its asker."""

    def broken() -> object:
        msg = "a connection was opened"
        raise AssertionError(msg)

    formations = StoredFormations(broken)  # type: ignore[arg-type]
    plain = run(lambda: formations.form(a_turn("What is the balance on Acme?")))
    refused = run(
        lambda: formations.form(
            a_turn("Remember that I prefer email.", answered=False, refused=True)
        )
    )
    assert plain.skipped == (NotFormed.NOTHING_TO_REMEMBER,)
    assert refused.skipped == (NotFormed.REFUSED,)
