"""Recall reads the corrections before the reader, so an undo changes what is recalled.

`brain.memory.recall` composes two existing decisions and adds none: `correction.corrected` says
which memories are marked, and `formation.may_recall` says whether one reader may be told one
memory. These tests hold the composition: a marked memory is not recalled whoever asks, a memory a
later correction put back is recalled again, and a memory nothing marked is still subject to reach
and decay exactly as before.

The instants are 2019, far from any wall clock, for CLAUDE.md's reason.

Task ids: M27.7.21
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Final

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.memory.correction import Demotion, Supersession
from brain.memory.digest import Learning, undo
from brain.memory.formation import RECALL_FLOOR, Formation, MemoryKind, clause_place
from brain.memory.recall import recall, standing
from brain.memory.signals import Signal
from brain.memory.tiers import Change, propose

FORMED: Final = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)
NOW: Final = FORMED + timedelta(hours=2)
IN_WEB: Final = clause_place(department="web")
CLIENT_NAME: Final = "read:client.name"
CONTRACT_VALUE: Final = "read:client.contract_value"


def memory(
    memory_id: str,
    *,
    capability: str = CLIENT_NAME,
    replaced_id: str | None = None,
    at: datetime = FORMED,
    confidence: float = 0.9,
) -> Learning:
    return Learning(
        memory_id=memory_id,
        proposal=propose(Change.PREFERENCE, subject=f"subject:{memory_id}"),
        formation=Formation(
            principal_id="u_subject",
            capabilities=(Capability(value=capability),),
            scope=IN_WEB,
            ent_hash="0" * 32,
            formed_at=at,
            kind=MemoryKind.ADAPTIVE,
        ),
        formed_confidence=confidence,
        replaced_id=replaced_id,
        agent_id="desk",
    )


def reader(*capabilities: str) -> EntitlementSet:
    return EntitlementSet(
        principal_id="u_reader",
        grants=tuple(
            Grant(capability=Capability(value=one), scope=Scope.unrestricted())
            for one in capabilities
        ),
    )


def ids(found: object) -> list[str]:
    return [one.memory_id for one in found]  # type: ignore[attr-defined]


def test_a_memory_nothing_marked_is_recalled_to_a_reader_who_reaches_it() -> None:
    """The positive case for every refusal below. Delete this and they are satisfied by a recall
    that returns nothing, which is a system that has stopped remembering."""
    found = recall([memory("m_1")], reader(CLIENT_NAME), now=NOW)

    assert ids(found) == ["m_1"]
    assert found[0].recollection.confidence >= RECALL_FLOOR


def test_an_undone_learning_is_not_recalled_and_the_memory_it_replaced_is() -> None:
    """**The leaf's behaviour, from the domain's own undo.** A learning replaced a memory, and the
    supersession marking the older one was recorded. Recall returns the learning. `digest.undo`
    writes its supersession the other way, and recall then returns the memory it replaced and not
    the learning. Delete this and an undo can be a row and a ledger entry beside a recall that goes
    on returning exactly what it did."""
    before, learnt = memory("m_before"), memory("m_learnt", replaced_id="m_before")
    learnt_it = Supersession("m_before", "m_learnt", Signal.CONTRADICTED, FORMED)
    everyone = reader(CLIENT_NAME)

    first = recall([before, learnt], everyone, now=NOW, supersessions=(learnt_it,))
    undone = undo(learnt, at=FORMED + timedelta(hours=1), supersessions=(learnt_it,))
    assert isinstance(undone.correction, Supersession)
    after = recall(
        [before, learnt], everyone, now=NOW, supersessions=(learnt_it, undone.correction)
    )

    assert ids(first) == ["m_learnt"]
    assert ids(after) == ["m_before"]


def test_a_demoted_memory_is_not_recalled_even_by_a_reader_who_reaches_everything() -> None:
    """A demotion takes effect whoever is asking. Delete this and a reader with a wide enough grant
    is still told a memory a person undid, because reach was asked first and passed."""
    demoted = Demotion(memory_id="m_1", field="subject:m_1", at=FORMED)
    everything = reader(CLIENT_NAME, CONTRACT_VALUE)

    assert recall([memory("m_1")], everything, now=NOW, demotions=(demoted,)) == ()
    assert ids(recall([memory("m_1")], everything, now=NOW)) == ["m_1"]


def test_reach_and_decay_still_decide_what_no_correction_marked() -> None:
    """A memory formed under a capability the reader lacks and one decayed under the floor are
    absent with no correction anywhere, and a fresh reachable one beside them is recalled. Delete
    this and reading corrections can become the whole of recall, which answers everybody everything
    nobody has undone."""
    found = recall(
        [
            memory("m_secret", capability=CONTRACT_VALUE),
            memory("m_faded", at=FORMED - timedelta(days=400)),
            memory("m_fresh"),
        ],
        reader(CLIENT_NAME),
        now=NOW,
    )

    assert ids(found) == ["m_fresh"]


def test_recall_is_most_confident_first_and_the_same_list_twice() -> None:
    """Ties break on the instant and then the id. Delete this and two readings of one store can
    order a prompt's hints differently, which is an answer that changes for no reason."""
    memories = [
        memory("m_b", confidence=0.5),
        memory("m_a", confidence=0.5),
        memory("m_top", confidence=0.95),
    ]

    first = recall(memories, reader(CLIENT_NAME), now=NOW)
    second = recall(list(reversed(memories)), reader(CLIENT_NAME), now=NOW)

    assert ids(first) == ids(second) == ["m_top", "m_a", "m_b"]


def test_standing_keeps_what_nothing_marked_in_the_order_given() -> None:
    """The step both recall and the Memory screen take, over pairs as the screen hands them. Delete
    this and the screen's filter and recall's can disagree about which memories an undo removed."""
    pairs = [(memory("m_2"), "two"), (memory("m_1"), "one"), (memory("m_3"), "three")]
    marked = Demotion(memory_id="m_1", field="subject:m_1", at=FORMED)

    kept = standing(pairs, lambda pair: pair[0].memory_id, demotions=(marked,))

    assert [statement for _, statement in kept] == ["two", "three"]
